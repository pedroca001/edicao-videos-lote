import unittest
import numpy as np
from auto_planner import automatic_plan
from edit_batch import timeline_frames


class CondensedContracts(unittest.TestCase):
    def test_short_voices_keep_five_ordered_stages_and_full_presentation(self):
        frames=np.zeros((960,256,144),dtype=np.uint8)
        for target in (355,392,401,425,428,481,576):
            _, p=automatic_plan(frames,target,profile='vids_receita_resumida')
            self.assertEqual(p['status'],'ready')
            self.assertEqual(timeline_frames(p['clips']),target)
            self.assertEqual([x['recipe_stage'] for x in p['clips']],
                ['mexida_inicial','bicarbonato','mel','limao','mexida_pegada_apresentacao_final'])
            self.assertEqual(p['clips'][0]['start_frame'],0)
            self.assertEqual(p['clips'][-1]['end_frame'],960)
            self.assertGreaterEqual(p['clips'][-1]['end_frame']-p['clips'][-1]['start_frame'],108)
            self.assertTrue(all(a['end_frame']<=b['start_frame'] for a,b in zip(p['clips'],p['clips'][1:])))
            self.assertFalse(p['visual_reviewed'])
            self.assertTrue(p['requires_user_authorization'])
            self.assertFalse(p['ingredient_recognition'])
            self.assertTrue(all(x['kind']=='exception' and not x['verified'] for x in p['removed']))
            self.assertFalse(p['speed_adjustments'])

    def test_opt_in_never_changes_standard_profile_or_claims_wrong_source_supported(self):
        frames=np.zeros((960,256,144),dtype=np.uint8)
        _, p=automatic_plan(frames,355)
        self.assertEqual(p['policy'],'local_auto_v1')
        for n,target in ((480,355),(960,300),(960,600)):
            _, p=automatic_plan(frames[:n],target,profile='vids_receita_resumida')
            self.assertEqual(p['status'],'exception')
            self.assertEqual(p['clips'],[])



class FlowCondensedContracts(unittest.TestCase):
    def test_flow_short_voices_keep_chronological_ingredients_and_continuous_result(self):
        frames=np.zeros((769,256,144),dtype=np.uint8)
        for target in (330,334,349,400,480,522,609,696,733,744):
            _,p=automatic_plan(frames,target,profile='flow_receita_resumida')
            self.assertEqual(p['status'],'ready')
            self.assertEqual(p['policy'],'flow_recipe_condensed_authorized_v1')
            self.assertEqual(p['clips'][2]['start_frame'],16*24)
            self.assertEqual(timeline_frames(p['clips']),target)
            self.assertEqual(p['clips'][0]['start_frame'],0)
            self.assertEqual(p['clips'][-1]['end_frame'],769)
            self.assertGreaterEqual(p['clips'][-1]['end_frame']-p['clips'][-1]['start_frame'],108)
            for shot,lo,hi in zip(p['clips'][1:4],[8,16,20],[16,20,24]):
                self.assertGreaterEqual(shot['start_frame'],lo*24)
                self.assertLessEqual(shot['end_frame'],hi*24)
            self.assertTrue(all(a['end_frame']<=b['start_frame'] for a,b in zip(p['clips'],p['clips'][1:])))
            self.assertTrue(p['requires_user_authorization'])
            self.assertFalse(p['visual_reviewed'])
            self.assertFalse(p['ingredient_recognition'])
            self.assertTrue(all(r['kind']=='exception' and not r['verified'] for r in p['removed']))

    def test_flow_opt_in_bounds_and_standard_profile_remain_distinct(self):
        frames=np.zeros((960,256,144),dtype=np.uint8)
        for n,target in ((960,349),(700,349),(769,300),(769,745)):
            _,p=automatic_plan(frames[:n],target,profile='flow_receita_resumida')
            self.assertEqual(p['status'],'exception')
            self.assertEqual(p['clips'],[])
        _,p=automatic_plan(frames[:769],349,profile='conservative')
        self.assertEqual(p['policy'],'local_auto_v1')

class GenericScenesContracts(unittest.TestCase):
    def test_all_four_scenes_and_continuous_result_survive_summary(self):
        frames=np.zeros((769,256,144),dtype=np.uint8)
        for target in (454,522,609,696,733,744):
            _,p=automatic_plan(frames,target,profile='flow_cenas_resumidas')
            self.assertEqual(timeline_frames(p['clips']),target)
            self.assertEqual(p['clips'][0]['start_frame'],0)
            self.assertEqual(p['clips'][-1]['end_frame'],769)
            self.assertGreaterEqual(p['clips'][-1]['end_frame']-p['clips'][-1]['start_frame'],108)
            for i,c in enumerate(p['clips']):
                self.assertGreaterEqual(c['start_frame'],i*192)
                self.assertLessEqual(c['end_frame'],(i+1)*192 if i<3 else 769)
            self.assertFalse(p['ingredient_recognition'])
            self.assertFalse(p['visual_reviewed'])
        with self.assertRaises(ValueError):automatic_plan(frames,300,profile='flow_cenas_resumidas')
