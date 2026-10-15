"""
阶段 4 回归测试：残差侧**可学习门控**（gate_head）的恒等性与作用范围。

守三件事：
1. 默认 `gate_mode='binary'` ⇒ 与改动前逐位相同（零侵入）；
2. `gate_mode='learned'` + 恒等参数（k=0）或 strength=0 ⇒ 同样逐位相同（恒等点）；
3. `learned` + 有效参数 ⇒ **只**改动 gate_axis 指定的动作维，且缺触发信号时不乱削。

运行：
  cd citylearnpy
  D:\\Users\\clfbe\\anaconda3\\envs\\cl2\\python.exe -m unittest tests.test_residual_phase4 -v
或：
  D:\\Users\\clfbe\\anaconda3\\envs\\cl2\\python.exe tests/test_residual_phase4.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CHESCA = ROOT / 'CHESCA-copy'
sys.path.insert(0, str(CHESCA))
sys.path.insert(0, str(ROOT))

from checa.residual import ResidualCorrector, parse_residual_config  # noqa: E402
from checa.residual.gate_head import (  # noqa: E402
    CoolingGateHead, ParametricCausalGate, apply_gate, build_gate_features,
    gate_axis_indices, maybe_apply_learned_gate,
)

A_BASE = [-0.5, 0.2, 0.7, -0.3, 0.1, 0.6, 0.0, -1.0, 0.9]
STATE = {
    'cur_battery_soc': [0.5, 0.5, 0.5],
    'min_battery_soc': [0.2, 0.2, 0.2],
    'outage': [False, False, False],
    'non_shiftable_load': [1.0, 6.0, 1.0],
    'non_shiftable_load_mean': [1.0, 1.0, 1.0],
    'net_load_mean': [2.0, 2.0, 2.0],
    'hour': 21,
}


class TestGateIdentity(unittest.TestCase):
    """恒等性：门控"关"时必须逐位等于基线。"""

    def test_binary_mode_is_identity(self):
        """默认 binary 模式：ResidualCorrector 逐位返回 a_base。"""
        cfg = parse_residual_config({})
        self.assertEqual(cfg.gate_mode, 'binary')
        out = ResidualCorrector(3, cfg).correct(list(A_BASE), chesca_state=STATE)
        np.testing.assert_allclose(np.asarray(out), np.asarray(A_BASE), atol=0, rtol=0)

    def test_learned_with_k0_is_identity(self):
        """learned + k=0（恒等锚点）：仍逐位等于 a_base，且 g≡1。"""
        cfg = parse_residual_config({
            'resmarl_enabled': True, 'residual_alpha': 0.3,
            'residual_gate_mode': 'learned',
            'residual_gate_params': {'k': 0.0},
        })
        rc = ResidualCorrector(3, cfg)
        out = rc.correct(list(A_BASE), chesca_state=STATE)
        np.testing.assert_allclose(np.asarray(out), np.asarray(A_BASE), atol=1e-12, rtol=0)
        np.testing.assert_allclose(np.asarray(rc.last_trace.gate_learned), 1.0)

    def test_strength_zero_is_identity(self):
        """strength=0 ⇒ g≡1（可关闭旋钮），即使参数很激进。"""
        cfg = parse_residual_config({
            'resmarl_enabled': True, 'residual_alpha': 0.3,
            'residual_gate_mode': 'learned', 'residual_gate_strength': 0.0,
            'residual_gate_params': {'k': 1.0, 'tau': 0.01, 'w': 0.01},
        })
        out = ResidualCorrector(3, cfg).correct(list(A_BASE), chesca_state=STATE)
        np.testing.assert_allclose(np.asarray(out), np.asarray(A_BASE), atol=1e-12, rtol=0)

    def test_maybe_gate_returns_none_for_binary(self):
        """binary ⇒ maybe_apply_learned_gate 返回 (None, ...)，调用方走原路径。"""
        fin, _ = maybe_apply_learned_gate(A_BASE, parse_residual_config({}), chesca_state=STATE)
        self.assertIsNone(fin)


class TestGateScope(unittest.TestCase):
    """作用范围：只动 gate_axis 指定的维，且缺信号不乱削。"""

    def test_apply_gate_only_touches_axis(self):
        out, applied = apply_gate(A_BASE, [0.5, 0.5, 0.5], axis='tmp')
        self.assertEqual(sorted(np.where(applied)[0].tolist()), [2, 5, 8])
        self.assertAlmostEqual(out[2], 0.7 * 0.5)
        self.assertEqual(gate_axis_indices(3, 'tmp').tolist(), [2, 5, 8])

    def test_identity_g_leaves_base_untouched(self):
        out, applied = apply_gate(A_BASE, np.ones(3), axis='tmp')
        np.testing.assert_allclose(out, np.asarray(A_BASE), atol=0, rtol=0)
        self.assertEqual(int(applied.sum()), 0)

    def test_learned_cuts_only_cooling_dims(self):
        cfg = parse_residual_config({
            'resmarl_enabled': True, 'residual_alpha': 0.3,
            'residual_gate_mode': 'learned',
            'residual_gate_params': {'k': 1.0, 'tau': 0.2, 'w': 0.5},
        })
        out = ResidualCorrector(3, cfg).correct(list(A_BASE), chesca_state=STATE)
        touched = np.where(np.abs(np.asarray(out) - np.asarray(A_BASE)) > 1e-9)[0].tolist()
        self.assertEqual(touched, [2, 5, 8])

    def test_missing_trigger_keeps_g_one(self):
        """没有任何不可调负荷信号 ⇒ g≡1（不乱削）。"""
        st = dict(STATE)
        st['non_shiftable_load'] = None
        st['non_shiftable_load_mean'] = None
        cfg = parse_residual_config({
            'resmarl_enabled': True, 'residual_alpha': 0.3,
            'residual_gate_mode': 'learned',
            'residual_gate_params': {'k': 1.0, 'tau': 0.2, 'w': 0.01},
        })
        fin, diag = maybe_apply_learned_gate(A_BASE, cfg, chesca_state=st)
        np.testing.assert_allclose(np.asarray(diag['g']), 1.0)
        np.testing.assert_allclose(np.asarray(fin), np.asarray(A_BASE), atol=0, rtol=0)


class TestGateFeatures(unittest.TestCase):
    """特征构造与先验曲线。"""

    def test_ns_ratio_matches_definition(self):
        feats, has = build_gate_features(3, A_BASE, chesca_state=STATE)
        np.testing.assert_allclose(feats[:, 0], [1.0, 6.0, 1.0], rtol=1e-5)
        self.assertTrue(bool(has.all()))

    def test_parametric_reproduces_probe_rule(self):
        """k=1,tau=3,w→0 即探针规则：ratio>3 ⇒ g=0。"""
        gate = ParametricCausalGate(k=1.0, tau=3.0, w=1e-6)
        feats = np.zeros((4, 10), dtype=np.float32)
        feats[:, 0] = [0.5, 2.9, 3.1, 6.0]
        np.testing.assert_allclose(gate.factors(feats), [1.0, 1.0, 0.0, 0.0], atol=1e-6)

    def test_mlp_head_anchors_to_prior(self):
        """MLP 头（零初始化增量）初始逐点等于参数化先验 ⇒ 可热启动。"""
        prior = ParametricCausalGate(k=1.0, tau=3.0, w=1.0)
        head = CoolingGateHead(3, prior=prior)
        feats = np.zeros((3, 10), dtype=np.float32)
        feats[:, 0] = [0.5, 3.5, 6.0]
        np.testing.assert_allclose(head.factors(feats), prior.factors(feats), atol=1e-6)


if __name__ == '__main__':
    unittest.main(verbosity=2)
