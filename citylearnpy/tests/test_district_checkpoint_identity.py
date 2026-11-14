"""Exercise checkpoint filesystem resolution without importing the Ray runtime."""
import ast
import tempfile
import types
import unittest
from pathlib import Path
from typing import List, Optional


class DistrictCheckpointIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.legacy = self.root / 'global'
        self.legacy.mkdir()
        (self.legacy / 'rllib_checkpoint.json').write_text('{}')
        source = Path(__file__).resolve().parents[1] / 'district_marl/district_eval.py'
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        names = {'_is_checkpoint_dir', '_task_id_candidates', '_resolve_from_task_id', 'resolve_checkpoint'}
        module = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
        self.ns = dict(Path=Path, List=List, Optional=Optional, log_console=lambda _: None,
                       dc=types.SimpleNamespace(DISTRICT_CHECKPOINT_DIR=self.legacy,
                                                DISTRICT_CKPT_REL_DIR='checkpoints/resume',
                                                DISTRICT_CKPT_BEST_REL_DIR='checkpoints/best'))
        exec(compile(module, str(source), 'exec'), self.ns)

    def test_missing_bound_model_does_not_use_global_checkpoint(self):
        result = self.ns['resolve_checkpoint'](None, 'missing', self.root / 'eval')
        self.assertIsNone(result[0])

    def test_task_model_resolves_with_its_identity(self):
        model = self.root / 'owned-train/checkpoints/resume'
        model.mkdir(parents=True)
        (model / 'rllib_checkpoint.json').write_text('{}')
        result = self.ns['resolve_checkpoint'](None, 'owned', self.root / 'eval')
        self.assertEqual(Path(result[0]), model)
        self.assertEqual(result[1], 'owned')

    def test_task_id_cannot_escape_output_root(self):
        for task in ('../global', '..\\global', str(self.legacy), '/global'):
            with self.subTest(task=task), self.assertRaises(ValueError):
                self.ns['resolve_checkpoint'](None, task, self.root / 'eval')

    def test_explicit_unbound_checkpoint_keeps_no_training_identity(self):
        result = self.ns['resolve_checkpoint'](str(self.legacy), None, self.root / 'eval')
        self.assertEqual(result[:2], (str(self.legacy), None))


if __name__ == '__main__':
    unittest.main()
