"""Edit speaking avatars, preserving original A/V sync and removing quiet pauses."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile
import time
import sys

from edit_batch import STYLES, audio_hash, make_ass, run_encoder, sha

FPS = 24
RATE = 48000
SAMPLES_PER_FRAME = RATE // FPS


def kept_ranges(duration, silences, words, fps=FPS, protect_words=True):
    """Remove measured quiet time on frame edges; optional ASR guards for callers."""
    total = round(duration * fps)
    guards = [(max(0, w['start'] - .055), min(duration, w['end'] + .075))
              for w in words] if protect_words else []
    removed = []
    for start, end in silences:
        # Leave a short breath between phrases and protect consonant tails.
        left = .06 if start > .02 else 0
        right = .08 if end < duration - .02 else 0
        candidates = [(start + left, end - right)]
        for a, b in guards:
            split = []
            for x, y in candidates:
                if b <= x or a >= y:
                    split.append((x, y))
                else:
                    if a > x:
                        split.append((x, a))
                    if b < y:
                        split.append((b, y))
            candidates = split
        for a, b in candidates:
            # At least two removable frames; short breathing gaps remain intact.
            first, last = math.ceil(a * fps), math.floor(b * fps)
            if last - first >= 2:
                removed.append((max(0, first), min(total, last)))
    removed.sort()
    merged = []
    for a, b in removed:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    keep, cursor = [], 0
    for a, b in merged:
        if a > cursor:
            keep.append((cursor, a))
        cursor = b
    if cursor < total:
        keep.append((cursor, total))
    if not keep:
        raise ValueError('No speech remains')
    return keep, merged


def remap_words(words, keep, fps=FPS):
    def mapped(t):
        elapsed = 0
        for a, b in keep:
            start, end = a / fps, b / fps
            if t <= end:
                return elapsed + max(0, t - start)
            elapsed += end - start
        return elapsed
    result = []
    for w in words:
        start, end = mapped(w['start']), mapped(w['end'])
        if end > start:
            result.append(dict(word=w['word'], start=start, end=end))
    return result


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, capture_output=True, **kwargs)


def probe(ffprobe, path):
    return json.loads(run([ffprobe, '-v', 'error', '-show_streams', '-show_format',
                           '-of', 'json', str(path)], text=True).stdout)


def analyze(path, index, model, config, scratch):
    import numpy as np
    ffmpeg = config['ffmpeg']
    info = probe(str(Path(ffmpeg).with_name('ffprobe.exe' if os.name == 'nt' else 'ffprobe')), path)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    if (video['width'], video['height'], video['r_frame_rate']) != (720, 1280, '24/1'):
        raise ValueError(f'Avatar mode requires 720x1280/24fps: {path.name}')
    duration = float(video['duration'])
    asr_raw = run([ffmpeg, '-v', 'error', '-i', str(path), '-vn', '-ac', '1',
                   '-ar', '16000', '-f', 'f32le', '-']).stdout
    samples = np.frombuffer(asr_raw, dtype=np.float32)
    segments, info_asr = model.transcribe(samples, language='en', word_timestamps=True,
                                         condition_on_previous_text=False, beam_size=5)
    words, text = [], []
    for segment in segments:
        text.append(segment.text)
        words.extend(dict(word=w.word, start=w.start, end=w.end)
                     for w in (segment.words or []))
    if len(words) < 8:
        raise ValueError(f'Too little recognized speech: {path.name}')
    detection = run([ffmpeg, '-hide_banner', '-nostdin', '-i', str(path), '-vn',
                     '-af', 'silencedetect=noise=-36dB:d=0.24', '-f', 'null', '-'], text=True).stderr
    silences, current = [], None
    for kind, value in re.findall(r'silence_(start|end): ([0-9.]+)', detection):
        if kind == 'start':
            current = float(value)
        elif current is not None:
            silences.append((current, min(float(value), duration)))
            current = None
    if current is not None:
        silences.append((current, duration))
    keep, removed = kept_ranges(duration, silences, words, protect_words=False)
    frames = sum(b-a for a, b in keep)
    row = dict(index=index, source=str(path), source_sha256=sha(path),
               original_duration=duration, duration=frames/FPS, frames=frames,
               keep=keep, removed=removed, silences=silences, original_words=words,
               words=remap_words(words, keep), text=''.join(text).strip(),
               visual_reviewed=False)
    (scratch/f'analysis_{index:03}.json').write_text(json.dumps(row, indent=2), encoding='utf8')
    print(json.dumps(dict(event='analyzed', name=path.name, duration=row['duration'],
                          removed_seconds=round(duration-row['duration'], 3), text=row['text'])), flush=True)
    return row


def render(row, config, output, scratch, caption_y, previous_sha=None):
    import numpy as np
    start = time.monotonic()
    source = Path(row['source'])
    destination = output/(source.stem+'__editado.mp4')
    if destination.exists() and (not previous_sha or sha(destination) != previous_sha):
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(prefix=f'avatar_{row["index"]:03}_', dir=scratch) as jobdir:
        job = Path(jobdir)
        ffmpeg = config['ffmpeg']
        raw = run([ffmpeg, '-v', 'error', '-i', str(source), '-vn', '-ac', '2',
                   '-ar', str(RATE), '-f', 'f32le', '-']).stdout
        original = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)
        parts = []
        gains = []
        scene_gains={}
        if row.get('fluid'):
            for scene in range(5):
                region=original[scene*8*RATE:(scene+1)*8*RATE]
                windows=np.sqrt(np.mean(region[:len(region)//480*480].reshape(-1,480,2)**2,axis=(1,2)))
                voiced=windows[windows>.012]
                level=float(np.percentile(voiced,65)) if len(voiced) else .08
                peak=max(float(np.max(np.abs(region))),.001)
                scene_gains[scene]=min(float(np.clip(.09/max(level,.001),.65,1.5)),.88/peak)
        for i, (a, b) in enumerate(row['keep']):
            piece = original[a*SAMPLES_PER_FRAME:b*SAMPLES_PER_FRAME].copy()
            if len(piece) != (b-a)*SAMPLES_PER_FRAME:
                raise ValueError('Source audio shorter than planned video')
            fade = min(144, len(piece))  # 3ms, only at measured quiet cut boundaries.
            if i:
                piece[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)[:, None]
            if i < len(row['keep'])-1:
                piece[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
            if not np.array_equal(piece[fade:-fade], original[a*SAMPLES_PER_FRAME+fade:b*SAMPLES_PER_FRAME-fade]):
                raise RuntimeError('Retained speech samples changed')
            gain=1.0
            if row.get('fluid'):
                # Fixed per original scene, avoiding gain pumping at internal cuts.
                gain=scene_gains[a//(8*FPS)]
                piece *= gain
            gains.append(gain)
            parts.append(piece)
        edited = np.concatenate(parts)
        speed = row.get('speed', 1.0)
        pcm = job/'voice.f32'
        edited.tofile(pcm)
        voice = job/'voice.m4a'
        audio_cmd = [ffmpeg, '-v', 'error', '-y', '-f', 'f32le', '-ar', str(RATE), '-ac', '2', '-i', str(pcm)]
        output_fps=row.get('output_fps',FPS)
        if speed != 1.0:
            audio_cmd += ['-af', f'atempo={speed},apad,atrim=end_sample={round(row["frames"]/output_fps*RATE)}']
        run(audio_cmd + ['-c:a', 'aac', '-b:a', '192k', str(voice)])
        expected_aac = audio_hash(ffmpeg, voice)
        style = dict(STYLES[row['style']], y=caption_y)
        if row.get('fluid'):
            style.update(size=50 if style['mode']=='card' else 52,animate=False)
        if row.get('footer_top'):
            style.update(y=1050,fg='161616',accent='426E2C',outline=0)
        transcript = dict(segments=[dict(words=row['words'])])
        (job/'captions.ass').write_text(make_ass(transcript, style, row['duration']), encoding='utf8')
        clean=[]
        for patch in row.get('source_cleanup',[]):
            x,y,w,h=patch['rect']
            if not (1<=x<720 and 1<=y<1280 and x+w<720 and y+h<1280):
                raise ValueError('Cleanup rectangle must stay inside source canvas')
            clean.append(f"delogo=x={x}:y={y}:w={w}:h={h}:enable='between(t,{patch['start']},{patch['end']})'")
        filters = [f'[0:v]'+(''.join(x+',' for x in clean))+f'split={len(parts)}'+''.join(f'[s{i}]' for i in range(len(parts)))]
        last_scene=None;zoomed=False;clip_zooms=[]
        for i, (a, b) in enumerate(row['keep']):
            scene=a//(8*FPS)
            zoomed=(not zoomed) if row.get('punch_in') and scene==last_scene else False
            last_scene=scene
            transform=',crop=680:1208:20:0,scale=720:1280' if zoomed else ''
            clip_zooms.append(720/680 if zoomed else 1.0)
            if row.get('footer_top'):
                top=row['footer_top']
                if not isinstance(top,int) or not 880<=top<=1080:
                    raise ValueError('Caption footer must preserve the upper subject area')
                transform+=f',crop=720:{top}:0:0,pad=720:1280:0:0:color=0xF8F6EF'
            filters.append(f'[s{i}]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS{transform},setsar=1[v{i}]')
        if row.get('fluid'):
            rate_filter=f'setpts=N/({output_fps}*TB),fps={output_fps},trim=end_frame={row["frames"]},'
        else:
            rate_filter = '' if speed == 1.0 else f'setpts=PTS/{speed},fps={FPS},trim=end_frame={row["frames"]},'
        filters.append(''.join(f'[v{i}]' for i in range(len(parts)))+
                       f'concat=n={len(parts)}:v=1:a=0,{rate_filter}ass=captions.ass[out]')
        (job/'filter.txt').write_text(';\n'.join(filters), encoding='utf8')
        encoder = config['encoder']
        cmd = [ffmpeg, '-hide_banner', '-nostdin', '-y', '-filter_complex_threads', '2',
               '-i', str(source), '-i', str(voice), '-filter_complex_script', 'filter.txt',
               '-map', '[out]', '-map', '1:a:0', '-c:v', encoder]
        if encoder == 'h264_nvenc':
            cmd += ['-preset', 'p4', '-rc', 'vbr', '-cq', '19', '-b:v', '0']
        elif encoder == 'libx264':
            cmd += ['-preset', 'fast', '-crf', '19']
        else:
            cmd += ['-b:v', '5500k']
        cmd += ['-pix_fmt', 'yuv420p', '-r', str(output_fps), '-c:a', 'copy',
                '-movflags', '+faststart', '-map_metadata', '-1', 'render.mp4']
        retries = run_encoder(cmd, job, encoder)
        result = job/'render.mp4'
        check = run([ffmpeg, '-v', 'error', '-xerror', '-i', str(result), '-progress',
                     'pipe:1', '-nostats', '-f', 'null', '-'], text=True)
        decoded = re.findall(r'^frame=(\d+)$', check.stdout, re.M)
        if check.stderr.strip() or not decoded or int(decoded[-1]) != row['frames']:
            raise RuntimeError(f'Decode/frame verification failed: {source.name}')
        if audio_hash(ffmpeg, result) != expected_aac:
            raise RuntimeError('Edited AAC changed during mux')
        digest = sha(result)
        partial = destination.with_name('.'+destination.name+'.partial')
        try:
            shutil.copyfile(result, partial)
            if sha(partial) != digest:
                raise RuntimeError('Destination copy hash mismatch')
            if destination.exists() and (not previous_sha or sha(destination) != previous_sha):
                raise FileExistsError(destination)
            if destination.exists():
                os.replace(partial, destination)
            else:
                os.rename(partial, destination)
        finally:
            if partial.exists():
                partial.unlink()
        if sha(source) != row['source_sha256']:
            raise RuntimeError('Source changed during edit')
        receipt = dict(source=source.name, output=str(destination), duration=row['duration'],
                       original_duration=row['original_duration'], frames=row['frames'],
                       cuts=len(row['removed']), style=style['name'], caption_y=style['y'],
                       source_sha256=row['source_sha256'], output_sha256=digest,
                       audio_sha256=expected_aac, decode_verified=True, pcm_verified=True,
                       copy_verified=True, encoder_retries=retries,
                       speed=speed,
                       output_fps=output_fps,clip_audio_gains=gains,footer_top=row.get('footer_top'),clip_zooms=clip_zooms,
                       seconds=round(time.monotonic()-start, 3))
        print(json.dumps(dict(event='completed', **receipt)), flush=True)
        return receipt


def storyboard(ffmpeg, paths, scratch):
    from PIL import Image, ImageDraw
    sheet = Image.new('RGB', (3*360, len(paths)*680), '#eeeeee')
    draw = ImageDraw.Draw(sheet)
    for r, path in enumerate(paths):
        for c, t in enumerate([1.8, 12, 24]):
            frame = scratch/f'frame_{r}_{c}.png'
            run([ffmpeg, '-v', 'error', '-y', '-ss', str(t), '-i', str(path),
                 '-frames:v', '1', '-vf', 'scale=360:640', str(frame)])
            with Image.open(frame) as im:
                sheet.paste(im, (c*360, r*680+40))
        draw.text((8, r*680+8), path.name[:65], fill='black')
    target = scratch/'pilot_storyboard.jpg'
    sheet.save(target, quality=90)
    return target


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if '--speech-only' in argv:
        from avatar_speech import main as speech_main
        return speech_main(argv)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True)
    p.add_argument('--videos', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--caption-y', type=int, default=1000)
    p.add_argument('--review-pilots', action='store_true')
    p.add_argument('--analysis-cache', help='Same-session JSON cache; all source/output hashes must match')
    a = p.parse_args(argv)
    if not 700 <= a.caption_y <= 1040:
        p.error('caption-y must be 700..1040 on the 1280px canvas')
    config = json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
    output = Path(a.output)
    if output.exists() and not a.analysis_cache:
        raise FileExistsError('Use a new output folder')
    sources = sorted((x for x in Path(a.videos).glob('*.mp4') if not x.name.startswith('._')),
                     key=lambda x: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', x.name)])
    if not sources:
        raise ValueError('No source MP4s')
    os.environ['HF_HUB_OFFLINE'] = '1'
    started = time.monotonic()
    previous = {}
    cache = None
    if a.analysis_cache:
        cache = json.loads(Path(a.analysis_cache).read_text(encoding='utf-8-sig'))
        previous = cache['previous_outputs']
        if output.exists() and {str(x) for x in output.iterdir()} != set(previous):
            raise ValueError('Output inventory differs from this session cache')
        for path, digest in previous.items():
            if sha(path) != digest:
                raise ValueError('Existing output changed')
        if {r['source'] for r in cache['rows']} != {str(x) for x in sources}:
            raise ValueError('Source inventory differs from cache')
    else:
        import torch
        from faster_whisper import WhisperModel
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; do not silently change runtime')
        model = WhisperModel(config['model'], device='cuda', compute_type='float16', local_files_only=True)
    with tempfile.TemporaryDirectory(prefix='local_avatar_editor_') as temp:
        scratch = Path(temp)
        print(json.dumps(dict(event='scratch', path=str(scratch), sources=len(sources))), flush=True)
        if cache:
            rows = cache['rows']
            for row in rows:
                if sha(row['source']) != row['source_sha256']:
                    raise ValueError('Source changed since transcription')
                row['keep'], row['removed'] = kept_ranges(row['original_duration'], row['silences'],
                                                        row['original_words'], protect_words=False)
                row['frames'] = sum(b-a for a, b in row['keep'])
                row['duration'] = row['frames']/FPS
                row['words'] = remap_words(row['original_words'], row['keep'])
        else:
            rows = [analyze(source, i, model, config, scratch) for i, source in enumerate(sources)]
            del model
        styles = [tuple(STYLES)[i % len(STYLES)] for i in range(len(rows))]
        random.Random(20261022).shuffle(styles)
        for row, style in zip(rows, styles):
            row['style'] = style
        (scratch/'analysis.json').write_text(json.dumps(rows, indent=2), encoding='utf8')
        output.mkdir(parents=True, exist_ok=bool(a.analysis_cache))
        # Cover the three scripts/styles where present, without rendering the batch first.
        pilots = []
        for version in ['v3_receita', 'v1_esposa', 'v2_alerta']:
            used = {r['style'] for r in pilots}
            row = next((r for r in rows if version in r['source'] and r['style'] not in used), None)
            if row:
                pilots.append(row)
        if not pilots:
            pilots = rows[:3]
        def render_one(row):
            dest = str(output/(Path(row['source']).stem+'__editado.mp4'))
            return render(row, config, output, scratch, a.caption_y, previous.get(dest))
        receipts = [render_one(r) for r in pilots]
        if a.review_pilots:
            sheet = storyboard(config['ffmpeg'], [Path(r['output']) for r in receipts], scratch)
            gate = scratch/'continue.json'
            print(json.dumps(dict(event='review_pilots', storyboard=str(sheet), analysis=str(scratch/'analysis.json'),
                                  gate=str(gate))), flush=True)
            while not gate.exists():
                time.sleep(1)
            if json.loads(gate.read_text()).get('approved') is not True:
                raise RuntimeError('Pilot gate not approved')
        pending = [r for r in rows if r not in pilots]
        errors = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = {pool.submit(render_one, r): r for r in pending}
            for future in as_completed(tasks):
                try:
                    receipts.append(future.result())
                except Exception as error:
                    errors.append(dict(source=tasks[future]['source'], error=str(error)))
        summary = dict(event='summary', sources=len(sources), completed=len(receipts), errors=errors,
                       output=str(output), original_seconds=sum(r['original_duration'] for r in receipts),
                       edited_seconds=sum(r['duration'] for r in receipts),
                       cuts=sum(r['cuts'] for r in receipts), seconds=round(time.monotonic()-started, 3),
                       receipts=receipts)
        print(json.dumps(summary), flush=True)
        return 2 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
