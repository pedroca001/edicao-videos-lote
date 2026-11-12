import unittest

from edit_avatar_batch import kept_ranges, remap_words


class AvatarCuts(unittest.TestCase):
    def test_removes_pause_but_protects_padded_speech(self):
        words = [dict(word='hello', start=.3, end=1.1), dict(word='there', start=2.1, end=2.8)]
        keep, removed = kept_ranges(4, [(0, .25), (1, 2.3), (2.9, 4)], words)
        for a, b in removed:
            for word in words:
                self.assertTrue(b/24 <= word['start']-.055+1e-8 or a/24 >= word['end']+.075-1e-8)
        self.assertLess(sum(b-a for a, b in keep), 96)
        mapped = remap_words(words, keep)
        for before, after in zip(words, mapped):
            self.assertAlmostEqual(before['end']-before['start'], after['end']-after['start'])
        self.assertGreater(mapped[1]['start'], mapped[0]['end'])

    def test_no_quiet_time_leaves_timeline_unchanged(self):
        keep, removed = kept_ranges(4, [], [])
        self.assertEqual(keep, [(0, 96)])
        self.assertEqual(removed, [])

    def test_acoustic_mode_cuts_quiet_inside_stretched_asr_timestamps(self):
        words = [dict(word='hello', start=0, end=2), dict(word='there', start=2, end=4)]
        keep, removed = kept_ranges(4, [(1, 1.8)], words, protect_words=False)
        self.assertTrue(removed)
        self.assertTrue(all(a/24 >= 1.06 and b/24 <= 1.72 for a, b in removed))
        mapped = remap_words(words, keep)
        self.assertAlmostEqual(mapped[-1]['end'], sum(b-a for a, b in keep)/24)

    def test_maps_across_multiple_removed_gaps(self):
        keep = [(0, 24), (48, 72), (96, 120)]
        words = [dict(word='last', start=4.2, end=4.7)]
        result = remap_words(words, keep)
        self.assertAlmostEqual(result[0]['start'], 2.2)
        self.assertAlmostEqual(result[0]['end'], 2.7)

    def test_short_quiet_gap_does_not_create_phoneme_cut(self):
        keep, removed = kept_ranges(4, [(1, 1.24)], [])
        self.assertEqual(removed, [])
        self.assertEqual(keep, [(0, 96)])


if __name__ == '__main__':
    unittest.main()
