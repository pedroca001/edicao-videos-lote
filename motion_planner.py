"""Per-source motion candidates and reviewed edit budgets, on normalized 24fps frames.

A small motion score is evidence for a candidate, never proof of a completed gesture.
"""
import hashlib
import math
from pathlib import Path
import subprocess

FPS = 24
WIDTH, HEIGHT = 144, 256
POLICY = 'foreground_rest_v1'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def decode_analysis_frames(ffmpeg, source):
    import numpy as np
    result = subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-i', str(source),
                             '-an', '-vf', f'fps={FPS},scale={WIDTH}:{HEIGHT}:flags=area,format=gray',
                             '-f', 'rawvideo', '-'], check=True, capture_output=True)
    size = WIDTH*HEIGHT
    if not result.stdout or len(result.stdout) % size:
        raise ValueError('Fonte sem frames completos para analise.')
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(-1, HEIGHT, WIDTH)


def foreground_scores(frames):
    """6fps candidates; tiles in products/hands/bowl ROI suppress upper-background motion."""
    import numpy as np
    samples = frames[::4, 96:248, 8:136].astype(np.float32)
    delta = samples[1:] - samples[:-1]
    # Correct approximately uniform illumination changes, not local object changes.
    delta -= np.median(delta, axis=(1,2))[:,None,None]
    delta = np.abs(delta)/255
    tiles = [delta[:, y:y+38, x:x+32].mean(axis=(1,2))
             for y in range(0,152,38) for x in range(0,128,32)]
    return np.quantile(np.stack(tiles, axis=1), .90, axis=1)


def pose_distance(a, b):
    import numpy as np
    delta = a[96:248, 8:136].astype(np.float32)-b[96:248, 8:136].astype(np.float32)
    delta -= np.median(delta)
    return float(np.abs(delta).mean()/255)


def region_priority(start, end, source_frames):
    # Stage boundaries are search regions, never fixed cuts.
    center = (start+end)/2
    distance = min(abs(center-s*FPS) for s in (10,20,30))
    if any(start < (s+2)*FPS and end > (s-2)*FPS for s in (10,20,30)):
        return 0, distance, 'emenda_de_etapas'
    if start < 3*FPS or end > source_frames-3*FPS:
        return 2, distance, 'pose_inicial_ou_final'
    return 1, distance, 'repouso_dentro_da_etapa'


def analyze_frames(frames, source_sha256='synthetic'):
    import numpy as np
    scores = foreground_scores(frames)
    # Relative calibration has absolute bounds: an always-moving clip must not
    # magically acquire "pauses" just because it has a lowest quartile.
    threshold = float(min(.018, max(.0025, np.quantile(scores,.25)*.80))) if len(scores) else .0025
    candidates = []
    first = None
    quiet = list(scores <= threshold)+[False]
    for i, is_quiet in enumerate(quiet):
        if is_quiet and first is None:
            first = i
        elif not is_quiet and first is not None:
            # 0.5s sustained rest, with 4-frame handles at both ends. Always
            # preserve the first second and the last 1.5s presentation.
            raw_start, raw_end = first*4, i*4
            start, end = max(FPS, raw_start+4), min(len(frames)-36, raw_end-4)
            if raw_end-raw_start >= 12 and end-start >= 4:
                distance = pose_distance(frames[start], frames[end])
                if distance <= .065:
                    priority, seam_distance, region = region_priority(start,end,len(frames))
                    candidates.append(dict(start_frame=start, end_frame=end, kind='pause',
                        region=region, priority=priority, seam_distance=seam_distance,
                        motion_score=float(np.max(scores[first:i])), pose_distance=distance,
                        confidence='heuristic_requires_visual_review', action='a_confirmar',
                        reason='Baixa mudanca sustentada no primeiro plano; conferir gesto e objetos.'))
            first = None
    candidates.sort(key=lambda c:(c['priority'],c['pose_distance'],c['seam_distance']))
    return dict(policy=POLICY, fps=FPS, source_sha256=source_sha256, source_frames=len(frames),
                threshold=threshold, candidates=candidates,
                candidate_seconds=sum(c['end_frame']-c['start_frame'] for c in candidates)/FPS)


def analyze_source(ffmpeg, source):
    frames = decode_analysis_frames(ffmpeg,source)
    return analyze_frames(frames,digest(source))


def _validate_regions(analysis, review):
    n = analysis['source_frames']
    if review.get('source_sha256') != analysis['source_sha256']:
        raise ValueError('A revisao pertence a outra fonte. Reanalise este video.')
    if review.get('fps') != FPS or review.get('source_frames') != n:
        raise ValueError('Revisao com timeline diferente da fonte normalizada.')
    regions = []
    for row in review.get('regions',[]):
        a,b = row['start_frame'],row['end_frame']
        if not isinstance(a,int) or not isinstance(b,int) or not 0 <= a < b <= n:
            raise ValueError('Intervalo de revisao invalido.')
        if row.get('kind') not in ('pause','repetition','speed','protect','exception'):
            raise ValueError('Tipo de intervalo invalido.')
        if not row.get('reason') or not row.get('action') or row.get('verified') is not True:
            raise ValueError('Registrar acao, motivo e verificacao visual de cada intervalo.')
        if row['kind'] != 'protect' and (a < FPS or b > n-36):
            raise ValueError('Preserve 1s inicial e 1,5s de apresentacao final.')
        regions.append(dict(row))
    regions.sort(key=lambda r:r['start_frame'])
    if any(a['end_frame'] > b['start_frame'] for a,b in zip(regions,regions[1:])):
        raise ValueError('Intervalos revisados nao podem se sobrepor.')
    return regions


def plan_from_review(analysis,target_frames,review):
    """Allocate only visually classified regions. Explicit shortage, no forced cuts."""
    return allocate_regions(analysis, target_frames, _validate_regions(analysis, review))


def allocate_regions(analysis, target_frames, regions, policy=POLICY, endpoint_review=True):
    """Internal allocator. Callers own evidence validation; never invent visual approval."""
    n=analysis['source_frames']
    if not isinstance(target_frames,int) or not 1 <= target_frames <= n:
        raise ValueError('Narracao deve ter entre um frame e a duracao da fonte.')
    remaining=n-target_frames
    removals=[]; speeds=[]
    def ranking(r):
        rank,dist,_=region_priority(r['start_frame'],r['end_frame'],n)
        category = rank if r['kind']=='pause' else {'repetition':3,'speed':4,'exception':5}.get(r['kind'],99)
        return category,dist
    for r in sorted(regions,key=ranking):
        if not remaining or r['kind']=='protect':continue
        a,b=r['start_frame'],r['end_frame'];length=b-a
        if r['kind']=='speed':
            max_speed=float(r.get('max_speed',1.15))
            if not 1 < max_speed <= 1.20:
                raise ValueError('Aceleracao visual seletiva limitada a 1,20x.')
            saved=min(remaining,length-math.ceil(length/max_speed))
            if saved:
                speeds.append(dict(r,output_frames=length-saved,saved_frames=saved))
                remaining-=saved
        else:
            amount=min(remaining,length)
            # Center a partial removal inside an already reviewed idle/cyclic region.
            start=a+(length-amount)//2
            removals.append(dict(r,start_frame=start,end_frame=start+amount,removed_frames=amount))
            remaining-=amount
    report=dict(policy=policy,source_sha256=analysis['source_sha256'],fps=FPS,
                source_frames=n,target_frames=target_frames,removed=removals,speed_adjustments=speeds,
                missing_frames=remaining,missing_seconds=remaining/FPS,
                requires_endpoint_review=endpoint_review,transitions='hard_cut',clips=[])
    if remaining:
        return report
    removals.sort(key=lambda r:r['start_frame'])
    boundaries=sorted({0,n,*[v for r in removals+speeds for v in (r['start_frame'],r['end_frame'])]})
    clips=[]
    for a,b in zip(boundaries,boundaries[1:]):
        if any(r['start_frame'] <= a and b <= r['end_frame'] for r in removals):continue
        speed=next((r for r in speeds if r['start_frame']==a and r['end_frame']==b),None)
        clip=dict(start_frame=a,end_frame=b,transition_frames=0,zoom=1.0)
        if speed:clip['output_frames']=speed['output_frames']
        if clips and not speed and 'output_frames' not in clips[-1] and clips[-1]['end_frame']==a:
            clips[-1]['end_frame']=b
        else:clips.append(clip)
    from edit_batch import timeline_frames
    assert timeline_frames(clips)==target_frames
    report['clips']=clips
    return report


def candidate_review(analysis):
    """Draft for a reviewer. Deliberately not marked verified."""
    return dict(source_sha256=analysis['source_sha256'],fps=FPS,source_frames=analysis['source_frames'],
                regions=[dict(c,verified=False) for c in analysis['candidates']])
