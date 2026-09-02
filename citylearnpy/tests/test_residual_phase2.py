"""
阶段 2 回归测试：state_builder / policy / corrector 加载 checkpoint。

运行：
  cd citylearnpy
  D:\\Users\\clfbe\\anaconda3\\envs\\cl2\\python.exe tests/test_residual_phase2.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
CHESCA = ROOT / 'CHESCA-copy'
sys.path.insert(0, str(CHESCA))
sys.path.insert(0, str(ROOT))

from checa.residual import ResidualCorrector, parse_residual_config  # noqa: E402
from checa.residual.policy import ResidualActorCritic  # noqa: E402
from checa.residual.state_builder import build_residual_state, residual_state_dim  # noqa: E402


class TestResidualPhase2(unittest.TestCase):
    def test_state_dim_formula(self):
        self.assertEqual(residual_state_dim(3), 3 + 6 * 3)

    def test_build_residual_state_shape(self):
        n = 3
        a_base = np.zeros(9, dtype=np.float32)
        state = build_residual_state(
            n,
            a_base,
            chesca_state={
                'hour': 12,
                'cur_battery_soc': [0.5, 0.4, 0.6],
                'cur_dhw_soc': [0.2, 0.3, 0.1],
                'net_load_mean': [1.0, 2.0, 0.5],
            },
        )
        self.assertEqual(state.shape, (residual_state_dim(n),))
        self.assertEqual(state.dtype, np.float32)

    def test_policy_save_load_and_act(self):
        n = 3
        dim = residual_state_dim(n)
        policy = ResidualActorCritic(dim, n)
        state = np.zeros(dim, dtype=np.float32)
        delta, log_prob, value = policy.act(state, deterministic=True)
        self.assertEqual(delta.shape, (n,))
        self.assertTrue(np.all(np.abs(delta) <= 1.0 + 1e-5))
        self.assertIsNone(log_prob)
        self.assertIsNotNone(value)

        delta_s, log_prob_s, _ = policy.act(state, deterministic=False)
        self.assertEqual(delta_s.shape, (n,))
        self.assertIsNotNone(log_prob_s)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'policy.pt'
            policy.save(path)
            loaded = ResidualActorCritic.load(path)
            d2, _, _ = loaded.act(state, deterministic=True)
            np.testing.assert_allclose(d2, delta, atol=1e-5)

    def test_corrector_loads_policy_and_changes_ele(self):
        n = 2
        dim = residual_state_dim(n)
        policy = ResidualActorCritic(dim, n)
        with torch.no_grad():
            policy.actor[-1].bias.fill_(0.8)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'policy.pt'
            policy.save(path)

            corrector = ResidualCorrector.from_params(
                n,
                {
                    'resmarl_enabled': True,
                    'residual_alpha': 0.5,
                    'residual_action_mask': {'dhw': False, 'ele': True, 'tmp': False},
                    'resmarl_policy_path': str(path),
                },
            )
            self.assertIsNotNone(corrector.policy)
            a_base = np.zeros(6, dtype=float)
            out = corrector.correct(
                a_base,
                chesca_state={
                    'hour': 10,
                    'cur_battery_soc': [0.5, 0.5],
                    'cur_dhw_soc': [0.2, 0.2],
                    'net_load_mean': [1.0, 1.0],
                },
                action_low=np.full(6, -1.0),
                action_high=np.full(6, 1.0),
            )
            self.assertAlmostEqual(out[0], 0.0, places=5)
            self.assertAlmostEqual(out[2], 0.0, places=5)
            self.assertNotAlmostEqual(out[1], 0.0, places=3)
            self.assertTrue(corrector.last_trace.applied)
            self.assertTrue(corrector.last_trace.policy_loaded)

    def test_parse_policy_path(self):
        cfg = parse_residual_config({'resmarl_policy_path': '  /tmp/a.pt  '})
        self.assertEqual(cfg.policy_path, '/tmp/a.pt')
        cfg2 = parse_residual_config({'resmarl_policy_path': '   '})
        self.assertIsNone(cfg2.policy_path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
