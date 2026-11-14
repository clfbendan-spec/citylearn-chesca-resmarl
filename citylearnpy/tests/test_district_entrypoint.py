import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class DistrictEntrypointTest(unittest.TestCase):
    def test_copied_platform_entries_support_configured_python_path(self):
        root = Path(__file__).resolve().parents[1]
        environment = dict(os.environ, CITYLEARN_PYTHON_PATH=str(root), PYTHONHASHSEED='0')
        environment.pop('CITYLEARNPY_DIR', None)
        for entry in ('District_MARL_train.py', 'District_MARL_eval.py'):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / entry
                shutil.copy2(root / entry, copied)
                run = subprocess.run([sys.executable, str(copied), '--help'], cwd=directory,
                                     env=environment, capture_output=True, timeout=90)
                self.assertEqual(run.returncode, 0, run.stdout.decode('utf-8', errors='replace') +
                                 run.stderr.decode('utf-8', errors='replace'))
                self.assertIn(b'--output-dir', run.stdout)


if __name__ == '__main__':
    unittest.main()
