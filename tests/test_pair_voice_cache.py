import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from edit_pair_batch import matching_voice_transcript


class PairVoiceCacheTests(unittest.TestCase):
    def test_exact_aac_matches_reuse_and_changed_voice_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'voice_0.m4a').write_bytes(b'voice')
            transcript = dict(segments=[dict(words=[dict(word='hello', start=0, end=1)])], audio_duration=2)
            (root/'voice_0.json').write_text(json.dumps(transcript))
            with patch('edit_pair_batch.audio_hash', side_effect=['identical', 'identical']):
                self.assertEqual(matching_voice_transcript(root, 0, 'new.m4a', 'ffmpeg'), transcript)
            with patch('edit_pair_batch.audio_hash', side_effect=['old', 'changed']):
                self.assertIsNone(matching_voice_transcript(root, 0, 'new.m4a', 'ffmpeg'))

    def test_missing_or_invalid_transcript_requires_new_transcription(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(matching_voice_transcript(root, 0, 'new.m4a', 'ffmpeg'))
            (root/'voice_0.m4a').write_bytes(b'voice')
            (root/'voice_0.json').write_text('{}')
            with patch('edit_pair_batch.audio_hash', return_value='same'):
                self.assertIsNone(matching_voice_transcript(root, 0, 'new.m4a', 'ffmpeg'))


if __name__ == '__main__':
    unittest.main()
