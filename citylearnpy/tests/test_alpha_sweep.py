"""
α 扫描变体矩阵与 registry 入库冒烟。

运行：
  cd citylearnpy
  python tests/test_alpha_sweep.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ablation_resmarl import (  # noqa: E402
    build_alpha_sweep_payload,
    build_alpha_sweep_variants,
    parse_alpha_list,
    register_alpha_sweep,
)


class TestAlphaSweep(unittest.TestCase):
    def test_parse_alpha_list(self):
        self.assertEqual(parse_alpha_list('0, 0.05;0.15'), [0.0, 0.05, 0.15])

    def test_build_variants(self):
        vs = build_alpha_sweep_variants(None, [0.0, 0.1, 0.1])
        self.assertEqual(vs[0]['name'], 'chesca_baseline')
        self.assertFalse(vs[0]['config']['resmarl_enabled'])
        names = [v['name'] for v in vs]
        self.assertEqual(len(names), 3)  # baseline + 0 + 0.1 (dedup)
        self.assertTrue(vs[1]['config']['resmarl_enabled'])

    def test_register_writes_summary(self):
        summaries = [
            {
                'name': 'chesca_baseline',
                'label': '纯 CHESCA',
                'resmarl_enabled': False,
                'residual_alpha': 0.0,
                'district_kpis': {'cost_total': 0.4, 'ramping_average': 0.9},
                'elapsed_sec': 1,
            },
            {
                'name': 'resmarl_a0p1',
                'label': 'ResMARL α=0.1',
                'resmarl_enabled': True,
                'residual_alpha': 0.1,
                'district_kpis': {'cost_total': 0.41, 'ramping_average': 0.91},
                'elapsed_sec': 1,
            },
        ]
        payload = build_alpha_sweep_payload(
            summaries,
            run_id='unit_test_run',
            policy_path=None,
            steps=24,
            alphas=[0.1],
            output_dir='.',
        )
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / 'unit_test_run'
            path = register_alpha_sweep(payload, run_dir, update_index=False)
            self.assertTrue(path.is_file())
            loaded = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(loaded['run_id'], 'unit_test_run')
            self.assertEqual(len(loaded['points']), 2)


if __name__ == '__main__':
    unittest.main()
