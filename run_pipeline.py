"""Run one or more narration/plan pairs and discard all working files on exit."""
import argparse
import atexit
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def final_report(stdout):
    match = re.search(r'(?m)^\{\s*"version"\s*:', stdout)
    if not match:
        raise RuntimeError('Editor did not return its final report')
    return json.JSONDecoder().raw_decode(stdout[match.start():])[0]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--avatar':
        from edit_avatar_batch import main as avatar_main
        raise SystemExit(avatar_main(sys.argv[2:]))
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task', nargs=2, action='append', required=True,
                   metavar=('AUDIO', 'PLAN'), help='Repeat for each audio and its job manifest')
    p.add_argument('--output', required=True, help='Destination for final verified MP4s')
    p.add_argument('--ffmpeg', required=True)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--transcribe-python', default=sys.executable)
    p.add_argument('--hf-home')
    p.add_argument('--model', default='mlx-community/whisper-large-v3-turbo')
    p.add_argument('--backend', choices=['mlx','faster_whisper'], default='mlx')
    p.add_argument('--encoder', choices=['h264_videotoolbox', 'libx264','h264_nvenc'], default='h264_videotoolbox')
    a = p.parse_args()
    if not 1 <= a.workers <= 4:
        p.error('workers must be 1..4')

    code = Path(__file__).resolve().parent
    env = os.environ.copy()
    env['HF_HUB_OFFLINE'] = '1'
    results = []
    # exFAT can create AppleDouble metadata siblings for files just written by
    # this run. Remove only siblings of outputs that did not preexist.
    new_outputs = []
    for _, plan in a.task:
        for job in json.loads(Path(plan).read_text()):
            target = Path(a.output)/(job['id']+'.mp4')
            if not target.exists():
                new_outputs.append(target)

    def clean_output_metadata():
        for target in new_outputs:
            sidecar = target.with_name('._'+target.name)
            if target.exists() and sidecar.is_file():
                sidecar.unlink()

    atexit.register(clean_output_metadata)
    # The OS temporary area owns plans, transcripts, ASS, frames, state and logs.
    # TemporaryDirectory removes everything on success, error, or interruption.
    with tempfile.TemporaryDirectory(prefix='local_video_editor_') as scratch_dir:
        scratch = Path(scratch_dir)
        for index, (audio, plan) in enumerate(a.task, start=1):
            print(f'Transcrevendo audio {index}/{len(a.task)}: {Path(audio).name}', flush=True)
            transcript = scratch / f'transcript_{index}.json'
            tr_cmd = [a.transcribe_python, str(code/'transcribe.py'), '--audio', audio,
                      '--ffmpeg', a.ffmpeg, '--output', str(transcript), '--model', a.model,
                      '--backend', a.backend]
            if a.hf_home:
                tr_cmd += ['--hf-home', a.hf_home]
            tr = subprocess.run(tr_cmd, env=env, capture_output=True, text=True)
            if tr.returncode:
                raise RuntimeError(f'Transcription failed for {audio}: {tr.stderr[-3000:]}')
            print(tr.stdout.strip(), flush=True)

            run_dir = scratch / f'run_{index}'
            command = [sys.executable, str(code/'edit_batch.py'), '--plan', plan,
                       '--transcript', str(transcript), '--audio', audio,
                       '--output', a.output, '--runtime', str(run_dir),
                       '--ffmpeg', a.ffmpeg, '--workers', str(a.workers), '--encoder', a.encoder]
            rendered = subprocess.run(command, capture_output=True, text=True)
            if rendered.returncode:
                raise RuntimeError(f'Edit failed for {audio}: {rendered.stderr[-3000:]}\n{rendered.stdout[-3000:]}')
            report = final_report(rendered.stdout)
            if report['errors']:
                raise RuntimeError(f'Edit failed for {audio}: {report["errors"]}')
            results.append(dict(audio=Path(audio).name, jobs=len(report['jobs']),
                                elapsed_seconds=report.get('elapsed_seconds'),
                                outputs=[Path(job['output']).name for job in report['jobs']]))
            print(f'Concluidos e verificados: {len(report["jobs"])} videos deste audio.', flush=True)
    print(json.dumps(dict(completed=results), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
