"""Install only the public application files and validate a real captioned render."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

FILES = ['edit_batch.py', 'run_pipeline.py', 'transcribe.py', 'auto_planner.py', 'condensed_planner.py', 'motion_planner.py', 'cut_review.py', 'batch_assistant.py']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', required=True)
    a = p.parse_args()
    root = Path(a.root).expanduser().resolve()
    source = Path(__file__).resolve().parent
    app = root/'app'
    app.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copy2(source/name, app/name)
    os.environ['HF_HOME'] = str(root/'models')
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    import imageio_ffmpeg
    from huggingface_hub import snapshot_download
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if platform.machine() != 'arm64':
        raise RuntimeError('Este pacote exige Apple Silicon e Python arm64.')
    import mlx.core
    backend, repo = 'mlx', 'mlx-community/whisper-large-v3-turbo'
    model = snapshot_download(repo_id=repo, allow_patterns=['config.json', 'weights.safetensors', 'weights.npz'])
    # Confirm downloaded weights can actually be loaded on this Mac.
    from mlx_whisper.load_models import load_model
    loaded = load_model(model, dtype=mlx.core.float16)
    del loaded

    # Check the entire render stack, not just the encoder listing.
    import sys
    sys.path.insert(0, str(app))
    from edit_batch import STYLES, make_ass
    with tempfile.TemporaryDirectory(prefix='editor_install_check_') as temp:
        scratch = Path(temp)
        text = {'segments':[{'words':[{'word':'Teste', 'start':0, 'end':.8}]}]}
        for i, style in STYLES.items():
            (scratch/f'{i}.ass').write_text(make_ass(text, style, 1))
        encoder = None
        for candidate in ['h264_videotoolbox', 'libx264']:
            result = subprocess.run([ffmpeg, '-v','error','-y','-f','lavfi','-i','color=c=gray:s=720x1280:r=24:d=1',
                                     '-vf', "ass=filename='0.ass'", '-c:v',candidate,'-pix_fmt','yuv420p',str(scratch/'test.mp4')],
                                    cwd=scratch,capture_output=True,text=True)
            if not result.returncode:
                encoder = candidate
                break
        if encoder is None:
            raise RuntimeError('FFmpeg/legendas nao passaram no teste: '+result.stderr)
        for i in tuple(STYLES)[1:]:
            subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=s=720x1280:r=24:d=1',
                            '-vf',f"ass=filename='{i}.ass'",'-f','null','-'],cwd=scratch,check=True)
    config = dict(version='0.8.2', ffmpeg=ffmpeg, backend=backend, model=model, encoder=encoder)
    partial = root/'config.json.partial'
    partial.write_text(json.dumps(config, indent=2))
    os.replace(partial, root/'config.json')
    print('Teste real de video/legendas aprovado. Backend: '+backend+'. Encoder: '+encoder, flush=True)


if __name__ == '__main__':
    main()
