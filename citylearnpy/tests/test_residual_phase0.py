"""
阶段 0 回归测试：ResMARL 关闭 / α=0 时残差层严格恒等。

运行：
  cd citylearnpy
  D:\\Users\\clfbe\\anaconda3\\envs\\cl2\\python.exe -m pytest tests/test_residual_phase0.py -q
或：
  D:\\Users\\clfbe\\anaconda3\\envs\\cl2\\python.exe tests/test_residual_phase0.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CHESCA = ROOT / 'CHESCA-copy'
sys.path.insert(0, str(CHESCA))
sys.path.insert(0, str(ROOT))

from checa.residual import ResidualCorrector, parse_residual_config  # noqa: E402
from local_evaluation_copy import load_agent_config  # noqa: E402


BASELINE_PATH = ROOT / 'configs' / 'chesca_baseline_v1.json'


class TestResidualPhase0(unittest.TestCase):
    def test_baseline_config_file_exists_and_disables_resmarl(self):
        self.assertTrue(BASELINE_PATH.is_file(), f'缺少基线配置: {BASELINE_PATH}')
        raw = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
        self.assertFalse(raw.get('resmarl_enabled'))
        self.assertEqual(float(raw.get('residual_alpha', -1)), 0.0)
        self.assertEqual(raw.get('tau'), 1)
        self.assertEqual(raw.get('balance_type'), 'C')

    def test_load_agent_config_parses_resmarl_defaults(self):
        cfg = load_agent_config(str(BASELINE_PATH))
        self.assertIsNotNone(cfg)
        self.assertFalse(cfg['resmarl_enabled'])
        self.assertEqual(cfg['residual_alpha'], 0.0)
        self.assertEqual(cfg['residual_action_mask']['ele'], True)
        self.assertEqual(cfg['residual_action_mask']['dhw'], False)
        self.assertEqual(cfg['residual_action_mask']['tmp'], False)

    def test_parse_residual_config_inactive_by_default(self):
        cfg = parse_residual_config({})
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.alpha, 0.0)
        self.assertFalse(cfg.is_active)

    def test_corrector_disabled_is_identity(self):
        corrector = ResidualCorrector.from_params(3, {'resmarl_enabled': False, 'residual_alpha': 0.2})
        a_base = [0.1, -0.3, 0.5, 0.0, 0.2, 0.0, -0.83, 0.0, 0.4]
        out = corrector.correct(a_base)
        np.testing.assert_array_equal(out, np.asarray(a_base, dtype=float))
        self.assertFalse(corrector.last_trace.applied)
        self.assertEqual(corrector.last_trace.skip_reason, 'disabled')

    def test_corrector_alpha_zero_is_identity(self):
        corrector = ResidualCorrector.from_params(3, {'resmarl_enabled': True, 'residual_alpha': 0.0})
        a_base = [0.1, -0.3, 0.5, 0.0, 0.2, 0.0, -0.83, 0.0, 0.4]
        out = corrector.correct(a_base)
        np.testing.assert_array_equal(out, np.asarray(a_base, dtype=float))
        self.assertFalse(corrector.last_trace.applied)
        self.assertEqual(corrector.last_trace.skip_reason, 'alpha_zero')

    def test_corrector_enabled_without_policy_still_zero_delta(self):
        """阶段0无策略网络：即使 enabled+α>0，Δa=0，动作数值不变。"""
        corrector = ResidualCorrector.from_params(
            3,
            {
                'resmarl_enabled': True,
                'residual_alpha': 0.15,
                'residual_action_mask': {'dhw': False, 'ele': True, 'tmp': False},
            },
        )
        a_base = np.array([0.1, -0.3, 0.5, 0.0, 0.2, 0.0, -0.83, 0.0, 0.4], dtype=float)
        low = np.full_like(a_base, -1.0)
        high = np.full_like(a_base, 1.0)
        out = corrector.correct(a_base, action_low=low, action_high=high)
        np.testing.assert_allclose(out, a_base, rtol=0, atol=1e-12)
        self.assertFalse(corrector.last_trace.applied)
        self.assertEqual(corrector.last_trace.skip_reason, 'zero_delta_policy')
        self.assertTrue(np.allclose(corrector.last_trace.delta, 0.0))

    def test_mask_zeros_non_ele_dims_when_policy_nonzero(self):
        """自定义 predict_delta 时，mask 应屏蔽 DHW/TMP。"""

        class FakeCorrector(ResidualCorrector):
            def predict_delta(self, a_base, observations=None, chesca_state=None):
                return np.ones(len(a_base), dtype=float)

        corrector = FakeCorrector(
            2,
            parse_residual_config({
                'resmarl_enabled': True,
                'residual_alpha': 0.5,
                'residual_action_mask': {'dhw': False, 'ele': True, 'tmp': False},
            }),
        )
        a_base = np.zeros(6, dtype=float)
        out = corrector.correct(a_base, action_low=np.full(6, -1.0), action_high=np.full(6, 1.0))
        # 仅 ELE 维（index 1, 4）变为 0.5
        expected = np.array([0.0, 0.5, 0.0, 0.0, 0.5, 0.0])
        np.testing.assert_allclose(out, expected, atol=1e-12)
        self.assertTrue(corrector.last_trace.applied)


if __name__ == '__main__':
    unittest.main(verbosity=2)
