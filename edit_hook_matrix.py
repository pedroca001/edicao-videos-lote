"""Explicit source/audio matrix, native local render, three-pilot review gate.

The manifest contains sources [{path,label}], audios [path], and output.
All working files live in OS TemporaryDirectory; delivery contains only MP4s.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

from auto_planner import automatic_plan
from batch_assistant import inspect_video, balanced_styles
from edit_batch import run_job, audio_hash, STYLES, normalized_words, sha
from motion_planner import decode_analysis_frames
import random


def _pilot_styles(jobs, pilots):
    """Cover active styles where possible, preserving the original batch quotas."""
    for ordinal,index in enumerate(pilots):
        desired=tuple(STYLES)[ordinal % len(STYLES)]
        if jobs[index]['style'] == desired:
            continue
        locked=set(pilots[:ordinal+1])
        donor=next((i for i in range(len(jobs)) if i not in locked and jobs[i]['style']==desired),None)
        if donor is not None:
            jobs[donor]['style'],jobs[index]['style']=jobs[index]['style'],desired


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--config',required=True)
    parser.add_argument('--review-pilots',action='store_true')
    a=parser.parse_args()
    manifest=json.loads(sys.stdin.read() if a.manifest=='-' else Path(a.manifest).read_text(encoding='utf-8-sig'))
    config=json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
    sources=manifest['sources'];audios=[Path(p).resolve() for p in manifest['audios']]
    profile=manifest.get('profile','flow_hook_receita_rapida')
    output=Path(manifest['output']).resolve();ffmpeg=config['ffmpeg']
    import re
    if output.exists() and not manifest.get('append',False):raise FileExistsError('Preserve a entrega anterior: escolha uma pasta nova.')
    if output.exists() and not output.is_dir():raise ValueError('Destino deve ser pasta.')
    preexisting={str(p):sha(p) for p in output.glob('*.mp4')}
    if len({s['label'] for s in sources})!=len(sources) or any(not re.fullmatch('[a-z0-9_]+',s['label']) for s in sources):
        raise ValueError('Rotulos de fontes devem ser unicos e seguros.')
    if not sources or not audios or len(set(audios))!=len(audios) or any(not p.is_file() for p in audios):
        raise ValueError('Fontes/audios vazios, duplicados ou ausentes.')
    if config['backend']=='faster_whisper':
        import torch
        if not torch.cuda.is_available():raise RuntimeError('CUDA obrigatoria neste lote Windows.')
        if config['encoder']!='h264_nvenc':raise RuntimeError('NVENC obrigatorio neste lote Windows.')
        print('GPU: '+torch.cuda.get_device_name(0),flush=True)
    started=time.monotonic()
    originals={str(Path(s['path']).resolve()):sha(s['path']) for s in sources}
    originals.update({str(p):sha(p) for p in audios})
    for s in sources:inspect_video(ffmpeg,Path(s['path']))
    styles=balanced_styles(len(sources)*len(audios),random.Random(5070))
    with tempfile.TemporaryDirectory(prefix='editor_hook_matrix_') as temp:
        scratch=Path(temp);frames={s['label']:decode_analysis_frames(ffmpeg,s['path']) for s in sources}
        records=[];plans=[];texts=[]
        env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1')
        for i,audio in enumerate(audios):
            normalized=scratch/f'voice_{i}.m4a'
            subprocess.run([ffmpeg,'-v','error','-nostdin','-i',str(audio),'-vn','-c:a','aac','-b:a','192k',str(normalized)],check=True)
            transcript_path=scratch/f'transcript_{i}.json'
            print(f'Transcricao CUDA {i+1}/{len(audios)}: {audio.name}',flush=True)
            subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('transcribe.py')),'--audio',str(normalized),
                            '--ffmpeg',ffmpeg,'--output',str(transcript_path),'--model',config['model'],
                            '--backend',config['backend']],env=env,check=True)
            transcript=json.loads(transcript_path.read_text(encoding='utf-8'))
            words=normalized_words(transcript)
            if not words or any(w['start']<0 or w['end']>transcript['audio_duration']+.05 for w in words):
                raise ValueError('Transcricao vazia ou fora da duracao da voz: '+audio.name)
            target=math.ceil(transcript['audio_duration']*24)
            expected=audio_hash(ffmpeg,normalized)
            texts.append(dict(audio=audio.name,text=transcript['text'],duration=transcript['audio_duration'],
                              device=transcript.get('device'),seconds=transcript['elapsed_seconds']))
            for j,s in enumerate(sources):
                source_hash=originals[str(Path(s['path']).resolve())]
                if profile=='flow_hook_receita_rapida' and manifest.get('long_voice'):
                    from condensed_planner import hook_recipe_plan
                    _,report=hook_recipe_plan(frames[s['label']],target,source_hash,3,2,manifest['long_voice'])
                else:
                    _,report=automatic_plan(frames[s['label']],target,source_hash,profile=profile)
                style=styles[len(records)]
                job=dict(id=f'{audio.stem.lower()}_{s["label"]}_{STYLES[style]["name"]}',source=s['path'],style=style,
                         clips=report['clips'],cut_policy=report['policy'])
                if not re.fullmatch('[a-z0-9_]+',job['id']):raise ValueError('Nome de audio inseguro.')
                args=SimpleNamespace(runtime=str(scratch/'renders'),output=str(output),audio=str(normalized),
                                     ffmpeg=ffmpeg,encoder=config['encoder'],fps=24)
                records.append((job,args,transcript,expected));plans.append(report)
        planning_seconds=time.monotonic()-started
        # Shortest, middle and longest voices; distinct hook and subtitle style.
        ranked=sorted(range(len(audios)),key=lambda i:records[i*len(sources)][2]['audio_duration'])
        pilot_indices=[ranked[0]*len(sources),ranked[len(ranked)//2]*len(sources)+min(1,len(sources)-1),
                       ranked[-1]*len(sources)+min(2,len(sources)-1)]
        pilot_indices=list(dict.fromkeys(pilot_indices))
        _pilot_styles([row[0] for row in records],pilot_indices)
        remaining=[i for i in range(len(records)) if i not in pilot_indices]
        # Explicit names are rebuilt from source/audio, avoiding fragile suffix parsing.
        for index,(job,args,_,_) in enumerate(records):
            audio=audios[index//len(sources)];s=sources[index%len(sources)]
            chosen=manifest.get('styles',{}).get(f'{audio.stem.lower()}_{s["label"]}')
            if chosen is not None:
                if chosen not in STYLES:raise ValueError('Estilo invalido no manifesto.')
                job['style']=chosen
            job['id']=f'{audio.stem.lower()}_{s["label"]}_{STYLES[job["style"]]["name"]}'
        if len({r[0]['id'] for r in records})!=len(records) or any((output/(r[0]['id']+'.mp4')).exists() for r in records):
            raise FileExistsError('Matriz colide com saida existente; nenhum render iniciado.')
        reports=[]
        def render(indices):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures={pool.submit(run_job,*records[i]):i for i in indices}
                for future in as_completed(futures):reports.append(future.result())
        render(pilot_indices)
        if a.review_pilots:
            images=[]
            for index in pilot_indices:
                job,args,transcript,_=records[index];duration=transcript['audio_duration']
                sheet=scratch/(job['id']+'.jpg')
                # Early hook, hook/recipe boundary, ingredient joins, final pose.
                hook_end=(job['clips'][0]['end_frame']-job['clips'][0]['start_frame'])/24
                times=[.6,hook_end-.15,hook_end+.15,hook_end+1,duration*.5,duration*.7,duration-4.4,duration-1]
                pngs=[]
                for k,t in enumerate(times):
                    png=scratch/f'frame_{index}_{k}.png';pngs.append(png)
                    subprocess.run([ffmpeg,'-v','error','-ss',str(max(0,t)),'-i',str(output/(job['id']+'.mp4')),
                                    '-frames:v','1','-vf','scale=270:480',str(png)],check=True)
                from PIL import Image,ImageDraw
                canvas=Image.new('RGB',(1080,1000),'white');draw=ImageDraw.Draw(canvas)
                for k,png in enumerate(pngs):
                    canvas.paste(Image.open(png),(k%4*270,k//4*500));draw.text((k%4*270+8,k//4*500+481),f'{times[k]:.2f}s',fill='black')
                canvas.save(sheet);images.append(str(sheet))
            gate=scratch/'continue_after_review'
            (scratch/'review.json').write_text(json.dumps(dict(images=images,texts=texts,pilots=pilot_indices,
                                                              plans=plans,records=[r[0] for r in records],gate=str(gate)),ensure_ascii=False,indent=2),encoding='utf-8')
            print('PILOT_REVIEW '+str(scratch/'review.json'),flush=True)
            while not gate.is_file():time.sleep(.5)
        render(remaining)
        if any(sha(path)!=digest for path,digest in {**originals,**preexisting}.items()):raise RuntimeError('Fonte/voz/final anterior foi alterado.')
        if len(list(output.glob('*.mp4')))!=len(records)+len(preexisting):raise RuntimeError('Contagem final incorreta.')
        print(json.dumps(dict(output=str(output),completed=len(reports),sources=len(sources),audios=len(audios),
                              planning_and_transcription_seconds=round(planning_seconds,3),
                              elapsed_seconds=round(time.monotonic()-started,3),
                              styles={s['name']:sum(r['style']==s['name'] for r in reports) for s in STYLES.values()},
                              reports=reports),ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
