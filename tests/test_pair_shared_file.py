import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from edit_pair_batch import load


class SharedFileTests(unittest.TestCase):
    def test_non_windows_permission_error_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'ready.json'
            path.write_text('[]')
            with patch('edit_pair_batch.os.name', 'posix'), \
                 patch.object(type(path), 'read_text', side_effect=PermissionError('denied')) as read, \
                 patch('edit_pair_batch.time.sleep') as pause:
                with self.assertRaises(PermissionError):
                    load(path, [])
                read.assert_called_once()
                pause.assert_not_called()

    def test_windows_atomic_replace_lock_recovers_without_empty_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'ready.json'
            path.write_text('[{"id":"114"}]')
            with patch('edit_pair_batch.os.name', 'nt'), \
                 patch.object(type(path), 'read_text', side_effect=[PermissionError('locked'), '[{"id":"114"}]']), \
                 patch('edit_pair_batch.time.sleep') as pause:
                self.assertEqual(load(path, []), [{'id': '114'}])
                pause.assert_called_once_with(.02)

    def test_persistent_lock_stops_after_six_reads_and_corruption_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'ready.json'
            path.write_text('[]')
            with patch('edit_pair_batch.os.name', 'nt'), \
                 patch.object(type(path), 'read_text', side_effect=PermissionError('locked')) as read, \
                 patch('edit_pair_batch.time.sleep'):
                with self.assertRaises(PermissionError):
                    load(path, [])
                self.assertEqual(read.call_count, 6)
            path.write_text('invalid json')
            with self.assertRaises(json.JSONDecodeError):
                load(path, [])


if __name__ == '__main__':
    unittest.main()
