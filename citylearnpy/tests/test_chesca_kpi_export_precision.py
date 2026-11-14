import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import CHESCA


class KpiExportPrecisionTest(unittest.TestCase):
    def test_export_preserves_ratio_precision(self):
        value = .010864708126371412
        table = pd.DataFrame([{'cost_function': 'discomfort_proportion', 'name': 'District',
                               'level': 'district', 'value': value}])
        env = SimpleNamespace(evaluate=lambda: table)
        with tempfile.TemporaryDirectory() as directory, patch.object(CHESCA, 'print_kpis_for_java'):
            path = CHESCA.save_episode_kpis(env, Path(directory))
            actual = pd.read_csv(path).iloc[0]['District']
            self.assertAlmostEqual(actual, value, places=14)


if __name__ == '__main__':
    unittest.main()
