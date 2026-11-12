import unittest, random
from collections import Counter
from batch_assistant import balanced_styles
from edit_batch import STYLES
from edit_hook_matrix import _pilot_styles

class MatrixStyleContracts(unittest.TestCase):
    def test_pilot_swaps_keep_exact_active_style_quotas_for_small_and_large_batches(self):
        for count in range(1,81):
            for seed in range(5):
                jobs=[{'style':s} for s in balanced_styles(count,random.Random(seed))]
                before=Counter(j['style'] for j in jobs)
                pilots=list(range(min(3,count)))
                _pilot_styles(jobs,pilots)
                self.assertEqual(Counter(j['style'] for j in jobs),before)
                self.assertTrue(all(j['style'] in STYLES for j in jobs))
                if count>=2:self.assertEqual([jobs[i]['style'] for i in pilots[:2]],[0,2])
                if count>=3 and before[0]>=2:self.assertEqual(jobs[pilots[2]]['style'],0)
