"""Explicit recipe ellipses for short narration, only after user authorization.

Stage timing and motion are local heuristics, not ingredient recognition.
The standard rest-preserving recipe profile never calls this planner.
"""
import numpy as np
from motion_planner import FPS, foreground_scores, pose_distance
from edit_batch import timeline_frames

POLICY = 'recipe_condensed_authorized_v1'


def hook_recipe_plan(frames, target_frames, source_sha256='synthetic',
                     hook_seconds=6, recipe_advance_seconds=0, long_voice=None):
    """Known 6s hook + four 8s recipe scenes. Keep the complete hook at 1x.

    Short voices require explicit recipe ellipses, never a silent rest claim.
    All five ingredient/presentation excerpts remain chronological at 1x.
    """
    n = len(frames)
    if not 910 <= n <= 915:
        raise ValueError('Perfil requer gancho6s + receita32s, aproximadamente38s.')
    if (hook_seconds,recipe_advance_seconds) not in ((6,0),(3,2)):
        raise ValueError('Abertura deve ser completa6s ou rapida3s/receita+2s.')
    hook_frames=hook_seconds*FPS
    recipe_start=(6+recipe_advance_seconds)*FPS
    minimum = np.array([hook_frames, 36, 60, 48, 48, 108], dtype=int)
    capacity = np.array([hook_frames, 336-recipe_start, 192, 96, 96, n-720], dtype=int)
    available=int(capacity.sum())
    if not isinstance(target_frames,int) or target_frames<int(minimum.sum()):
        raise ValueError('Voz curta demais para gancho e etapas protegidas.')
    if target_frames>available and long_voice not in ('slow_recipe','repeat_presentation'):
        raise ValueError('Voz maior que a imagem apos abertura rapida; escolher alongamento explicitamente.')
    if long_voice=='slow_recipe' and (available-hook_frames)/(target_frames-hook_frames)<.8:
        raise ValueError('Desaceleracao da receita ultrapassa limite0,80x.')
    visual_target=min(target_frames,available)
    lengths = minimum.copy()
    weights = [1, 1, 2, 1.5, 1.5, 1]
    while int(lengths.sum()) < visual_target:
        i = min((i for i in range(1,6) if lengths[i] < capacity[i]),
                key=lambda i: (lengths[i]-minimum[i])/weights[i])
        lengths[i] += 1
    scores = foreground_scores(frames)
    clips = [dict(start_frame=0,end_frame=hook_frames,recipe_stage='gancho_completo' if hook_seconds==6 else 'gancho_curto',zoom=1.,transition_frames=0),
             dict(start_frame=recipe_start,end_frame=recipe_start+int(lengths[1]),recipe_stage='mexida_inicial',zoom=1.,transition_frames=0)]
    for length,lo,hi,center,stage in zip(lengths[2:5],[14,22,26],[22,26,30],
                                        [17.25,23.75,27.5],['bicarbonato','mel','limao']):
        length = int(length)
        prior = max(lo*FPS,min(round(center*FPS-length/2),hi*FPS-length))
        starts = [lo*FPS] if stage == 'mel' else range(max(lo*FPS,prior-18),min(hi*FPS-length,prior+18)+1,2)
        a = max(starts,key=lambda a:float(np.mean(scores[a//4:(a+length+3)//4]))-.012*((a+length/2)/FPS-center)**2)
        clips.append(dict(start_frame=a,end_frame=a+length,recipe_stage=stage,zoom=1.,transition_frames=0))
    clips.append(dict(start_frame=n-int(lengths[5]),end_frame=n,
                      recipe_stage='mexida_pegada_apresentacao_final',zoom=1.,transition_frames=0))
    if any(a['end_frame'] > b['start_frame'] for a,b in zip(clips,clips[1:])):
        raise ValueError('Resumo invade outra etapa.')
    removed = [dict(start_frame=a['end_frame'],end_frame=b['start_frame'],kind='exception',
                    verified=False,endpoint_cost=pose_distance(frames[a['end_frame']-1],frames[b['start_frame']]),
                    reason='Elipse de receita para voz curta; nao representa repouso comprovado.')
               for a,b in zip(clips,clips[1:]) if a['end_frame'] < b['start_frame']]
    speeds=[]
    if target_frames>available and long_voice=='slow_recipe':
        recipe_lengths=np.array([c['end_frame']-c['start_frame'] for c in clips[1:]],dtype=int)
        exact=recipe_lengths*(target_frames-hook_frames)/int(recipe_lengths.sum())
        output_lengths=np.floor(exact).astype(int)
        for i in np.argsort(-(exact-output_lengths),kind='stable')[:target_frames-hook_frames-int(output_lengths.sum())]:output_lengths[i]+=1
        for clip,output in zip(clips[1:],output_lengths):
            clip.update(output_frames=int(output),authorized_slowdown=True)
            speeds.append(dict(start_frame=clip['start_frame'],end_frame=clip['end_frame'],output_frames=int(output),
                               speed=(clip['end_frame']-clip['start_frame'])/int(output),reason='Desaceleracao da receita escolhida para preservar a voz.'))
    elif target_frames>available and long_voice=='repeat_presentation':
        remaining=target_frames-available
        # Explicitly chosen replay, separate from chronological recipe excerpts.
        while remaining:
            amount=min(remaining,108)
            clips.append(dict(start_frame=n-amount,end_frame=n,recipe_stage='repeticao_final_autorizada',
                              authorized_repeat=True,zoom=1.,transition_frames=0))
            remaining-=amount
    assert timeline_frames(clips) == target_frames
    profile='flow_hook_receita' if hook_seconds==6 else 'flow_hook_receita_rapida'
    return dict(source_frames=n,fps=FPS,source_sha256=source_sha256),dict(
        policy='flow_hook_recipe_v1' if hook_seconds==6 else 'flow_hook_recipe_v2',profile=profile,source_frames=n,fps=FPS,
        source_sha256=source_sha256,target_frames=target_frames,status='ready',missing_frames=0,
        clips=clips,removed=removed,speed_adjustments=speeds,visual_reviewed=False,
        hook_seconds=hook_seconds,recipe_advance_seconds=recipe_advance_seconds,long_voice=long_voice,
        requires_user_authorization=True,ingredient_recognition=False,
        risk_score=round(sum(r['endpoint_cost'] for r in removed),4))


def condensed_recipe_plan(frames, target_frames, source_sha256='synthetic', profile='vids_receita_resumida'):
    if profile not in ('vids_receita_resumida','flow_receita_resumida'):raise ValueError('Perfil de resumo desconhecido.')
    flow = profile == 'flow_receita_resumida'
    n = len(frames)
    if not isinstance(target_frames, int) or not 1 <= target_frames <= n:
        raise ValueError('Narracao deve caber na fonte.')
    analysis = dict(source_frames=n, fps=FPS, source_sha256=source_sha256)
    report = dict(policy='flow_recipe_condensed_authorized_v1' if flow else POLICY, source_sha256=source_sha256, source_frames=n,
                  target_frames=target_frames, fps=FPS, profile=profile,
                  visual_reviewed=False, requires_endpoint_review=False,
                  requires_user_authorization=True, ingredient_recognition=False,
                  transitions='hard_cut', clips=[], removed=[], speed_adjustments=[])
    minimum = np.array([48, 60, 48, 48, 108] if flow else [48, 60, 54, 54, 108], dtype=int)
    source_min, source_max, target_max = (31,33,31) if flow else (39,41,24)
    if not source_min*FPS <= n <= source_max*FPS or target_frames < int(minimum.sum()) or target_frames > target_max*FPS:
        report.update(status='exception', missing_frames=max(1, int(minimum.sum())-target_frames),
                      reason='Resumo Flow recebe receitas31–33s e narracao13–31s.' if flow else 'Resumo recebe receitas39–41s e narracao13,5–24s.')
        return analysis, report
    # Five chronological shots: initial mix, bicarbonate, honey, lemon, final
    # mix/lift/presentation. The last shot is continuous through the final frame.
    weights = np.array([1., 2., 1.5, 1.5, 1.])
    exact = (target_frames-int(minimum.sum()))*weights/weights.sum()
    additions = np.floor(exact).astype(int)
    for i in np.argsort(-(exact-additions), kind='stable')[:target_frames-int(minimum.sum())-int(additions.sum())]:
        additions[i] += 1
    lengths = minimum+additions
    if flow and target_frames > 480:
        capacities = np.array([192,192,96,96,n-576], dtype=int)
        lengths = minimum.copy()
        while int(lengths.sum()) < target_frames:
            choices = [i for i in range(5) if lengths[i] < capacities[i]]
            i = min(choices, key=lambda i: (lengths[i]-minimum[i])/weights[i])
            lengths[i] += 1
    scores = foreground_scores(frames)
    clips = [dict(start_frame=0, end_frame=int(lengths[0]), transition_frames=0, zoom=1.,
                  recipe_stage='mexida_inicial')]
    # Restrict motion adaptation to a small neighborhood of each known gesture.
    # A reach with high motion must not move the shot away from the addition.
    centers = [11.25,17.75,21.5] if flow else [15.5,23.65,27.5]
    lows = [8.,16.,20.] if flow else [11.75,21.,25.75]
    highs = [16.,20.,24.] if flow else [19.75,25.75,30.75]
    for length, center, lo, hi, stage in zip(lengths[1:4],centers,lows,highs,['bicarbonato','mel','limao']):
        length = int(length)
        prior = int(round(center*FPS-length/2))
        prior = max(round(lo*FPS), min(prior, round(hi*FPS)-length))
        starts = range(max(round(lo*FPS), prior-18), min(round(hi*FPS)-length, prior+18)+1, 2)
        # Flow's third scene begins with the honey addition. Keep its opening,
        # rather than allowing motion from the later lemon reach to replace it.
        if flow and stage == 'mel':starts = [round(lo*FPS)]
        candidates = []
        for a in starts:
            b = a+length
            if a < clips[-1]['end_frame']:
                continue
            activity = float(np.mean(scores[a//4:min(len(scores),(b+3)//4)]))
            prior_distance = abs((a+b)/2/FPS-center)
            candidates.append((activity-.012*prior_distance**2, -prior_distance, -a, a, b))
        if not candidates:
            raise ValueError('Orcamento de resumo causa sobreposicao de etapas.')
        _, _, _, a, b = max(candidates)
        clips.append(dict(start_frame=a, end_frame=b, transition_frames=0, zoom=1., recipe_stage=stage))
    clips.append(dict(start_frame=n-int(lengths[4]), end_frame=n, transition_frames=0,
                      zoom=1., recipe_stage='mexida_pegada_apresentacao_final'))
    if any(a['end_frame'] > b['start_frame'] for a,b in zip(clips, clips[1:])):
        raise ValueError('Etapas resumidas se sobrepoem.')
    removed = []
    for left, right in zip(clips, clips[1:]):
        a, b = left['end_frame'], right['start_frame']
        if a != b:
            removed.append(dict(start_frame=a, end_frame=b, removed_frames=b-a,
                kind='exception', action='elipse_autorizada_entre_trechos_de_gestos', verified=False,
                reason='Montagem resumida autorizada; pode omitir alcance/retorno/miolo de gesto.',
                endpoint_cost=pose_distance(frames[a-1],frames[b])))
    assert timeline_frames(clips) == target_frames
    report.update(status='ready', missing_frames=0, missing_seconds=0, reason='', clips=clips,
                  removed=removed, risk_score=round(sum(r['endpoint_cost'] for r in removed),4))
    return analysis, report


def condensed_scenes_plan(frames, target_frames, source_sha256='synthetic'):
    """Opt-in summary of four 8s scenes, without assuming recipe ingredients."""
    n=len(frames)
    if not 31*FPS <= n <= 33*FPS or not 324 <= target_frames <= min(n,31*FPS):
        raise ValueError('Resumo de cenas recebe Flow31–33s e voz13,5–31s.')
    minimum=np.array([72,72,72,108],dtype=int)
    capacity=np.array([192,192,192,n-576],dtype=int)
    lengths=minimum.copy()
    while int(lengths.sum()) < target_frames:
        i=min((i for i in range(4) if lengths[i]<capacity[i]),key=lambda i: lengths[i]-minimum[i])
        lengths[i]+=1
    scores=foreground_scores(frames)
    clips=[dict(start_frame=0,end_frame=int(lengths[0]),zoom=1.,transition_frames=0)]
    for i in (1,2):
        length=int(lengths[i]);lo=i*192;hi=(i+1)*192
        # Keep the most active contiguous excerpt inside each real scene.
        a=max(range(lo,hi-length+1),key=lambda a:float(np.mean(scores[a//4:(a+length+3)//4])))
        clips.append(dict(start_frame=a,end_frame=a+length,zoom=1.,transition_frames=0))
    clips.append(dict(start_frame=n-int(lengths[3]),end_frame=n,zoom=1.,transition_frames=0))
    removed=[dict(start_frame=a['end_frame'],end_frame=b['start_frame'],kind='exception',verified=False)
             for a,b in zip(clips,clips[1:]) if a['end_frame']<b['start_frame']]
    assert timeline_frames(clips)==target_frames
    return dict(source_frames=n,fps=FPS,source_sha256=source_sha256),dict(
        policy='flow_scenes_condensed_authorized_v1',profile='flow_cenas_resumidas',status='ready',
        source_sha256=source_sha256,source_frames=n,target_frames=target_frames,clips=clips,
        removed=removed,speed_adjustments=[],missing_frames=0,visual_reviewed=False,
        requires_user_authorization=True,ingredient_recognition=False)
