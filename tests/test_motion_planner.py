import unittest
from motion_planner import plan_from_review, analyze_frames
from cut_review import validate_final_review, plan_digest
from edit_batch import timeline_frames, build_filter


def analysis():
    return dict(source_frames=960, fps=24, source_sha256='source')


def region(a,b,kind='pause',**kwargs):
    return dict(start_frame=a,end_frame=b,kind=kind,action='acao conferida',
                reason='poses e intervalo conferidos',verified=True,**kwargs)


def reviewed(regions):
    return dict(analysis(),regions=regions)


class MotionPlannerContracts(unittest.TestCase):
    def test_seam_pauses_first_and_variable_segment_count(self):
        r=reviewed([region(90,130),region(210,252),region(450,492),region(684,720)])
        p=plan_from_review(analysis(),840,r)
        self.assertEqual(p['missing_frames'],0)
        self.assertEqual(p['clips'],[dict(start_frame=a,end_frame=b,transition_frames=0,zoom=1.0)
                                   for a,b in [(0,210),(252,450),(492,684),(720,960)]])
        self.assertEqual(timeline_frames(p['clips']),840)

    def test_no_unreviewed_low_motion_or_moving_actions_silently_deleted(self):
        r=reviewed([region(210,252),region(450,492,'protect')])
        p=plan_from_review(analysis(),570,r)
        self.assertEqual(p['missing_frames'],348)
        self.assertEqual(p['clips'],[])
        r['regions'][0]['verified']=False
        with self.assertRaises(ValueError):plan_from_review(analysis(),840,r)

    def test_shortage_uses_cyclic_motion_then_selective_speed_before_exception(self):
        r=reviewed([region(50,98,'repetition'),region(210,258),
                    region(300,420,'speed',max_speed=1.2),region(500,600,'exception')])
        p=plan_from_review(analysis(),844,r)
        self.assertEqual(p['missing_frames'],0)
        self.assertFalse(any(x['kind']=='exception' for x in p['removed']))
        self.assertEqual(p['speed_adjustments'][0]['output_frames'],100)
        self.assertEqual(timeline_frames(p['clips']),844)
        self.assertIn('setpts=(PTS-STARTPTS)*100/120',build_filter({'clips':p['clips']},24))

    def test_source_and_final_review_bind_to_actual_plan(self):
        r=reviewed([region(210,252)])
        p=plan_from_review(analysis(),918,r)
        with self.assertRaises(ValueError):validate_final_review(analysis(),918,r)
        r.update(endpoints_reviewed=True,plan_sha256=plan_digest(p))
        self.assertEqual(validate_final_review(analysis(),918,r)['clips'],p['clips'])
        with self.assertRaises(ValueError):validate_final_review(analysis(),920,r)
        r['source_sha256']='wrong'
        with self.assertRaises(ValueError):plan_from_review(analysis(),918,r)

    def test_protect_start_final_pose_and_prevent_overlapping_annotations(self):
        for regions in [[region(0,48)],[region(900,950)],[region(210,252),region(240,260,'protect')]]:
            with self.assertRaises(ValueError):plan_from_review(analysis(),840,reviewed(regions))

    def test_static_endpoints_do_not_hide_an_action_in_between(self):
        import numpy as np
        frames=np.zeros((480,256,144),dtype=np.uint8)
        # A product returns to its initial place. Whole action cannot be a pause.
        for i in range(48,168):
            x=10+(i*3)%95
            frames[i,140:200,x:x+25]=220
        result=analyze_frames(frames)
        self.assertFalse(any(c['start_frame']<=48 and c['end_frame']>=168 for c in result['candidates']))

    def test_upper_background_does_not_veto_foreground_rest(self):
        import numpy as np
        frames=np.zeros((480,256,144),dtype=np.uint8)
        for i in range(480):frames[i,:80,:]=(i*31)%255
        result=analyze_frames(frames)
        self.assertGreater(result['candidate_seconds'],15)
        self.assertTrue(all(c['confidence']=='heuristic_requires_visual_review' for c in result['candidates']))


if __name__=='__main__':unittest.main()
