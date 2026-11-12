"""Opt-in scripted-avatar cleanup: retain spoken text, drop nonverbal gaps, stage replacements."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import tempfile
import time

from edit_avatar_batch import FPS, render, remap_words, run, sha, storyboard
from edit_batch import STYLES


def tokens(text):
    substitutions = {'1':'one', '2':'two', '10':'ten', '30':'thirty',
                     '65':'sixty five', '70':'seventy'}
    text = re.sub(r'\$\s*2\b', 'two dollars', text.lower())
    text = re.sub(r'\b(\d+)\b', lambda m: substitutions.get(m[0], m[0]), text)
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)


def match_speech(words, expected):
    """Match lexical content; do not turn laughs/fillers into retained caption words."""
    actual, owners = [], []
    for i, w in enumerate(words):
        pieces = tokens(w['word'])
        actual.extend(pieces)
        owners.extend([i]*len(pieces))
    reference = tokens(expected)
    matcher = SequenceMatcher(None, reference, actual, autojunk=False)
    matches = matcher.get_matching_blocks()
    coverage = sum(block.size for block in matches)/len(reference)
    if coverage < .82:
        raise ValueError(f'Script coverage too low: {coverage:.1%}; actual={actual}')
    chosen = sorted({owners[j] for block in matches for j in range(block.b, block.b+block.size)})
    result = [words[i] for i in chosen]
    if not result or result[-1]['end'] <= result[0]['start']:
        raise ValueError('No positive speech interval')
    return result, coverage


def speech_ranges(duration, words, silences, fps=FPS):
    """Retain aligned words, with two-frame onset/tail protection and tiny joins."""
    total = round(duration*fps)
    chunks = []
    for w in words:
        a = max(0, math.floor((w['start']-.045)*fps))
        b = min(total, math.ceil((w['end']+.055)*fps))
        if b <= a:
            continue
        if chunks and a <= chunks[-1][1]+1:
            chunks[-1] = (chunks[-1][0], max(b, chunks[-1][1]))
        else:
            chunks.append((a, b))
    # Quiet /f/, /s/, /t/ and word endings can fall below the silence threshold.
    # Never remove acoustic silence inside a matched word. Lexical gaps and
    # nonverbal tails are already discarded by the word envelope above.
    for start, end in silences:
        a, b = math.ceil((start+.025)*fps), math.floor((end-.035)*fps)
        if b-a < 2:
            continue
        candidates=[(a,b)]
        for word in words:
            first=max(0,math.floor((word['start']-.02)*fps))
            last=min(total,math.ceil((word['end']+.04)*fps))
            safe=[]
            for x,y in candidates:
                if last<=x or first>=y:
                    safe.append((x,y))
                else:
                    if x<first:
                        safe.append((x,first))
                    if last<y:
                        safe.append((last,y))
            candidates=safe
        for a,b in candidates:
            if b-a<2:
                continue
            updated=[]
            for x,y in chunks:
                if b<=x or a>=y:
                    updated.append((x,y))
                else:
                    if x<a:
                        updated.append((x,a))
                    if b<y:
                        updated.append((b,y))
            chunks=updated
    # Eliminate tiny video slivers from timing overlap with a quiet cut.
    chunks=[(a,b) for a,b in chunks if b-a >= 2]
    removed=[]
    cursor=0
    for a,b in chunks:
        if a>cursor:
            removed.append((cursor,a))
        cursor=b
    if cursor<total:
        removed.append((cursor,total))
    if not chunks:
        raise ValueError('No speech retained')
    return chunks, removed


def fluid_ranges(duration, scenes, fps=FPS):
    """One uninterrupted speaking shot per generated scene, without pre-roll leaks."""
    keep=[]
    for scene in scenes:
        lower=round((scene['scene']-1)*8*fps)
        upper=min(round(duration*fps),lower+8*fps)
        a=max(lower,math.floor((scene['start']-.055)*fps))
        b=min(upper,math.ceil((scene['end']+.22)*fps))
        if b<=a:
            raise ValueError('Empty scene speech window')
        keep.append((a,b))
    removed=[]
    cursor=0
    for a,b in keep:
        if a>cursor:
            removed.append((cursor,a))
        cursor=b
    if cursor<round(duration*fps):
        removed.append((cursor,round(duration*fps)))
    return keep,removed


def tighten_fluid_ranges(keep, silences, features=None, fps=FPS):
    """Cut only long measured quiet, choosing visually similar edges when available."""
    import numpy as np
    cuts=[]
    for start,end in silences:
        if end-start<.35:
            continue
        candidates=[]
        for a in range(math.ceil((start+.055)*fps),math.ceil((start+.145)*fps)+1):
            for b in range(math.floor((end-.16)*fps),math.floor((end-.10)*fps)+1):
                if b-a<3 or not any(x<=a<b<=y for x,y in keep):
                    continue
                # Compare the frames that will actually touch after the cut.
                pose=float(np.mean((features[a-1]-features[b])**2)) if features is not None else 0
                residual=(a/fps-start)+(end-b/fps)
                candidates.append((pose+.002*residual,a,b))
        if candidates:
            _,a,b=min(candidates)
            cuts.append((a,b))
    result=list(keep)
    for a,b in cuts:
        updated=[]
        for x,y in result:
            if b<=x or a>=y:
                updated.append((x,y))
            else:
                if x<a:
                    updated.append((x,a))
                if b<y:
                    updated.append((b,y))
        result=updated
    return result,cuts


def rebuild_fluid_plan(row, config):
    import numpy as np
    keep,_=fluid_ranges(row['original_duration'],row['scenes'])
    detection=run([config['ffmpeg'],'-hide_banner','-nostdin','-i',row['source'],'-vn',
                   '-af','silencedetect=noise=-40dB:d=0.35','-f','null','-'],text=True).stderr
    silences=[];current=None
    for kind,value in re.findall(r'silence_(start|end): ([0-9.]+)',detection):
        if kind=='start':
            current=float(value)
        elif current is not None:
            silences.append((current,float(value)));current=None
    raw=run([config['ffmpeg'],'-v','error','-i',row['source'],'-vf',
             'crop=720:950:0:0,scale=48:64,format=gray','-f','rawvideo','-']).stdout
    features=np.frombuffer(raw,np.uint8).reshape(-1,48*64).astype(np.float32)/255
    row['keep'],row['quiet_cuts']=tighten_fluid_ranges(keep,silences,features)
    row['removed']=[];cursor=0
    for a,b in row['keep']:
        if a>cursor:
            row['removed'].append((cursor,a))
        cursor=b
    if cursor<round(row['original_duration']*FPS):
        row['removed'].append((cursor,round(row['original_duration']*FPS)))
    row['frames']=sum(b-a for a,b in row['keep'])
    row['duration']=row['frames']/26
    row['words']=remap_words(row['original_words'],row['keep'])
    for word in row['words']:
        word['start']/=row['speed'];word['end']/=row['speed']


def scripts_from_markdown(path):
    text=Path(path).read_text(encoding='utf-8-sig')
    section=text.split('## Falas para revisao rapida',1)[1].split('## Prompts completos',1)[0]
    result={}
    for version, block in re.findall(r'### Versao (\d):([^#]+)', section):
        phrases=re.findall(r'^\d\. (.+)$', block, re.M)
        if len(phrases)!=5:
            raise ValueError('Expected five phrases per version')
        result[int(version)]=phrases
    if set(result)!={1,2,3}:
        raise ValueError('Expected three script versions')
    return result


def analyze_speech(path, index, model, config, scripts, scratch, speed, fluid=False):
    import numpy as np
    from edit_avatar_batch import probe
    info=probe(str(Path(config['ffmpeg']).with_name('ffprobe.exe' if os.name=='nt' else 'ffprobe')),path)
    video=next(s for s in info['streams'] if s['codec_type']=='video')
    duration=float(video['duration'])
    if (video['width'],video['height'],video['r_frame_rate'])!=(720,1280,'24/1') or abs(duration-40)>.02:
        raise ValueError('Scripted avatar requires five 8-second scenes, 720x1280/24fps')
    version=int(re.search(r'__v([123])_',path.name)[1])
    raw=run([config['ffmpeg'],'-v','error','-i',str(path),'-vn','-ac','1','-ar','16000','-f','f32le','-']).stdout
    samples=np.frombuffer(raw,dtype=np.float32)
    words,scenes=[],[]
    for i,expected in enumerate(scripts[version]):
        segments,_=model.transcribe(samples[i*128000:(i+1)*128000],language='en',word_timestamps=True,
                                    condition_on_previous_text=False,beam_size=5)
        recognized=[]
        for segment in segments:
            recognized.extend(dict(word=w.word,start=w.start+i*8,end=w.end+i*8,probability=w.probability)
                              for w in segment.words or [])
        matched,coverage=match_speech(recognized,expected)
        words.extend(matched)
        scenes.append(dict(scene=i+1,start=matched[0]['start'],end=matched[-1]['end'],
                           coverage=coverage,text=''.join(w['word'] for w in recognized)))
    detection=run([config['ffmpeg'],'-hide_banner','-nostdin','-i',str(path),'-vn','-af',
                   'silencedetect=noise=-36dB:d=0.14','-f','null','-'],text=True).stderr
    silences,current=[],None
    for kind,value in re.findall(r'silence_(start|end): ([0-9.]+)',detection):
        if kind=='start':
            current=float(value)
        elif current is not None:
            silences.append((current,min(float(value),duration)))
            current=None
    if current is not None:
        silences.append((current,duration))
    keep,removed=fluid_ranges(duration,scenes) if fluid else speech_ranges(duration,words,silences)
    remapped=remap_words(words,keep)
    for w in remapped:
        w['start']/=speed
        w['end']/=speed
    output_fps=26 if fluid else FPS
    frames=sum(b-a for a,b in keep) if fluid else round(sum(b-a for a,b in keep)/speed)
    row=dict(index=index,source=str(path),source_sha256=sha(path),original_duration=duration,
             duration=frames/output_fps,frames=frames,keep=keep,removed=removed,words=remapped,
             original_words=words,scenes=scenes,speed=speed,visual_reviewed=False,
             output_fps=output_fps,fluid=fluid)
    print(json.dumps(dict(event='analyzed_speech',name=path.name,duration=row['duration'],
                          scenes=scenes,cuts=len(removed))),flush=True)
    return row


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--speech-only',action='store_true')
    p.add_argument('--config',required=True)
    p.add_argument('--videos',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--scripts',required=True)
    p.add_argument('--caption-y',type=int,default=1000)
    p.add_argument('--speed',type=float,default=1.08)
    p.add_argument('--replace-existing',action='store_true')
    p.add_argument('--review-pilots',action='store_true')
    p.add_argument('--fluid',action='store_true',help='Five continuous speech shots; all source frames at 26fps')
    p.add_argument('--cleanup-manifest',help='Explicit source-coordinate delogo regions per filename')
    p.add_argument('--analysis-cache',help='Validated same-session scene analysis, without re-transcription')
    p.add_argument('--punch-in',action='store_true',help='Small deliberate reframing at internal pause edits')
    a=p.parse_args(argv)
    if not 1 <= a.speed <= 1.15 or not 700<=a.caption_y<=1040:
        p.error('Speed must be 1..1.15; caption-y 700..1040')
    cfg=json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
    if a.fluid:
        a.speed=26/24
    cleanup=json.loads(Path(a.cleanup_manifest).read_text(encoding='utf-8-sig')) if a.cleanup_manifest else {}
    sources=sorted(x for x in Path(a.videos).glob('*.mp4') if not x.name.startswith('._'))
    if not sources:
        raise ValueError('No source MP4s')
    out=Path(a.output)
    expected={str(out/(x.stem+'__editado.mp4')) for x in sources}
    if out.exists():
        if not a.replace_existing or {str(x) for x in out.iterdir()}!=expected:
            raise ValueError('Replacement requires explicit flag and exact source/output inventory')
        previous={str(x):sha(x) for x in out.iterdir()}
    else:
        previous={}
    scripts=scripts_from_markdown(a.scripts)
    os.environ['HF_HUB_OFFLINE']='1'
    cache=json.loads(Path(a.analysis_cache).read_text(encoding='utf-8-sig')) if a.analysis_cache else None
    if cache is None:
        import torch
        from faster_whisper import WhisperModel
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA required for this Windows mode')
        model=WhisperModel(cfg['model'],device='cuda',compute_type='float16',local_files_only=True)
    else:
        if {r['source'] for r in cache}!={str(x) for x in sources}:
            raise ValueError('Analysis cache inventory differs from sources')
        for row in cache:
            if sha(row['source'])!=row['source_sha256'] or row.get('fluid')!=a.fluid or row['speed']!=a.speed:
                raise ValueError('Analysis cache signature differs from requested edit')
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='avatar_speech_') as work:
        scratch=Path(work)
        stage=scratch/'staged'
        stage.mkdir()
        print(json.dumps(dict(event='scratch',path=str(scratch))),flush=True)
        rows=cache if cache is not None else [analyze_speech(x,i,model,cfg,scripts,scratch,a.speed,a.fluid) for i,x in enumerate(sources)]
        if cache is None:
            del model
        if a.fluid:
            for row in rows:
                rebuild_fluid_plan(row,cfg)
        styles=[tuple(STYLES)[i % len(STYLES)] for i in range(len(rows))]
        random.Random(20261022).shuffle(styles)
        for row,style in zip(rows,styles):
            row['style']=style
            row['punch_in']=a.punch_in
            correction=cleanup.get(Path(row['source']).name,[])
            row['source_cleanup']=correction.get('regions',[]) if isinstance(correction,dict) else correction
            if isinstance(correction,dict) and 'footer_top' in correction:
                row['footer_top']=correction['footer_top']
        (scratch/'analysis.json').write_text(json.dumps(rows),encoding='utf8')
        pilots=[]
        for version in ['v3_receita','v1_esposa','v2_alerta']:
            row=next((r for r in rows if version in r['source'] and r['style'] not in {x['style'] for x in pilots}),None)
            if row:
                pilots.append(row)
        if a.fluid:
            pilots=random.Random(915246).sample(rows,min(5,len(rows)))
        receipts=[render(r,cfg,stage,scratch,a.caption_y) for r in pilots]
        if a.review_pilots:
            sheet=storyboard(cfg['ffmpeg'],[Path(r['output']) for r in receipts],scratch)
            gate=scratch/'continue.json'
            print(json.dumps(dict(event='review_pilots',sheet=str(sheet),gate=str(gate))),flush=True)
            while not gate.exists():
                time.sleep(1)
            if json.loads(gate.read_text()).get('approved') is not True:
                raise RuntimeError('Pilot gate not approved')
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(render,r,cfg,stage,scratch,a.caption_y) for r in rows if r not in pilots]
            receipts.extend(f.result() for f in as_completed(futures))
        # Keep all previous finals in place until every replacement has passed verification.
        if len(receipts)!=len(sources):
            raise RuntimeError('Incomplete staged batch')
        for path,digest in previous.items():
            if sha(path)!=digest:
                raise ValueError('Previous final changed during rendering')
        out.mkdir(parents=True,exist_ok=True)
        for receipt in receipts:
            candidate=Path(receipt['output'])
            target=out/candidate.name
            partial=out/('.'+target.name+'.partial')
            try:
                shutil.copyfile(candidate,partial)
                if sha(partial)!=receipt['output_sha256']:
                    raise RuntimeError('Replacement copy mismatch')
                if target.exists() and sha(target)!=previous.get(str(target)):
                    raise ValueError('Final changed before replacement')
                os.replace(partial,target)
                receipt['output']=str(target)
            finally:
                if partial.exists():
                    partial.unlink()
        summary=dict(event='summary',sources=len(sources),completed=len(receipts),output=str(out),
                     original_seconds=sum(r['original_duration'] for r in receipts),
                     edited_seconds=sum(r['duration'] for r in receipts),cuts=sum(r['cuts'] for r in receipts),
                     speed=a.speed,seconds=time.monotonic()-started,receipts=receipts)
        print(json.dumps(summary),flush=True)
    return 0
