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
from utils.ches_config import load_agent_config  # noqa: E402


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


class TestResidualGate(unittest.TestCase):
    """
    P0 门控：α>0 时，命中「停电 / SOC 触界」的楼栋本步必须严格恒等（a_final 逐位 == a_base）。

    判据在 checa.residual.config.evaluate_residual_gate 里只有一份，
    两条残差实现（SAC additive / PPO additive）都调它 ⇒ 这里用基类覆盖 predict_delta 即可验接线。
    """

    N = 3
    ACT = 9
    BASE = [0.1, -0.3, 0.5, 0.0, 0.2, 0.0, -0.83, 0.0, 0.4]

    def _make(self, **overrides):
        """构造「已加载策略 + α=0.3」的残差器（predict_delta 恒返回 0.5，便于看门控效果）。"""
        n = self.N

        class FakeCorrector(ResidualCorrector):
            def predict_delta(self, a_base, observations=None, chesca_state=None):
                return np.full(3 * n, 0.5, dtype=float)

        params = {'resmarl_enabled': True, 'residual_alpha': 0.3}
        params.update(overrides)
        corrector = FakeCorrector(n, parse_residual_config(params))
        corrector.policy = object()  # 假装已加载策略 ⇒ 走"真正生效"那条分支
        return corrector

    @staticmethod
    def _state(soc, outage, lo=0.1):
        return {
            'cur_battery_soc': list(soc),
            'min_battery_soc': [lo] * len(soc),
            'outage': list(outage),
        }

    def _expect(self, applied_buildings):
        """按「哪些楼栋放行残差」给出期望动作：放行楼栋的 ELE 维 +α·span·Δa，其余严格等于 a_base。"""
        exp = np.array(self.BASE, dtype=float)
        for b in applied_buildings:
            exp[3 * b + 1] += 0.3 * 1.0 * 0.5
        return exp

    def _correct(self, corrector, state):
        a_base = np.array(self.BASE, dtype=float)
        out = corrector.correct(
            a_base,
            chesca_state=state,
            action_low=np.full(self.ACT, -1.0),
            action_high=np.full(self.ACT, 1.0),
        )
        return a_base, np.asarray(out, dtype=float)

    def test_outage_mutes_every_building(self):
        corrector = self._make()
        a_base, out = self._correct(corrector, self._state([0.5] * 3, [True] * 3))
        np.testing.assert_allclose(out, a_base, rtol=0, atol=1e-12)
        self.assertEqual(corrector.last_trace.skip_reason, 'gated')
        self.assertEqual(corrector.last_trace.gate_reason, 'outage×3')
        self.assertEqual(list(corrector.last_trace.gate), [0.0] * self.ACT)

    def test_soc_high_mutes_only_that_building(self):
        corrector = self._make()
        _, out = self._correct(corrector, self._state([0.5, 0.985, 0.5], [False] * 3))
        # 只有 Building_2（维 3/4/5）触上界 ⇒ 该楼栋 ELE 维保持 a_base，另两栋照常 +0.15
        np.testing.assert_allclose(out, self._expect([0, 2]), atol=1e-12)
        self.assertEqual(corrector.last_trace.gate_reason, 'soc_high×1')

    def test_soc_low_mutes_that_building(self):
        corrector = self._make()
        _, out = self._correct(corrector, self._state([0.5, 0.11, 0.5], [False] * 3, lo=0.1))
        self.assertEqual(corrector.last_trace.gate_reason, 'soc_low×1')
        np.testing.assert_allclose(out, self._expect([0, 2]), atol=1e-12)

    def test_outage_ceiling_is_tighter_than_normal(self):
        """停电时上界收紧到 max_soc_outage(0.87)：SOC=0.88 正常不触界、停电触界。"""
        normal = self._make(residual_gate_outage=False)
        self._correct(normal, self._state([0.88] * 3, [False] * 3))
        self.assertEqual(normal.last_trace.gate_reason, 'none')

        outage = self._make(residual_gate_outage=False)
        self._correct(outage, self._state([0.88] * 3, [True] * 3))
        self.assertEqual(outage.last_trace.gate_reason, 'soc_high×3')

    def test_gate_disabled_keeps_residual(self):
        corrector = self._make(residual_gate_enabled=False)
        _, out = self._correct(corrector, self._state([0.99] * 3, [True] * 3))
        np.testing.assert_allclose(out, self._expect([0, 1, 2]), atol=1e-12)
        self.assertEqual(corrector.last_trace.gate_reason, 'none')

    def test_both_rules_can_be_disabled(self):
        corrector = self._make(residual_gate_outage=False, residual_gate_soc_bound=False)
        _, out = self._correct(corrector, self._state([0.5] * 3, [True] * 3))
        np.testing.assert_allclose(out, self._expect([0, 1, 2]), atol=1e-12)

    def test_missing_state_is_reported_not_assumed(self):
        """缺 cur_battery_soc 时 SOC 规则显式跳过（不误关残差），且原因可追溯 ✗。"""
        corrector = self._make()
        _, out = self._correct(corrector, {'outage': [False] * 3})
        self.assertEqual(corrector.last_trace.gate_reason, 'no_state×3')
        np.testing.assert_allclose(out, self._expect([0, 1, 2]), atol=1e-12)


if __name__ == '__main__':
    unittest.main(verbosity=2)
