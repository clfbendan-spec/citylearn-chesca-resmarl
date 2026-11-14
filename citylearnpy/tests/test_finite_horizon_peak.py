import sys,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_causal_peak_controller import battery
from finite_horizon_peak_env import horizon_features,terminal_charge_action
from causal_peak_controller import battery_post_energy


class FiniteHorizonTests(unittest.TestCase):
    def test_horizon_boundary(self):
        self.assertEqual(float(horizon_features(0,720)[0]),1.)
        self.assertAlmostEqual(float(horizon_features(718,720)[1]),1/24,places=7)
        self.assertEqual(horizon_features(719,720).tolist(),[0.,0.])

    def test_reachable_final_target_without_state_mutation(self):
        s=battery();s.soc=[.55];s.energy_init=2.2;s.initial_soc=.2
        action,diag=terminal_charge_action(s,.03)
        self.assertTrue(diag['feasible']);self.assertTrue(diag['changed'])
        self.assertGreaterEqual(battery_post_energy(s,action*s.nominal_power),2.4)
        self.assertEqual(s.energy_init,2.2);self.assertEqual(s.soc,[.55])

    def test_sufficient_action_preserved(self):
        s=battery();s.initial_soc=.2
        action,diag=terminal_charge_action(s,0.)
        self.assertEqual(action,0.);self.assertFalse(diag['changed'])

    def test_infeasible_target_is_explicit(self):
        s=battery();s.initial_soc=.2;s.energy_init=2.;s.available_nominal_power=0
        action,diag=terminal_charge_action(s,0.)
        self.assertFalse(diag['feasible']);self.assertEqual(action,1.)


if __name__=='__main__':unittest.main()
