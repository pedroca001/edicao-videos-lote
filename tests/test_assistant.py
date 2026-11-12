import random
import unittest
from batch_assistant import balanced_styles, validate_allocations
from edit_batch import timeline_frames, STYLES
from collections import Counter


class AssistantContracts(unittest.TestCase):
    def test_style_distribution_has_balanced_counts_without_neighbours(self):
        for n in range(1, 201):
            for seed in range(10):
                styles = balanced_styles(n, random.Random(seed))
                counts = Counter(styles)
                self.assertEqual(len(styles), n)
                self.assertTrue(set(styles) <= set(STYLES))
                self.assertTrue(all(a != b for a,b in zip(styles, styles[1:])))
                self.assertLessEqual(max(counts.get(i,0) for i in STYLES)-min(counts.get(i,0) for i in STYLES), 1)

    def test_allocations_reject_missing_or_extra_inputs(self):
        self.assertEqual(validate_allocations(58, [('a','20'),('b','20'),('c','restante')]), [20,20,18])
        for specs in [[('a','59')], [('a','57')], [('a','-1')], [('a','restante'),('b','2')]]:
            with self.assertRaises(ValueError):
                validate_allocations(58, specs)
