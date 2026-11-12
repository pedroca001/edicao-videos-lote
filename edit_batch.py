"""Explicit edit plans -> local captioned MP4s. No source-clip audio is mapped."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

VERSION = '0.4.2'
# Stable IDs: 1 is retired; historical 2 continues to mean lime.
STYLES = {
    0: dict(name='impacto_amarelo', font='Arial Black', size=57, y=342, fg='FFFFFF', accent='31E8FF', outline=4, upper=True, words=3, limit=21, mode='pop'),
    2: dict(name='duas_linhas_lima', font='Arial Rounded MT Bold', size=57, y=360, fg='FFFFFF', accent='6BFFCE', outline=4, upper=True, words=4, limit=29, mode='stack'),
}
if os.name == 'nt':
    STYLES[2]['font']='Arial Black'



def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def atomic_json(path, obj):
    p = Path(path)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    os.replace(tmp, p)


def normalized_words(transcript):
    words = []
    for segment in transcript['segments']:
        for w in segment['words']:
            token = w['word'].strip()
            if not token:
                continue
            if token.startswith('-') and words:
                words[-1]['text'] += token
                words[-1]['end'] = float(w['end'])
            else:
                words.append(dict(text=token, start=float(w['start']), end=float(w['end'])))
    for i, w in enumerate(words):
        if w['end'] <= w['start']:
            w['end'] = w['start'] + .04
        if i and w['start'] < words[i-1]['start']:
            raise ValueError('Non-monotonic word timestamps')
    return words


def group_words(words, style):
    groups, chunk = [], []
    for w in words:
        chars = len(' '.join([x['text'] for x in chunk] + [w['text']]))
        gap = chunk and w['start'] - chunk[-1]['end'] > .32
        if chunk and (len(chunk) >= style['words'] or chars > style['limit'] or gap):
            groups.append(chunk)
            chunk = []
        chunk.append(w)
        if w['text'].endswith(('.', '?', '!', ',')):
            groups.append(chunk)
            chunk = []
    if chunk:
        groups.append(chunk)
    return groups


def stamp(sec):
    cs = max(0, round(sec * 100))
    return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'


def escape(s):
    return s.replace('\\', '').replace('{', '').replace('}', '').replace('\n', ' ')


def make_ass(transcript, style, duration):
    lines = [
        '[Script Info]', 'ScriptType: v4.00+', 'PlayResX: 720', 'PlayResY: 1280',
        'WrapStyle: 2', 'ScaledBorderAndShadow: yes', '', '[V4+ Styles]',
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
        f"Style: Main,{style['font']},{style['size']},&H00{style['fg']},&H00{style['accent']},&H0014100B,&H80000000,-1,0,0,0,100,100,0,0,1,{style['outline']},1.5,5,58,80,0,1",
        '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
    ]
    groups = group_words(normalized_words(transcript), style)
    for gi, group in enumerate(groups):
        start = group[0]['start']
        next_start = groups[gi+1][0]['start'] if gi+1 < len(groups) else duration
        end = min(duration, next_start, group[-1]['end']+.14)
        y = style['y']
        if style['mode'] in ('card', 'panel'):
            # Fixed compact cards keep layout stable when the active word changes.
            half = 286 if style['mode'] == 'card' else 280
            h = 52
            path = f'm {-half+16} {-h} l {half-16} {-h} b {half} {-h} {half} {-h} {half} {-h+16} l {half} {h-16} b {half} {h} {half} {h} {half-16} {h} l {-half+16} {h} b {-half} {h} {-half} {h} {-half} {h-16} l {-half} {-h+16} b {-half} {-h} {-half} {-h} {-half+16} {-h}'
            bg = '{'+fr'\an7\pos(354,{y})\p1\bord0\shad0\1c&H17100B&\1a&H28&\fad(70,60)'+'}'+path+'{\\p0}'
            lines.append(f'Dialogue: 0,{stamp(start)},{stamp(end)},Main,,0,0,0,,{bg}')
        for wi, word in enumerate(group):
            a = word['start'] if wi else start
            b = min(end, group[wi+1]['start']) if wi+1 < len(group) else end
            if b <= a:
                continue
            motion = ''
            if wi == 0 and style.get('animate', True):
                if style['mode'] in ('pop', 'stack'):
                    motion = r'\fscx94\fscy94\t(0,90,\fscx103\fscy103)\t(90,170,\fscx100\fscy100)'
                elif style['mode'] == 'rise':
                    motion = fr'\move(354,{y+12},354,{y},0,120)'
                elif style['mode'] == 'fade':
                    motion = r'\fad(70,0)'
            pos = '' if '\\move' in motion else fr'\pos(354,{y})'
            prefix = '{'+r'\an5'+pos+motion+'}'
            parts = []
            for j, w in enumerate(group):
                color = style['accent'] if j == wi else style['fg']
                text = escape(w['text'].upper() if style['upper'] else w['text'])
                sep = r'\N' if style['mode'] == 'stack' and len(group) >= 3 and j == 2 else (' ' if j else '')
                parts.append(sep+'{'+fr'\1c&H{color}&'+'}'+text)
            lines.append(f'Dialogue: 1,{stamp(a)},{stamp(b)},Main,,0,0,0,,{prefix}{"".join(parts)}')
    return '\n'.join(lines)+'\n'


def clip_frames(clip):
    length=clip['end_frame']-clip['start_frame']
    output=clip.get('output_frames',length)
    if not isinstance(output,int) or output < 1:
        raise ValueError('Invalid output frame count')
    if output > length and (clip.get('authorized_slowdown') is not True or length/output < .8):
        raise ValueError('Slowdown requires explicit authorization and speed >= 0.80x')
    if length/output > 1.20001:
        raise ValueError('Invalid selective speed duration (maximum 1.20x)')
    return output


def timeline_frames(clips):
    total = 0
    for i, clip in enumerate(clips):
        start, end = clip['start_frame'], clip['end_frame']
        if start < 0 or end <= start:
            raise ValueError('Invalid trim')
        length = clip_frames(clip)
        overlap = clip.get('transition_frames', 0) if i else 0
        if overlap < 0 or overlap >= length or (i and overlap >= total):
            raise ValueError('Invalid transition overlap')
        total += length-overlap
    return total


def build_filter(job, fps, subtitle='captions.ass'):
    clips = job['clips']
    timeline_frames(clips)
    filters = [f'[0:v]fps={fps},settb=1/{fps},split={len(clips)}'+''.join(f'[s{i}]' for i in range(len(clips)))]
    for i, c in enumerate(clips):
        zoom = c.get('zoom', 1.)
        w, h = round(720/zoom)//2*2, round(1280/zoom)//2*2
        timing = f'setpts=(PTS-STARTPTS)*{clip_frames(c)}/{c["end_frame"]-c["start_frame"]}'
        filters.append(f'[s{i}]trim=start_frame={c["start_frame"]}:end_frame={c["end_frame"]},{timing},crop={w}:{h},scale=720:1280:flags=lanczos,setsar=1,format=yuv420p,fps={fps},tpad=stop_mode=clone:stop_duration={1/fps:.8f},trim=end_frame={clip_frames(c)},settb=1/{fps}[v{i}]')
    previous = 'v0'
    groups = []
    total = clip_frames(clips[0])
    for i,c in enumerate(clips[1:], 1):
        name = f'j{i}'
        overlap = c.get('transition_frames', 0)
        if overlap:
            filters.append(f'[{previous}][v{i}]xfade=transition={c.get("transition", "fade")}:duration={overlap/fps:.8f}:offset={(total-overlap)/fps:.8f},fps={fps},settb=1/{fps}[{name}]')
        else:
            # Keep concat downstream of xfade: concat does not advertise CFR.
            groups.append(previous)
            previous = f'v{i}'
            total = clip_frames(c)
            continue
        total += clip_frames(c)-overlap
        previous = name
    groups.append(previous)
    filters.append(''.join(f'[{g}]' for g in groups)+f'concat=n={len(groups)}:v=1:a=0,fps={fps}[joined]')
    filters.append(f"[joined]tpad=stop_mode=clone:stop_duration=1,trim=end_frame={timeline_frames(clips)},setpts=PTS-STARTPTS,ass=filename='{subtitle}',format=yuv420p[out]")
    return ';\n'.join(filters)


def audio_hash(ffmpeg, path):
    raw = subprocess.run([ffmpeg, '-v', 'error', '-i', str(path), '-map', '0:a:0',
                          '-c:a', 'copy', '-f', 'adts', '-'], check=True, capture_output=True).stdout
    return hashlib.sha256(raw).hexdigest()


def run_encoder(cmd, runtime, encoder):
    """Retry one NVENC initialization rejection before any output packets."""
    log = runtime/'render.log'
    for attempt in range(2):
        try:
            with log.open('a' if attempt else 'w') as output:
                subprocess.run(cmd, cwd=runtime, stdout=output,
                               stderr=subprocess.STDOUT, check=True)
            return attempt
        except subprocess.CalledProcessError as error:
            detail = log.read_text(encoding='utf8', errors='replace')[-4000:]
            result = runtime/'render.mp4'
            empty = not result.exists() or result.stat().st_size == 0
            if (attempt == 0 and encoder == 'h264_nvenc' and empty
                    and 'OpenEncodeSessionEx failed: incompatible client key (21)' in detail
                    and 'Nothing was written into output file' in detail):
                time.sleep(.5)
                continue
            raise RuntimeError(f'{encoder} failed ({error.returncode}):\n{detail}') from error


def run_job(job, args, transcript, expected_audio_hash):
    if job['style'] not in STYLES:
        raise ValueError('Estilo removido ou desconhecido. Use 0 (amarelo) ou 2 (lima).')
    t = time.monotonic()
    runtime = Path(args.runtime)/job['id']
    runtime.mkdir(parents=True, exist_ok=True)
    output = Path(args.output)/(job['id']+'.mp4')
    source = Path(job['source'])
    signature = hashlib.sha256(json.dumps(dict(version=VERSION, job=job, transcript=transcript,
                  source=sha(source), audio=sha(args.audio), encoder=args.encoder), sort_keys=True).encode()).hexdigest()
    state = runtime/'state.json'
    if output.exists():
        old = json.loads(state.read_text()) if state.exists() else {}
        if old.get('signature') == signature and old.get('output_sha256') == sha(output):
            return dict(old, cached=True)
        raise FileExistsError(f'Existing output not verified for this job: {output}')
    style = STYLES[job['style']]
    duration = transcript['audio_duration']
    frames = timeline_frames(job['clips'])
    if abs(frames/args.fps-duration) > 1/args.fps+.002:
        raise ValueError('Timeline must match narration within one frame')
    (runtime/'captions.ass').write_text(make_ass(transcript, style, duration))
    (runtime/'filter.txt').write_text(build_filter(job, args.fps))
    atomic_json(runtime/'plan.json', job)
    cmd=[args.ffmpeg, '-hide_banner', '-nostdin', '-y', '-filter_complex_threads', '2',
         '-i', str(source), '-i', args.audio, '-filter_complex_script', 'filter.txt',
         '-map', '[out]', '-map', '1:a:0', '-c:v', args.encoder]
    if args.encoder == 'h264_videotoolbox':
        cmd += ['-b:v', '5500k', '-maxrate', '8000k', '-bufsize', '16000k', '-profile:v', 'high']
    elif args.encoder == 'h264_nvenc':
        cmd += ['-preset', 'p4', '-rc', 'vbr', '-cq', '19', '-b:v', '0']
    else:
        cmd += ['-preset', 'fast', '-crf', '19']
    cmd += ['-pix_fmt','yuv420p','-r',str(args.fps),'-c:a','copy','-t',f'{frames/args.fps:.8f}',
            '-movflags','+faststart','-map_metadata','-1','render.mp4']
    atomic_json(runtime/'command.json',cmd)
    print(f'Start {job["id"]}',flush=True)
    encoder_retries = run_encoder(cmd, runtime, args.encoder)
    render_seconds = time.monotonic()-t
    result = runtime/'render.mp4'
    # Decode all frames and audio, fail on decoding errors, not just container existence.
    check=subprocess.run([args.ffmpeg,'-v','error','-xerror','-i',str(result),'-progress','pipe:1','-nostats','-f','null','-'],capture_output=True,text=True)
    if check.returncode or check.stderr.strip():
        raise RuntimeError('Decode verification failed: '+check.stderr)
    decoded = re.findall(r'^frame=(\d+)$', check.stdout, re.MULTILINE)
    if not decoded or int(decoded[-1]) != frames:
        raise RuntimeError(f'Expected {frames} decoded frames, got {decoded[-1:]!r}')
    actual_audio_hash=audio_hash(args.ffmpeg,result)
    if actual_audio_hash != expected_audio_hash:
        raise RuntimeError('Output AAC differs from supplied narration')
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    # A local scratch directory and removable output volume are different
    # filesystems. Copy to a sibling temporary file, verify, then rename locally.
    partial = output.with_name('.'+output.name+'.partial')
    try:
        shutil.copyfile(result, partial)
        if sha(partial) != sha(result):
            raise RuntimeError('Copied output hash differs from verified render')
        os.replace(partial,output)
    finally:
        if partial.exists():
            partial.unlink()
    report=dict(id=job['id'],signature=signature,output=str(output),source=str(source),
                style=style['name'],frames=frames,duration=frames/args.fps,
                render_seconds=round(render_seconds,3),total_seconds=round(time.monotonic()-t,3),
                output_sha256=sha(output),audio_packets_sha256=actual_audio_hash,decode_verified=True,cached=False,
                encoder_retries=encoder_retries)
    atomic_json(state,report)
    print(f'Done {job["id"]}: {report["render_seconds"]}s render',flush=True)
    return report


def main():
    p=argparse.ArgumentParser()
    for field in ('plan','transcript','audio','output','runtime','ffmpeg'):
        p.add_argument('--'+field,required=True)
    p.add_argument('--workers',type=int,default=2)
    p.add_argument('--fps',type=int,default=24)
    p.add_argument('--encoder',default='h264_videotoolbox',choices=['h264_videotoolbox','libx264','h264_nvenc'])
    a=p.parse_args()
    if not 1 <= a.workers <= 4:
        p.error('workers must be 1..4')
    jobs=json.loads(Path(a.plan).read_text())
    if len({j['id'] for j in jobs})!=len(jobs) or any(not re.fullmatch(r'[a-z0-9_]+',j['id']) for j in jobs):
        p.error('Job ids must be distinct safe file names')
    transcript=json.loads(Path(a.transcript).read_text())
    expected=audio_hash(a.ffmpeg,a.audio)
    t=time.monotonic()
    report=dict(version=VERSION,started_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),jobs=[],errors=[])
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futures={ex.submit(run_job,j,a,transcript,expected):j['id'] for j in jobs}
        for f in as_completed(futures):
            try:
                report['jobs'].append(f.result())
            except Exception as err:
                report['errors'].append(dict(id=futures[f],error=str(err)))
                print('FAILED',futures[f],str(err),flush=True)
            report['elapsed_seconds']=round(time.monotonic()-t,3)
            atomic_json(Path(a.runtime)/'report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['errors']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
