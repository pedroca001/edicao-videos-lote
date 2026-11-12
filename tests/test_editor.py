import unittest

from edit_batch import STYLES, group_words, make_ass, normalized_words, timeline_frames


class EditorContracts(unittest.TestCase):
    def test_slowdown_is_explicit_bounded_and_preserves_complete_source(self):
        clip=dict(start_frame=0,end_frame=769,output_frames=913)
        with self.assertRaises(ValueError):timeline_frames([clip])
        clip['authorized_slowdown']=True
        self.assertEqual(timeline_frames([clip]),913)
        clip['output_frames']=1000
        with self.assertRaises(ValueError):timeline_frames([clip])
    def test_realistic_overlaps_match_voice_duration(self):
        lengths = [125, 132, 70, 110, 74, 122, 113]
        clips = [dict(start_frame=0, end_frame=n, transition_frames=4 if i in (1, 3, 5) else 0)
                 for i, n in enumerate(lengths)]
        self.assertEqual(timeline_frames(clips), 734)
        with self.assertRaises(ValueError):
            timeline_frames([dict(start_frame=0, end_frame=4), dict(start_frame=0, end_frame=4, transition_frames=4)])

    def test_hyphenated_speech_preserves_words_and_timing(self):
        source = {'segments': [{'words': [
            dict(word='70', start=1, end=1.2), dict(word='-year', start=1.2, end=1.4),
            dict(word='-old', start=1.4, end=1.6), dict(word=' man.', start=1.6, end=2)]}]}
        words = normalized_words(source)
        self.assertEqual(words, [dict(text='70-year-old', start=1, end=1.6), dict(text='man.', start=1.6, end=2)])
        for style in STYLES.values():
            grouped = group_words(words, style)
            self.assertEqual([w for g in grouped for w in g], words)
            ass = make_ass(source, style, 2.1)
            self.assertIn('70-YEAR-OLD' if style['upper'] else '70-year-old', ass)
            self.assertIn('0:00:02.10', ass)

    def test_only_approved_styles_remain_with_stable_ids(self):
        self.assertEqual(set(STYLES), {0, 2})
        self.assertEqual(STYLES[2]['name'], 'duas_linhas_lima')
        from edit_batch import run_job
        with self.assertRaises(ValueError):run_job({'style':1},None,None,None)

    def test_bad_timestamp_order_is_rejected(self):
        with self.assertRaises(ValueError):
            normalized_words({'segments': [{'words': [dict(word='a', start=2, end=3), dict(word='b', start=1, end=2)]}]})


if __name__ == '__main__':
    unittest.main()
