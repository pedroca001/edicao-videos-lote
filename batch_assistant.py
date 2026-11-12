"""Portable Mac assistant: select inputs, plan short-voice edits, run verified pipeline."""
import argparse
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time

from edit_batch import STYLES
from motion_planner import analyze_source
from cut_review import interactive_review, validate_final_review
from auto_planner import analyze_and_plan, sample_jobs, PROFILES


def natural_key(path):
    return tuple((1, int(x)) if x.isdigit() else (0, x.lower())
                 for x in re.split(r'(\d+)', path.name))


def balanced_styles(count, rng):
    ids = tuple(STYLES)
    remaining = Counter({i: count // len(ids) for i in ids})
    for i in rng.sample(ids, count % len(ids)):
        remaining[i] += 1
    # Highest remaining count prevents a stranded repeated final style. Random ties.
    result = []
    while len(result) < count:
        candidates = [i for i in remaining if remaining[i] and (not result or i != result[-1])]
        if not candidates:
            raise ValueError('Nao foi possivel distribuir os estilos.')
        top = max(remaining[i] for i in candidates)
        choice = rng.choice([i for i in candidates if remaining[i] == top])
        result.append(choice)
        remaining[choice] -= 1
    return result


def inspect_video(ffmpeg, path):
    result = subprocess.run([ffmpeg, '-hide_banner', '-i', str(path)], capture_output=True, text=True)
    text = result.stderr
    duration = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', text)
    line = next((line for line in text.splitlines() if 'Video:' in line), '')
    dimensions = re.search(r'\b(\d{2,5})x(\d{2,5})\b', line)
    if not duration or not dimensions:
        raise ValueError(f'Nao foi possivel ler o video: {path.name}')
    if tuple(map(int, dimensions.groups())) != (720, 1280):
        raise ValueError(f'{path.name}: esta versao recebe videos verticais 720x1280, como os exports do Vids.')
    h, m, s = map(float, duration.groups())
    return math.floor((h*3600+m*60+s)*24 + .001)


def validate_allocations(total, audio_specs):
    counts, used = [], 0
    for index, (_, count) in enumerate(audio_specs):
        if count == 'restante' and index == len(audio_specs)-1:
            n = total - used
        else:
            try:
                n = int(count)
            except ValueError:
                raise ValueError('Use uma quantidade inteira ou "restante" no ultimo audio.')
        if n < 1:
            raise ValueError('Cada audio precisa receber pelo menos um video.')
        counts.append(n)
        used += n
    if used != total:
        raise ValueError(f'Foram encontrados {total} videos, mas as quantidades somam {used}.')
    return counts


def run_batch(config, folder, audio_specs, output=None, workers=2, seed=None, cut_reviews=None, no_ui=False,
              review_mode='auto', review_exceptions=False, profile='vids_receita', sample_size=3,
              plan_only=False):
    started = time.monotonic()
    if review_mode not in ('auto','manual') or profile not in PROFILES or not 0 <= sample_size <= 10:
        raise ValueError('Modo, perfil ou tamanho de amostra invalido.')
    folder = Path(folder).expanduser().resolve()
    videos = sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == '.mp4'
                     and not p.name.startswith('.')], key=natural_key)
    if not videos:
        raise ValueError('Nenhum MP4 encontrado diretamente na pasta escolhida.')
    counts = validate_allocations(len(videos), audio_specs)
    audios = [Path(a).expanduser().resolve() for a, _ in audio_specs]
    if any(not p.is_file() for p in audios):
        raise ValueError('Um dos arquivos de audio nao existe.')
    if set(audios) & set(videos):
        raise ValueError('Guarde os audios fora da pasta de videos para nao conta-los como fontes.')
    output = Path(output).expanduser().resolve() if output else folder.parent / ('videos_editados_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if output.exists():
        raise ValueError('A pasta de saida ja existe. Escolha uma pasta nova para preservar os arquivos.')
    ffmpeg = config['ffmpeg']
    print(f'Conferindo {len(videos)} videos...', flush=True)
    for p in videos:
        inspect_video(ffmpeg, p)
    cut_reviews = cut_reviews or {}
    styles = balanced_styles(len(videos), random.Random(seed))
    code = Path(__file__).resolve().parent
    env = __import__('os').environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1')
    exceptions, records = [], []
    planning_seconds = 0.0
    with tempfile.TemporaryDirectory(prefix='editor_batch_') as temp:
        scratch = Path(temp)
        command = [sys.executable, '-B', str(code/'run_pipeline.py'), '--ffmpeg', ffmpeg,
                   '--output', str(output), '--workers', str(workers), '--model', config['model'],
                   '--backend', config['backend'], '--encoder', config['encoder']]
        offset = 0
        for index, (audio, count) in enumerate(zip(audios, counts), 1):
            # Preserve AAC packets when possible. Other formats are normalized once.
            info = subprocess.run([ffmpeg, '-hide_banner', '-i', str(audio)], capture_output=True, text=True).stderr
            if not re.search(r'Audio: aac\b', info):
                normalized = scratch / f'audio_{index}.m4a'
                subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-i', str(audio), '-map', '0:a:0',
                                '-vn', '-c:a', 'aac', '-b:a', '192k', str(normalized)], check=True)
                audio = normalized
            raw = subprocess.run([ffmpeg, '-v', 'error', '-i', str(audio), '-vn', '-ac', '1', '-ar',
                                  '16000', '-f', 'f32le', '-'], capture_output=True, check=True).stdout
            target = math.ceil(len(raw)/64000*24)
            if not target:
                raise ValueError(f'Audio {index} vazio.')
            jobs = []
            for j in range(offset, offset+count):
                slug = re.sub(r'[^a-z0-9_]+', '_', videos[j].stem.lower()).strip('_')[:65]
                name = f'{j+1:03d}_{slug}_audio{index}_{STYLES[styles[j]]["name"]}'
                print(f'Analisando movimento {j+1}/{len(videos)}: {videos[j].name}', flush=True)
                tick = time.monotonic()
                try:
                    if review_mode == 'auto':
                        analysis, report = analyze_and_plan(ffmpeg,videos[j],target,profile)
                    else:
                        analysis = analyze_source(ffmpeg,videos[j])
                        report = {'missing_frames': analysis['source_frames']-target}
                    if target > analysis['source_frames']:
                        raise ValueError('Narracao maior que a fonte.')
                    review = cut_reviews.get(analysis['source_sha256'])
                    needs_review = review_mode == 'manual' or (report['missing_frames'] and review_exceptions)
                    if review is None and needs_review and not no_ui and not plan_only:
                        review = interactive_review(ffmpeg,videos[j],analysis,target)
                    if review is not None:
                        report = validate_final_review(analysis,target,review)
                    elif review_mode == 'manual':
                        raise ValueError('Revisao manual ausente; forneca --cut-review ou habilite a interface.')
                    if report['missing_frames']:
                        exceptions.append(dict(source=videos[j].name,audio=index,
                            reason=report.get('reason','Orcamento insuficiente.'),
                            missing_seconds=report['missing_frames']/24))
                        print(f'EXCECAO: {videos[j].name}: faltam {report["missing_frames"]/24:.2f}s removiveis.',flush=True)
                        continue
                    clips = report['clips']
                except (ValueError, subprocess.CalledProcessError) as error:
                    exceptions.append(dict(source=videos[j].name,audio=index,reason=str(error)))
                    print(f'EXCECAO: {videos[j].name}: {error}',flush=True)
                    continue
                finally:
                    planning_seconds += time.monotonic()-tick
                (scratch/f'cuts_{j+1}.json').write_text(json.dumps(report,indent=2))
                jobs.append(dict(id=name, source=str(videos[j]), style=styles[j], clips=clips,
                                 cut_policy=report['policy']))
                records.append(dict(source=videos[j].name,output=name+'.mp4',audio=index,
                                    style=STYLES[styles[j]]['name'],risk_score=report.get('risk_score',0)))
            if jobs:
                plan = scratch / f'plan_{index}.json'
                plan.write_text(json.dumps(jobs))
                command += ['--task', str(audio), str(plan)]
            offset += count
        print(f'Distribuicao dos audios: {counts}. Saida: {output}', flush=True)
        if records and not plan_only:
            subprocess.run(command, env=env, check=True)
    finals = [p for p in output.glob('*.mp4') if not p.name.startswith('.')]
    if not plan_only and len(finals) != len(records):
        raise RuntimeError('A contagem final difere dos planos aprovados pelas regras.')
    result = dict(output=str(output),inputs=len(videos),planned=len(records),completed=len(finals),
                  exceptions=exceptions,samples=sample_jobs(records,sample_size),plan_only=plan_only,
                  planning_seconds=round(planning_seconds,3),elapsed_seconds=round(time.monotonic()-started,3))
    print(f'{"PLANEJADO" if plan_only else "CONCLUIDO"}: {len(records) if plan_only else len(finals)}/{len(videos)}; '
          f'{len(exceptions)} excecoes. Nao houve revisao visual automatica pelo Codex.',flush=True)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    return result


def dialog(script, *args):
    result = subprocess.run(['/usr/bin/osascript', '-e', 'on run argv\n'+script+'\nend run', *map(str,args)],
                            capture_output=True, text=True)
    if result.returncode:
        if '-128' in result.stderr:
            raise KeyboardInterrupt
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def wizard(config):
    folder = dialog('return POSIX path of (choose folder with prompt "Escolha a pasta com os videos MP4 (720x1280)")')
    specs = []
    while True:
        audio = dialog('return POSIX path of (choose file with prompt "Escolha o audio '+str(len(specs)+1)+'")')
        count = dialog('return text returned of (display dialog "Quantos videos recebem este audio? Use restante para todos os que faltam." default answer "restante")')
        specs.append((audio, count))
        if count.strip().lower() == 'restante':
            break
        more = dialog('return button returned of (display dialog "Adicionar outro audio?" buttons {"Nao", "Sim"} default button "Sim")')
        if more == 'Nao':
            break
    specs = [(a,c.strip().lower()) for a,c in specs]
    result = run_batch(config, folder, specs)
    if result['completed']:
        subprocess.run(['/usr/bin/open', result['output']], check=True)
    details = '\n'.join(f'{r["source"]}: {r["reason"]}' for r in result['exceptions'][:5])
    dialog('display dialog (item 1 of argv) buttons {"OK"} default button "OK"',
           f'{result["completed"]}/{result["inputs"]} videos gerados. {len(result["exceptions"])} excecoes.\n'
           f'Saida: {result["output"]}\nConfira a amostra e a lista completa no Terminal.\n{details}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', default=str(Path(__file__).resolve().parent.parent/'config.json'))
    p.add_argument('--videos')
    p.add_argument('--audio', nargs=2, action='append', metavar=('ARQUIVO', 'QUANTIDADE'))
    p.add_argument('--output')
    p.add_argument('--workers', type=int, choices=range(1,5), default=2)
    p.add_argument('--seed', type=int)
    p.add_argument('--cut-review', help='JSON com revisoes por SHA256 da fonte, incluindo hash do plano aprovado.')
    p.add_argument('--no-ui', action='store_true', help='Nao abrir revisao manual no navegador.')
    p.add_argument('--review-mode', choices=['auto','manual'],default='auto')
    p.add_argument('--review-exceptions', action='store_true',help='Abrir revisao somente dos casos sem plano automatico.')
    p.add_argument('--profile', choices=PROFILES,default='vids_receita')
    p.add_argument('--sample-size', type=int,choices=range(11),default=3,help='Listar ate N saidas para inspecao visual opcional.')
    p.add_argument('--plan-only',action='store_true',help='Medir e listar planos/excecoes sem transcrever ou renderizar.')
    a = p.parse_args()
    config = json.loads(Path(a.config).read_text())
    if a.videos:
        if not a.audio:
            p.error('Informe --audio ARQUIVO QUANTIDADE pelo menos uma vez.')
        result = run_batch(config, a.videos, a.audio, a.output, a.workers, a.seed,
                  json.loads(Path(a.cut_review).read_text()) if a.cut_review else None, a.no_ui,
                  a.review_mode,a.review_exceptions,a.profile,a.sample_size,a.plan_only)
        if result['exceptions']:
            raise SystemExit(2)
    else:
        wizard(config)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nOperacao cancelada. Originais preservados.')
        raise SystemExit(130)
    except Exception as error:
        print(f'ERRO: {error}', file=sys.stderr)
        raise SystemExit(1)
