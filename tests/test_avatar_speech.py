import unittest
from avatar_speech import match_speech, speech_ranges, tokens, fluid_ranges, tighten_fluid_ranges


class AvatarSpeechTests(unittest.TestCase):
    def test_tighten_uses_only_long_quiet_and_protects_its_edges(self):
        keep,cuts=tighten_fluid_ranges([(0,180),(192,360)],[(1,1.2),(3,3.8)])
        self.assertEqual(len(cuts),1)
        a,b=cuts[0]
        self.assertGreaterEqual(a/24,3.055)
        self.assertLessEqual(b/24,3.7)
        self.assertTrue(all(not (x<=383<y) for x,y in keep))

    def test_fluid_cannot_leak_previous_scene_reference_frame(self):
        scenes=[dict(scene=i+1,start=i*8,end=i*8+6.5) for i in range(5)]
        keep,removed=fluid_ranges(40,scenes)
        self.assertEqual(len(keep),5)
        self.assertEqual([a for a,b in keep],[0,192,384,576,768])
        self.assertFalse(any(a<=383<b for a,b in keep))

    def test_fluid_preserves_scene_interior_and_soft_speech_tail(self):
        keep,removed=fluid_ranges(40,[dict(scene=5,start=32,end=39.04)])
        self.assertEqual(keep,[(768,943)])
        self.assertGreaterEqual(keep[0][1]/24,39.25)

    def test_matches_script_and_excludes_laugh_tokens(self):
        words=[dict(word=w,start=i*.4,end=i*.4+.3) for i,w in enumerate(['hello','there','ha','ha'])]
        selected,coverage=match_speech(words,'hello there')
        self.assertEqual([w['word'] for w in selected],['hello','there'])
        self.assertEqual(coverage,1)

    def test_nonverbal_tail_is_removed_even_without_acoustic_silence(self):
        words=[dict(word='trick',start=5.96,end=6.44),dict(word='it',start=8.0,end=8.14)]
        keep,removed=speech_ranges(16,words,[])
        self.assertTrue(any(a/24>=6.44 and b/24<=8.0 and b-a>24 for a,b in removed))
        self.assertTrue(all(not(a<=7*24<b) for a,b in keep))

    def test_low_coverage_stops_before_render(self):
        with self.assertRaisesRegex(ValueError,'coverage'):
            match_speech([dict(word='unrelated',start=0,end=1)],'the complete original spoken sentence')

    def test_quiet_consonants_and_final_word_are_never_cut_as_silence(self):
        words=[dict(word='follow',start=0,end=.4),dict(word='privately',start=1,end=1.7)]
        keep,removed=speech_ranges(3,words,[(0,.2),(1.3,1.6)])
        for word in words:
            self.assertTrue(any(a/24<=word['start'] and b/24>=word['end'] for a,b in keep))

    def test_numeric_asr_spelling_matches_script(self):
        self.assertEqual(tokens('$2'),tokens('two dollars'))
        self.assertEqual(tokens('65'),tokens('sixty-five'))


if __name__=='__main__':
    unittest.main()
