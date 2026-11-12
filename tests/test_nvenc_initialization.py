import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from edit_batch import run_encoder


class NvencInitializationTests(unittest.TestCase):
    def failure(self, text, size=0):
        def fail(cmd, **kwargs):
            kwargs['stdout'].write(text)
            (Path(kwargs['cwd'])/'render.mp4').write_bytes(b'x' * size)
            raise subprocess.CalledProcessError(21, cmd)
        return fail

    def test_known_zero_output_initialization_failure_retries_once(self):
        text = 'OpenEncodeSessionEx failed: incompatible client key (21)\nNothing was written into output file\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = 0
            failure = self.failure(text)
            def render(cmd, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    failure(cmd, **kwargs)
                kwargs['stdout'].write('second attempt successful\n')
            with patch('edit_batch.subprocess.run', side_effect=render), patch('edit_batch.time.sleep'):
                self.assertEqual(run_encoder(['ffmpeg'], root, 'h264_nvenc'), 1)
            self.assertEqual(calls, 2)
            self.assertIn(text, (root/'render.log').read_text())

    def test_unknown_encoder_nonempty_output_and_second_failure_stop(self):
        known = 'OpenEncodeSessionEx failed: incompatible client key (21)\nNothing was written into output file\n'
        cases = [('h264_nvenc', 'other error', 0, 1),
                 ('libx264', known, 0, 1),
                 ('h264_nvenc', known, 8, 1),
                 ('h264_nvenc', known, 0, 2)]
        for encoder, text, size, expected in cases:
            with self.subTest(encoder=encoder, size=size, text=text), tempfile.TemporaryDirectory() as directory:
                with patch('edit_batch.subprocess.run', side_effect=self.failure(text, size)) as render, patch('edit_batch.time.sleep'):
                    with self.assertRaises(RuntimeError):
                        run_encoder(['ffmpeg'], Path(directory), encoder)
                self.assertEqual(render.call_count, expected)


if __name__ == '__main__':
    unittest.main()
