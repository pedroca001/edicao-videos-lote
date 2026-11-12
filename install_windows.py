"""Configure the Windows editor with existing local Whisper, then render a fixture."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--python',dest='python_path')
    p.add_argument('--model')
    p.add_argument('--ffmpeg')
    a=p.parse_args()
    if os.name!='nt':p.error('Este instalador requer Windows')
    whisper=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'LocalWhisper'
    python=Path(a.python_path) if a.python_path else whisper/'venv/Scripts/python.exe'
    if not python.is_file():p.error('Informe --python com faster-whisper, NumPy e PyTorch instalados')
    candidates=list((whisper/'models').glob('models--*faster-whisper*large-v3-turbo*/snapshots/*'))
    candidates=[d for d in candidates if (d/'model.bin').is_file()]
    model=Path(a.model) if a.model else (candidates[0] if len(candidates)==1 else None)
    if not model or not model.is_dir():p.error('Informe --model com o modelo faster-whisper local')
    ffmpeg=a.ffmpeg or shutil.which('ffmpeg')
    if not ffmpeg:p.error('FFmpeg com libass necessario')
    env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1')
    command=lambda args:subprocess.run(args,env=env,check=True,capture_output=True,text=True,encoding='utf-8')
    command([str(python),'-c','import numpy, torch, faster_whisper; print(torch.cuda.is_available())'])
    with tempfile.TemporaryDirectory(prefix='editor_windows_smoke_') as scratch:
        scratch=Path(scratch);video=scratch/'source.mp4';audio=scratch/'voice.m4a'
        command([ffmpeg,'-v','error','-nostdin','-f','lavfi','-i','testsrc2=size=720x1280:rate=24','-t','2','-c:v','libx264','-preset','ultrafast',str(video)])
        command([ffmpeg,'-v','error','-nostdin','-f','lavfi','-i','anullsrc=r=48000:cl=mono','-t','2','-c:a','aac',str(audio)])
        command([str(python),'-B',str(ROOT/'transcribe.py'),'--audio',str(audio),'--ffmpeg',ffmpeg,'--model',str(model),'--backend','faster_whisper','--output',str(scratch/'asr.json')])
        asr=json.loads((scratch/'asr.json').read_text(encoding='utf-8'))
        transcript={'audio_duration':2,'segments':[{'words':[{'word':'Edição','start':.1,'end':.7},{'word':'no','start':.7,'end':1},{'word':'Windows','start':1,'end':1.8}]}]}
        (scratch/'transcript.json').write_text(json.dumps(transcript,ensure_ascii=False),encoding='utf-8')
        sys.path.insert(0,str(ROOT));from edit_batch import STYLES
        jobs=[{'id':f'estilo_{i}','source':str(video),'style':i,'clips':[{'start_frame':0,'end_frame':48}]} for i in STYLES]
        (scratch/'plan.json').write_text(json.dumps(jobs),encoding='utf-8')
        rendered=command([str(python),'-B',str(ROOT/'edit_batch.py'),'--plan',str(scratch/'plan.json'),'--transcript',str(scratch/'transcript.json'),'--audio',str(audio),'--output',str(scratch/'output'),'--runtime',str(scratch/'runtime'),'--ffmpeg',ffmpeg,'--encoder','h264_nvenc'])
        sys.path.insert(0,str(ROOT));from run_pipeline import final_report
        report=final_report(rendered.stdout)
        if report['errors'] or len(report['jobs'])!=len(STYLES):raise RuntimeError('Teste de render falhou: '+str(report['errors']))
        if not all(j['decode_verified'] and j['frames']==48 for j in report['jobs']):raise RuntimeError('Saidas incompletas')
        result={'rendered_styles':len(STYLES),'encoder':'h264_nvenc','decode_verified':True,'audio_packets_verified':True,'asr_backend':asr['backend'],'asr_device':asr['device'],'asr_fixture':'silence_2s'}
    app=Path.home()/'.local/share/local_video_editor';app.mkdir(parents=True,exist_ok=True)
    config={'version':'windows_1','ffmpeg':ffmpeg,'backend':'faster_whisper','model':str(model),'encoder':'h264_nvenc'}
    (app/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    (app/'installation.json').write_text(json.dumps({'root':str(ROOT),'python':str(python),'verification':result},indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
