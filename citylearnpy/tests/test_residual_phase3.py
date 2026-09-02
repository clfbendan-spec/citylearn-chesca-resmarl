"""
阶段 3 回归：Trace base/delta/final 导出 + 消融配置矩阵。

运行：
  cd citylearnpy
  python tests/test_residual_phase3.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHESCA = ROOT / 'CHESCA-copy'
sys.path.insert(0, str(CHESCA))
sys.path.insert(0, str(ROOT))

from checa.trace_exporter import (  # noqa: E402
    TRACE_COLUMNS,
    ChescaTraceRecorder,
    _build_step_phases,
    save_chesca_trace,
    save_decision_trace_json,
)
from ablation_resmarl import build_variants, write_ablation_configs  # noqa: E402


class TestResidualPhase3(unittest.TestCase):
    def test_trace_columns_include_base_final(self):
        for col in (
            'residual_base_ele',
            'residual_final_ele',
            'residual_delta_ele',
        ):
            self.assertIn(col, TRACE_COLUMNS)

    def test_step_phases_include_resmarl_when_enabled(self):
        rows = [
            {
                'building': 0,
                'actual_outdoor_temp': 28,
                'forecast_outdoor_temp': 27,
                'forecast_outdoor_next': 29,
                'control_mode': 'normal',
                'action_dhw_init': 0.1,
                'action_ele_init': 0.0,
                'action_tmp_init': 0.5,
                'tau': 1,
                'outage_flag': False,
                'trigger_reduce_load': False,
                'trigger_increase_load': False,
                'resmarl_enabled': True,
                'residual_alpha': 0.15,
                'residual_applied': True,
                'residual_skip_reason': 'none',
                'residual_base_ele': 0.2,
                'residual_delta_ele': 0.03,
                'residual_final_ele': 0.23,
            }
        ]
        phases = _build_step_phases(rows, global_refine=True)
        self.assertEqual(len(phases), 6)
        self.assertEqual(phases[-1]['phase'], 6)
        self.assertIn('ResMARL', phases[-1]['name'])

    def test_decision_trace_json_has_base_delta_final(self):
        recorder = ChescaTraceRecorder(1)
        recorder.episode = 1
        recorder._step = 0
        recorder.rows.append({
            'episode': 1,
            'step': 0,
            'hour': 1,
            'building': 0,
            'refine_skip_reason': 'first_step',
            'tau': 1,
            'balance_type': 'C',
            'B_low': 1.18,
            'B_high': 1.0,
            'control_mode': 'normal',
            'outage_flag': False,
            'decision_summary': 'test',
            'decision_narrative': '',
            'battery_soc': 0.5,
            'dhw_soc': 0.2,
            'action_dhw_init': 0,
            'action_ele_init': 0,
            'action_tmp_init': 0,
            'action_dhw_final': 0,
            'action_ele_final': 0.2,
            'action_tmp_final': 0,
            'forecast_load_next': 1,
            'forecast_solar_next': 0,
            'forecast_dhw_next': 0,
            'refine_applied': False,
            'trigger_reduce_load': False,
            'trigger_increase_load': False,
            'net_load_next': 1,
            'net_load_mean': 1,
            'net_load_std': 0,
            'battery_search_cost': 0,
            'resmarl_enabled': True,
            'residual_alpha': 0.15,
            'residual_applied': True,
            'residual_skip_reason': 'none',
            'residual_action_mask': {'dhw': False, 'ele': True, 'tmp': False},
            'resmarl_after_safety': True,
            'residual_base_dhw': 0,
            'residual_base_ele': 0.1,
            'residual_base_tmp': 0,
            'residual_delta_dhw': 0,
            'residual_delta_ele': 0.05,
            'residual_delta_tmp': 0,
            'residual_final_dhw': 0,
            'residual_final_ele': 0.15,
            'residual_final_tmp': 0,
        })
        with tempfile.TemporaryDirectory() as td:
            json_path = Path(td) / 'decision_trace.json'
            csv_path = Path(td) / 'chesca_trace.csv'
            save_decision_trace_json(recorder, json_path)
            save_chesca_trace(recorder, csv_path)
            payload = json.loads(json_path.read_text(encoding='utf-8'))
            residual = payload['steps'][0]['buildings'][0]['residual']
            self.assertIn('base', residual)
            self.assertIn('delta', residual)
            self.assertIn('final', residual)
            self.assertAlmostEqual(residual['base']['ele'], 0.1)
            self.assertAlmostEqual(residual['delta']['ele'], 0.05)
            self.assertAlmostEqual(residual['final']['ele'], 0.15)
            csv_text = csv_path.read_text(encoding='utf-8')
            self.assertIn('residual_base_ele', csv_text)
            self.assertIn('residual_final_ele', csv_text)

    def test_ablation_variants_matrix(self):
        variants = build_variants(None, 0.15)
        names = [v['name'] for v in variants]
        self.assertEqual(names, ['chesca_baseline', 'resmarl_alpha0', 'resmarl_full'])
        self.assertFalse(variants[0]['config']['resmarl_enabled'])
        self.assertTrue(variants[1]['config']['resmarl_enabled'])
        self.assertEqual(variants[1]['config']['residual_alpha'], 0.0)
        self.assertTrue(variants[2]['config']['resmarl_enabled'])
        self.assertEqual(variants[2]['config']['residual_alpha'], 0.15)
        write_ablation_configs(variants)
        for name in names:
            path = ROOT / 'configs' / 'ablation' / f'{name}.json'
            self.assertTrue(path.is_file(), path)
            cfg = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(cfg['_ablation_name'], name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
