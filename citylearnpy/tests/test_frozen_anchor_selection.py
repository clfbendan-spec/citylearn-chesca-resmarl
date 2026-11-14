"""Model selection must never substitute a training task for the frozen anchor."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aacmadrl import task


class FrozenAnchorSelectionTest(unittest.TestCase):
    def test_frozen_anchor_loads_only_verified_predeclared_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / 'anchor.pt'
            model.write_bytes(b'fixed reference policy')
            args = task.parser('eval').parse_args(['--output-dir', directory, '--frozen-anchor', 'on'])
            with patch.object(task, 'FROZEN_ANCHOR_PATH', model), patch.object(
                    task, 'FROZEN_ANCHOR_SHA256',
                    hashlib.sha256(b'fixed reference policy').hexdigest()):
                self.assertEqual(task.resolve_evaluation_model(args, Path(directory)), model)
                model.write_bytes(b'replaced policy')
                with self.assertRaisesRegex(ValueError, 'SHA256'):
                    task.resolve_evaluation_model(args, Path(directory))

    def test_frozen_anchor_rejects_competing_model_sources(self):
        for competing in (['--train-task-id', 'another-task'], ['--checkpoint', 'another.pt']):
            args = task.parser('eval').parse_args(['--output-dir', '.', '--frozen-anchor', 'on', *competing])
            with self.assertRaisesRegex(ValueError, '模型来源'):
                task.resolve_evaluation_model(args, Path('.'))

    def test_default_still_requires_a_model(self):
        args = task.parser('eval').parse_args(['--output-dir', '.'])
        with self.assertRaisesRegex(ValueError, '模型来源'):
            task.resolve_evaluation_model(args, Path('.'))


if __name__ == '__main__':
    unittest.main()
