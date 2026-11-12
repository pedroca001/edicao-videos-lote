"""Build a small source/installer ZIP using an explicit public-file allowlist."""
import argparse
import hashlib
from pathlib import Path
import zipfile

FILES = ['LEIA_PRIMEIRO.md','instalar_mac.command','iniciar_editor.command','install_runtime.py',
         'auto_planner.py', 'condensed_planner.py', 'motion_planner.py', 'cut_review.py', 'batch_assistant.py','edit_batch.py','edit_avatar_batch.py','avatar_speech.py','edit_hook_matrix.py','run_pipeline.py','transcribe.py','requirements_apple.txt']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    hashes = []
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in FILES:
            data = (source/name).read_bytes()
            hashes.append(hashlib.sha256(data).hexdigest()+'  '+name)
            entry = zipfile.ZipInfo('editor_videos_bassi/'+name)
            entry.create_system = 3
            entry.external_attr = (0o100755 if name.endswith('.command') else 0o100644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(entry, data)
        bundle.writestr('editor_videos_bassi/SHA256SUMS.txt', '\n'.join(hashes)+'\n')
    with zipfile.ZipFile(output) as bundle:
        assert bundle.testzip() is None
        assert len(bundle.namelist()) == len(FILES)+1
    print(output)
    print('SHA256: '+hashlib.sha256(output.read_bytes()).hexdigest())
    print('Bytes: '+str(output.stat().st_size))


if __name__ == '__main__':
    main()
