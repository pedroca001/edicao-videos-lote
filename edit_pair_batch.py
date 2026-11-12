"""Render one final per assigned hook/recipe/audio pair, without visual review."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

from condensed_planner import hook_recipe_plan
from edit_batch import run_job, sha, audio_hash, normalized_words, STYLES
from motion_planner import decode_analysis_frames


def load(path, default):
    for attempt in range(6):
        try:
            return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default
        except PermissionError:
            if os.name != 'nt' or attempt == 5:
                raise
            time.sleep(.02 * (attempt + 1))


def matching_voice_transcript(cache, index, normalized, ffmpeg):
    if not cache:
        return None
    cache = Path(cache)
    old_audio, old_transcript = cache/f'voice_{index}.m4a', cache/f'voice_{index}.json'
    if not old_audio.is_file() or not old_transcript.is_file():
        return None
    if audio_hash(ffmpeg, old_audio) != audio_hash(ffmpeg, normalized):
        return None
    transcript = load(old_transcript, {})
    if not isinstance(transcript.get('segments'), list) or transcript.get('audio_duration', 0) <= 0:
        return None
    try:
        if not normalized_words(transcript):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return transcript


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest')
    p.add_argument('--config', required=True)
    p.add_argument('--flow-root', required=True)
    p.add_argument('--watch', action='store_true')
    p.add_argument('--reuse-voice-cache', help='Previous scratch voices; reused only after exact AAC comparison.')
    a = p.parse_args()
    root = Path(a.manifest).resolve().parent
    manifest = load(Path(a.manifest), {})
    target = int(manifest['quantity'])
    if any(pair['style'] not in STYLES for pair in manifest['pairs']):
        raise ValueError('Manifesto usa estilo removido. Ativos: 0 amarelo e 2 lima.')
    config = load(Path(a.config), {})
    sys.path.insert(0, str(Path(a.flow_root).resolve()))
    sys.path.insert(0, str(Path(a.flow_root).resolve()/'scripts'))
    import bridge
    import platform_lock
    from compose_hook_recipe import compose
    if os.name == 'nt':
        import torch
        if config['encoder'] != 'h264_nvenc' or not torch.cuda.is_available():
            raise ValueError('Windows batch requires installed CUDA/NVENC.')
        print('GPU '+torch.cuda.get_device_name(0),flush=True)
    output = Path(manifest['destination'])
    if not output.parent.is_dir():
        raise ValueError('Delivery volume is not mounted.')
    audios = list(dict.fromkeys(pair['audio'] for pair in manifest['pairs']))
    print('Preparing '+str(len(audios))+' reusable narration transcripts.',flush=True)
    with (root/'pair_editor.lock').open('a') as lock, tempfile.TemporaryDirectory(prefix='editor_pairs_') as temp:
        platform_lock.flock(lock, platform_lock.LOCK_EX | platform_lock.LOCK_NB)
        scratch = Path(temp)
        voice_cache = {}
        for index, audio in enumerate(audios):
            normalized = scratch/f'voice_{index}.m4a'
            transcript_path = scratch/f'voice_{index}.json'
            subprocess.run([config['ffmpeg'],'-v','error','-nostdin','-i',audio,'-vn','-c:a','aac','-b:a','192k',str(normalized)],check=True)
            env = os.environ.copy()
            env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1')
            transcript = matching_voice_transcript(a.reuse_voice_cache, index, normalized, config['ffmpeg'])
            if transcript is None:
                subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('transcribe.py')),'--audio',str(normalized),
                                '--ffmpeg',config['ffmpeg'],'--output',str(transcript_path),'--model',config['model'],
                                '--backend',config['backend']],env=env,check=True)
                transcript = load(transcript_path,{})
            else:
                bridge.atomic(transcript_path, transcript)
                print('Reused verified narration '+str(index), flush=True)
            voice_cache[audio] = (normalized,transcript,audio_hash(config['ffmpeg'],normalized),sha(audio))
        def render(pair):
            receipt_path = root/'edit_receipts'/(pair['id']+'.json')
            normalized, transcript, expected, original_audio_hash = voice_cache[pair['audio']]
            with tempfile.TemporaryDirectory(prefix='pair_'+pair['id']+'_',dir=scratch) as work:
                work = Path(work)
                joined = compose(pair['hook_folder'],pair['recipe_folder'],work/'joined')
                frames = decode_analysis_frames(config['ffmpeg'],joined['final'])
                target = math.ceil(transcript['audio_duration']*24)
                _, plan = hook_recipe_plan(frames,target,joined['sha256'],3,2,manifest['long_voice'])
                style = pair['style']
                job = dict(id=pair['id']+'_'+Path(pair['audio']).stem.lower()+'_'+STYLES[style]['name'],
                           source=joined['final'],style=style,clips=plan['clips'],cut_policy=plan['policy'])
                args = SimpleNamespace(runtime=str(work/'render'),output=str(output),audio=str(normalized),
                                       ffmpeg=config['ffmpeg'],encoder=config['encoder'],fps=24)
                report = run_job(job,args,transcript,expected)
                if sha(pair['audio']) != original_audio_hash:
                    raise ValueError('Original narration changed during render.')
                report.update(pair_id=pair['id'],hook_folder=pair['hook_folder'],recipe_folder=pair['recipe_folder'],
                              visual_reviewed=False,quality_regeneration=False,source_hook_sha256=joined['hook_sha256'],
                              source_recipe_sha256=joined['recipe_sha256'])
                bridge.atomic(receipt_path,report)
                return report
        futures = {}
        attempted = set()
        with ThreadPoolExecutor(max_workers=2) as pool:
            while True:
                for key, future in list(futures.items()):
                    if not future.done():
                        continue
                    try:
                        result = future.result()
                        print('DELIVERED '+result['pair_id']+' '+result['output'],flush=True)
                    except Exception as error:
                        bridge.atomic(root/'edit_errors'/(key+'.json'),dict(id=key,error=str(error)))
                        print('ERROR '+key+' '+str(error),flush=True)
                    del futures[key]
                try:
                    ready = load(root/'ready_edits.json',[])
                except PermissionError as error:
                    if os.name != 'nt':
                        raise
                    # Windows can briefly deny opening the controller's atomic
                    # replacement. Keep completed receipts and running renders;
                    # retry reading on the next poll, never use an empty queue.
                    bridge.atomic(root/'editor_progress.json',dict(
                        completed=len(list((root/'edit_receipts').glob('*.json'))),
                        active=len(futures),errors=len(list((root/'edit_errors').glob('*.json'))),
                        waiting_for_ready_manifest=True,read_error=str(error)))
                    print('WAIT ready_edits: '+str(error),flush=True)
                    time.sleep(2)
                    continue
                for pair in ready:
                    key = pair['id']
                    if len(futures) >= 2:
                        break
                    if key in attempted:
                        continue
                    receipt = load(root/'edit_receipts'/(key+'.json'),None)
                    if receipt:
                        if not Path(receipt['output']).is_file() or sha(receipt['output']) != receipt['output_sha256']:
                            raise ValueError('Previously delivered output missing/changed: '+key)
                        attempted.add(key)
                        continue
                    if load(root/'edit_errors'/(key+'.json'),None):
                        attempted.add(key)
                        continue
                    attempted.add(key)
                    futures[key] = pool.submit(render,pair)
                completed = len(list((root/'edit_receipts').glob('*.json')))
                bridge.atomic(root/'editor_progress.json',dict(completed=completed,active=len(futures),errors=len(list((root/'edit_errors').glob('*.json')))))
                if completed == target or (not a.watch and not futures):
                    print('COMPLETED '+str(completed)+'/'+str(target),flush=True)
                    return
                time.sleep(2)


if __name__ == '__main__':
    main()
