"""
阶段 1 回归：ResMARL 配置解析 + Trace 剧本 MARL 行显隐。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'CHESCA-copy'))
sys.path.insert(0, str(ROOT))

from checa.trace_exporter import _build_decision_narrative_lines, _build_resmarl_narrative_lines  # noqa: E402
from checa.narrative_code_refs import classify_narrative_line, build_code_ref  # noqa: E402


class TestResidualPhase1(unittest.TestCase):
    def test_marl_lines_absent_when_disabled(self):
        row = {
            'hour': 14,
            'building': 0,
            'resmarl_enabled': False,
            'residual_alpha': 0.2,
            'control_mode': 'normal',
            'action_dhw_init': -0.83,
            'action_ele_init': 0.0,
            'action_tmp_init': 0.0,
            'action_dhw_final': -0.83,
            'action_ele_final': -0.3,
            'action_tmp_final': 0.0,
        }
        lines = _build_resmarl_narrative_lines(row, 0.45)
        self.assertEqual(lines, [])
        full = _build_decision_narrative_lines(row, True, 0.45)
        self.assertFalse(any('[MARL层' in ln for ln in full))
        self.assertFalse(any('[残差生成]' in ln for ln in full))

    def test_marl_lines_present_when_enabled(self):
        row = {
            'hour': 14,
            'building': 0,
            'resmarl_enabled': True,
            'residual_alpha': 0.15,
            'residual_skip_reason': 'zero_delta_policy',
            'residual_action_mask': {'dhw': False, 'ele': True, 'tmp': False},
            'resmarl_after_safety': True,
            'battery_soc': 0.62,
            'net_load_next': 105.0,
            'residual_delta_dhw': 0.0,
            'residual_delta_ele': 0.0,
            'residual_delta_tmp': 0.0,
            'residual_base_ele': -0.3,
            'residual_final_ele': -0.3,
            'electricity_pricing': 0.45,
            'control_mode': 'normal',
            'action_dhw_init': -0.83,
            'action_ele_init': 0.0,
            'action_tmp_init': 0.0,
            'action_dhw_final': -0.83,
            'action_ele_final': -0.3,
            'action_tmp_final': 0.0,
        }
        lines = _build_resmarl_narrative_lines(row, 0.45)
        self.assertTrue(any('[MARL层介入]' in ln for ln in lines))
        self.assertTrue(any('[残差生成]' in ln for ln in lines))
        self.assertTrue(any('α=0.15' in ln for ln in lines))
        self.assertEqual(classify_narrative_line(lines[0]), 'marl_layer')
        self.assertEqual(classify_narrative_line(lines[1]), 'residual_gen')
        ref = build_code_ref('marl_layer')
        self.assertIn('apply_residual_correction', ref['source_label'])
        self.assertTrue(len(ref['code_snippet']) > 20)

    def test_nonzero_delta_text(self):
        row = {
            'resmarl_enabled': True,
            'residual_alpha': 0.2,
            'residual_skip_reason': 'none',
            'residual_action_mask': {'ele': True, 'tmp': False, 'dhw': False},
            'resmarl_after_safety': True,
            'residual_delta_ele': -0.15,
            'residual_delta_tmp': 0.0,
            'residual_delta_dhw': 0.0,
            'residual_base_ele': -0.3,
            'residual_final_ele': -0.45,
        }
        lines = _build_resmarl_narrative_lines(row, None)
        joined = '\n'.join(lines)
        self.assertIn('追加放电残差', joined)
        self.assertIn('-0.15', joined)


if __name__ == '__main__':
    unittest.main(verbosity=2)
