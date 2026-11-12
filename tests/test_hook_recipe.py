import unittest
import numpy as np
from auto_planner import automatic_plan
from edit_batch import timeline_frames
from condensed_planner import hook_recipe_plan


class HookRecipeContracts(unittest.TestCase):
    def test_short_medium_full_voices_preserve_hook_and_recipe_order(self):
        frames=np.zeros((912,256,144),dtype=np.uint8)
        for target in (444,453,522,609,652,694,733,912):
            _,p=automatic_plan(frames,target,profile='flow_hook_receita')
            self.assertEqual(timeline_frames(p['clips']),target)
            self.assertEqual((p['clips'][0]['start_frame'],p['clips'][0]['end_frame']),(0,144))
            self.assertEqual(p['clips'][1]['start_frame'],144)
            self.assertEqual(p['clips'][3]['start_frame'],22*24)
            self.assertEqual(p['clips'][-1]['end_frame'],912)
            self.assertGreaterEqual(p['clips'][-1]['end_frame']-p['clips'][-1]['start_frame'],108)
            self.assertTrue(all(a['end_frame']<=b['start_frame'] for a,b in zip(p['clips'],p['clips'][1:])))
            self.assertFalse(p['visual_reviewed'])
            self.assertTrue(all(x['kind']=='exception' and not x['verified'] for x in p['removed']))
            self.assertFalse(p['speed_adjustments'])

    def test_reject_wrong_flow_layout_and_insufficient_voice(self):
        for n,target in ((769,453),(960,453),(912,443),(912,913)):
            with self.assertRaises(ValueError):
                automatic_plan(np.zeros((n,256,144),dtype=np.uint8),target,profile='flow_hook_receita')

    def test_rapid_opening_always_advances_recipe_even_with_long_voice(self):
        frames=np.zeros((913,256,144),dtype=np.uint8)
        for target in (454,522,609,652,694,733,793):
            _,p=automatic_plan(frames,target,profile='flow_hook_receita_rapida')
            self.assertEqual(timeline_frames(p['clips']),target)
            self.assertEqual(p['clips'][0]['end_frame'],72)
            self.assertEqual(p['clips'][1]['start_frame'],192)
            self.assertEqual(p['clips'][-1]['end_frame'],913)
            self.assertFalse(p['speed_adjustments'])
        with self.assertRaises(ValueError):
            automatic_plan(frames,913,profile='flow_hook_receita_rapida')
        _,p=hook_recipe_plan(frames,913,hook_seconds=3,recipe_advance_seconds=2,long_voice='slow_recipe')
        self.assertEqual(timeline_frames(p['clips']),913)
        self.assertEqual(p['clips'][0]['end_frame'],72)
        self.assertEqual(p['clips'][1]['start_frame'],192)
        self.assertNotIn('output_frames',p['clips'][0])
        self.assertTrue(all(c['authorized_slowdown'] for c in p['clips'][1:]))
        self.assertTrue(all(.8<=s['speed']<1 for s in p['speed_adjustments']))
        with self.assertRaises(ValueError):
            hook_recipe_plan(frames,1000,hook_seconds=3,recipe_advance_seconds=2,long_voice='slow_recipe')

    def test_explicit_repeat_preserves_voice_duration_without_slowing(self):
        _,p=hook_recipe_plan(np.zeros((913,256,144),dtype=np.uint8),913,hook_seconds=3,
                             recipe_advance_seconds=2,long_voice='repeat_presentation')
        self.assertEqual(timeline_frames(p['clips']),913)
        self.assertFalse(p['speed_adjustments'])
        self.assertEqual(p['clips'][-1]['recipe_stage'],'repeticao_final_autorizada')
