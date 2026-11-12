import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from auto_planner import automatic_plan, recurrence_evidence, sample_jobs
from batch_assistant import run_batch
from edit_batch import timeline_frames


class AutomaticContracts(unittest.TestCase):
    def test_default_can_finish_without_any_visual_approval(self):
        frames=np.zeros((960,256,144),dtype=np.uint8)
        _,p=automatic_plan(frames,936)
        self.assertEqual(p['status'],'ready')
        self.assertEqual(timeline_frames(p['clips']),936)
        self.assertFalse(p['visual_reviewed'])
        self.assertFalse(p['requires_endpoint_review'])
        self.assertTrue(all(r['verified'] is False for r in p['removed']))
        self.assertEqual(p['clips'][0]['start_frame'],0)
        self.assertEqual(p['clips'][-1]['end_frame'],960)

    def test_unknown_recipe_duration_routes_to_exception(self):
        frames=np.zeros((480,256,144),dtype=np.uint8)
        _,p=automatic_plan(frames,450)
        self.assertEqual(p['status'],'exception')
        self.assertEqual(p['clips'],[])
        _,p=automatic_plan(frames,450,profile='conservative')
        self.assertEqual(timeline_frames(p['clips']),450)

    def test_shortage_never_forces_a_cut_or_exceeds_speed_limit(self):
        rng=np.random.default_rng(17)
        frames=rng.integers(0,255,(960,256,144),dtype=np.uint8)
        _,p=automatic_plan(frames,570)
        self.assertEqual(p['status'],'exception')
        self.assertGreater(p['missing_frames'],0)
        self.assertEqual(p['clips'],[])
        self.assertFalse(p['removed'])
        for s in p['speed_adjustments']:
            self.assertLessEqual((s['end_frame']-s['start_frame'])/s['output_frames'],1.20)

    def test_endpoint_return_alone_does_not_prove_recurrence(self):
        rng=np.random.default_rng(41)
        frames=rng.integers(0,255,(192,256,144),dtype=np.uint8)
        frames[-1]=frames[0]
        self.assertIsNone(recurrence_evidence(frames,0,len(frames)))

    def test_samples_bounded_and_cover_audio_groups(self):
        records=[dict(source=str(i),audio=i//20,style=i%3,risk_score=i/100) for i in range(58)]
        sample=sample_jobs(records)
        self.assertEqual(len(sample),3)
        self.assertEqual(len({r['audio'] for r in sample}),3)
        self.assertEqual(sample_jobs(records,0),[])

    def test_batch_skips_exception_keeps_audio_assignment_and_cleans_scratch(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir()
            for i in (1,2,3):(source/f'IMG{i}.mp4').touch()
            audio=root/'audio.mp4';audio.touch();out=root/'final'
            scratch_paths=[];jobs=[]
            def plan(ff,p,target,profile):
                a=dict(source_sha256=p.name,source_frames=960)
                bad=p.name=='IMG2.mp4'
                return a,dict(policy='local_auto_v1',missing_frames=24 if bad else 0,
                              clips=[] if bad else [dict(start_frame=0,end_frame=target)],risk_score=0)
            def run(cmd,**kw):
                if 'run_pipeline.py' in ' '.join(map(str,cmd)):
                    out.mkdir()
                    for k,arg in enumerate(cmd):
                        if arg=='--task':
                            path=Path(cmd[k+2]);scratch_paths.append(path.parent)
                            group=json.loads(path.read_text());jobs.extend(group)
                            for job in group:(out/(job['id']+'.mp4')).touch()
                    return subprocess.CompletedProcess(cmd,0)
                if '-f' in cmd:
                    return subprocess.CompletedProcess(cmd,0,stdout=b'\0'*(64000*30),stderr=b'')
                return subprocess.CompletedProcess(cmd,0,stdout='',stderr='Audio: aac')
            with patch('batch_assistant.inspect_video'),patch('batch_assistant.analyze_and_plan',side_effect=plan),patch('batch_assistant.subprocess.run',side_effect=run),patch('batch_assistant.interactive_review') as review,contextlib.redirect_stdout(io.StringIO()):
                r=run_batch(dict(ffmpeg='ffmpeg',model='model',backend='mlx',encoder='libx264'),source,
                            [(audio,'2'),(audio,'restante')],output=out,no_ui=True)
            self.assertEqual(r['completed'],2)
            self.assertEqual(len(r['exceptions']),1)
            self.assertEqual(r['exceptions'][0]['source'],'IMG2.mp4')
            self.assertIn('audio1',jobs[0]['id']);self.assertIn('audio2',jobs[1]['id'])
            review.assert_not_called()
            self.assertTrue(all(not p.exists() for p in scratch_paths))
            self.assertEqual(len(list(out.iterdir())),2)


if __name__=='__main__':unittest.main()
