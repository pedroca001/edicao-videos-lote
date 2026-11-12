"""Local heuristic planning. Recipe timing is a prior, never semantic verification."""
import math
import numpy as np
from motion_planner import (FPS, analyze_frames, decode_analysis_frames, digest,
                            pose_distance, allocate_regions, region_priority)

POLICY = 'local_auto_v1'
PROFILES = ('vids_receita', 'conservative', 'vids_receita_resumida', 'flow_receita_resumida', 'flow_cenas_resumidas', 'flow_hook_receita', 'flow_hook_receita_rapida')


def recurrence_evidence(frames, a, b):
    """Require recurring foreground appearance throughout a known stirring window.

    Similar endpoints alone cannot approve an entire action. This remains a
    heuristic and is intentionally restricted to the recipe's stirring stages.
    """
    x = frames[a:b:4, 128:244:4, 24:120:4].astype(np.float32) / 255
    if len(x) < 18:
        return None
    distances = np.mean(np.abs(x[:, None] - x[None, :]), axis=(2, 3))
    indices = np.arange(len(x))
    lag = np.abs(indices[:, None] - indices[None, :])
    nearest = np.where((lag >= 3) & (lag <= 12), distances, np.inf).min(axis=1)
    spread = float(np.quantile(distances, .75))
    coverage = float(np.mean(nearest <= .045))
    ratio = float(np.median(nearest) / max(spread, .001))
    # Reject static poses, weak recurrence, and isolated high-change events.
    if spread < .008 or coverage < .90 or ratio > .68 or np.max(nearest) > .08:
        return None
    return dict(recurrence_coverage=coverage, recurrence_ratio=ratio)


def endpoint_cost(frames, a, b):
    """Compare actual adjacent retained frames plus two nearby poses, not time guesses."""
    if a < 4 or b + 3 >= len(frames):
        return float('inf')
    return max(pose_distance(frames[a-1+k], frames[b+k]) for k in (-3, 0, 3))


def _overlaps(a, b, regions):
    return any(a < r['end_frame'] and b > r['start_frame'] for r in regions)


def automatic_plan(frames, target_frames, source_sha256='synthetic', profile='vids_receita'):
    if profile not in PROFILES:
        raise ValueError('Perfil automatico desconhecido.')
    if profile == 'flow_hook_receita':
        from condensed_planner import hook_recipe_plan
        return hook_recipe_plan(frames, target_frames, source_sha256)
    if profile == 'flow_hook_receita_rapida':
        from condensed_planner import hook_recipe_plan
        return hook_recipe_plan(frames,target_frames,source_sha256,hook_seconds=3,recipe_advance_seconds=2)
    if profile == 'flow_cenas_resumidas':
        from condensed_planner import condensed_scenes_plan
        return condensed_scenes_plan(frames, target_frames, source_sha256)
    if profile in ('vids_receita_resumida','flow_receita_resumida'):
        from condensed_planner import condensed_recipe_plan
        return condensed_recipe_plan(frames, target_frames, source_sha256, profile)
    analysis = analyze_frames(frames, source_sha256)
    n = len(frames)
    if not isinstance(target_frames, int) or not 1 <= target_frames <= n:
        raise ValueError('Narracao deve caber na fonte.')
    regions = []
    remaining = n - target_frames
    recipe = profile == 'vids_receita'
    if recipe and not 39*FPS <= n <= 41*FPS and remaining:
        report = allocate_regions(analysis, target_frames, [], POLICY, False)
        report.update(status='exception', reason='Perfil de receita requer fonte de aproximadamente 40s.',
                      profile=profile, visual_reviewed=False)
        return analysis, report

    # Sustained rest first. Small interior pauses in ingredient stages are
    # ambiguous (a held bottle or a thin stream): leave these actions intact.
    for c in analysis['candidates']:
        if not remaining:
            break
        lo, hi = c['start_frame'], c['end_frame']
        if recipe and lo < 30*FPS and hi > 10*FPS and c['priority'] != 0:
            continue
        # Never remove more than 2s of a detected pose in recipe mode.
        amount = min(remaining, hi-lo, 2*FPS if recipe else hi-lo)
        if amount < 4:
            continue
        starts = range(lo, hi-amount+1, 2)
        a = min(starts, key=lambda s: endpoint_cost(frames, s, s+amount))
        b = a + amount
        cost = endpoint_cost(frames, a, b)
        if cost > .045:
            continue
        regions.append(dict(c, start_frame=a, end_frame=b, confidence='local_heuristic',
                            verified=False, endpoint_cost=cost,
                            reason='Repouso sustentado e poses proximas; sem verificacao semantica.'))
        remaining -= amount

    # The profile limits recurrence cuts to stirring, never pours or squeezing.
    # Preserve the start/stop handles and all of the final presentation region.
    if recipe:
        for lo, hi in ((FPS, 9*FPS), (int(30.75*FPS), int(35.5*FPS))):
            if remaining < 12:
                break
            # A late stop/lift can invalidate the entire window. Find a shorter
            # recurring subwindow instead of discarding all useful stirring.
            windows=[]
            for length in range(hi-lo,3*FPS-1,-12):
                for start in range(lo,hi-length+1,12):
                    evidence=recurrence_evidence(frames,start,start+length)
                    if evidence is not None:
                        windows.append((start,start+length,evidence))
                if windows:
                    break
            if not windows:
                continue
            candidates = []
            # Coarse length search with dense actual endpoint comparisons. Keep
            # the exact remaining budget as a candidate to avoid rounding loss.
            for start,end,evidence in windows:
                maximum = min(remaining, end-start)
                lengths = sorted({maximum, *range(12, maximum+1, 6)}, reverse=True)
                for amount in lengths:
                    found=False
                    for a in range(start,end-amount+1,4):
                        b=a+amount
                        if _overlaps(a,b,regions):
                            continue
                        cost=endpoint_cost(frames,a,b)
                        if cost <= .065:
                            candidates.append((amount,cost,a,b,evidence));found=True
                    if found:
                        break
            if candidates:
                amount,cost,a,b,evidence = min(candidates,key=lambda x:(-x[0],x[1]))
                regions.append(dict(start_frame=a,end_frame=b,kind='repetition',
                    action='mexida_prevista_no_perfil',reason='Recorrencia local dentro de etapa de mexida.',
                    confidence='local_heuristic',verified=False,endpoint_cost=cost,**evidence))
                remaining -= amount

    # Selective mild speed only after rest/repetition. Protect the first second,
    # final presentation. Speed preserves every source frame in sequence before
    # temporal resampling, including reaches, pours and stage transitions.
    windows = [(FPS,n-36)] if not recipe else [(FPS,240),(240,480),(480,720),(720,n-36)]
    free = []
    for lo,hi in windows:
        points = sorted({lo,hi,*[v for r in regions for v in (r['start_frame'],r['end_frame']) if lo<v<hi]})
        for a,b in zip(points,points[1:]):
            if b-a >= FPS and not _overlaps(a,b,regions):
                free.append((a,b))
    for a,b in sorted(free,key=lambda ab:ab[1]-ab[0],reverse=True):
        if not remaining:
            break
        saved = min(remaining,(b-a)-math.ceil((b-a)/1.20))
        if saved:
            regions.append(dict(start_frame=a,end_frame=b,kind='speed',max_speed=1.20,
                action='acao_continua',reason='Preservar acao continua com velocidade visual ate 1,20x.',
                confidence='local_rule',verified=False))
            remaining -= saved
    report = allocate_regions(analysis,target_frames,regions,POLICY,False)
    report.update(status='exception' if report['missing_frames'] else 'ready',profile=profile,
                  visual_reviewed=False,reason='Duracao insuficiente dentro das regras locais.' if report['missing_frames'] else '',
                  risk_score=round(sum(r.get('endpoint_cost',0) for r in report['removed']) +
                                   .1*len(report['speed_adjustments']),4))
    return analysis,report


def analyze_and_plan(ffmpeg, source, target_frames, profile='vids_receita'):
    return automatic_plan(decode_analysis_frames(ffmpeg,source),target_frames,digest(source),profile)


def sample_jobs(records, maximum=3):
    """Bound visual workload: representative audio/style cases, highest-risk ties."""
    selected=[]
    while len(selected)<min(maximum,len(records)):
        remaining=[r for r in records if r not in selected]
        audios={r['audio'] for r in selected};styles={r['style'] for r in selected}
        selected.append(max(remaining,key=lambda r:(2*(r['audio'] not in audios)+(r['style'] not in styles),r['risk_score'])))
    return selected
