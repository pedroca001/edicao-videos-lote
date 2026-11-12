"""Local MLX transcription. Dependencies/model cache belong outside the checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--audio', required=True)
    p.add_argument('--ffmpeg', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--model', default='mlx-community/whisper-large-v3-turbo')
    p.add_argument('--hf-home')
    p.add_argument('--backend', choices=['mlx','faster_whisper'], default='mlx')
    a = p.parse_args()
    if a.hf_home:
        os.environ['HF_HOME'] = a.hf_home
    import numpy as np
    digest = hashlib.sha256(Path(a.audio).read_bytes()).hexdigest()
    out = Path(a.output)
    if out.exists():
        old = json.loads(out.read_text())
        if old.get('source_sha256') == digest and old.get('model') == a.model:
            print('Transcription cache hit', flush=True)
            return
    t = time.monotonic()
    raw = subprocess.run([a.ffmpeg, '-v', 'error', '-i', a.audio, '-vn', '-ac', '1',
                          '-ar', '16000', '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, dtype=np.float32).copy()
    if a.backend == 'faster_whisper':
        # Reuse the local Windows Whisper environment and its CUDA libraries.
        import torch
        from faster_whisper import WhisperModel
        device='cuda' if torch.cuda.is_available() else 'cpu'
        compute_type='float16' if device=='cuda' else 'int8'
        model=WhisperModel(a.model,device=device,compute_type=compute_type,local_files_only=True)
        segments,info=model.transcribe(samples,word_timestamps=True,condition_on_previous_text=False)
        rows=[]
        for segment in segments:
            rows.append(dict(start=segment.start,end=segment.end,text=segment.text,
                             words=[dict(start=w.start,end=w.end,word=w.word,probability=w.probability) for w in (segment.words or [])]))
        result=dict(language=info.language,text=''.join(s['text'] for s in rows).strip(),segments=rows,
                    backend='faster_whisper',device=device,compute_type=compute_type)
    else:
        import mlx_whisper
        result = mlx_whisper.transcribe(samples, path_or_hf_repo=a.model,
                                       word_timestamps=True,
                                       condition_on_previous_text=False, verbose=None)
    result.update(source_sha256=digest, model=a.model, audio_duration=len(raw)/4/16000,
                  elapsed_seconds=round(time.monotonic()-t, 3))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'language': result['language'], 'text': result['text'],
                      'seconds': result['elapsed_seconds']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
