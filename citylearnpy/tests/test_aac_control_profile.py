import argparse
import unittest

from aacmadrl.control_profiles import HISTORICAL_PROFILE, configure_profile
from aacmadrl.task import parser


class HistoricalControlProfileTest(unittest.TestCase):
    def test_task_accepts_explicit_profile(self):
        args = parser('train').parse_args(['--output-dir', 'unused', '--control-profile', HISTORICAL_PROFILE])
        self.assertEqual(args.control_profile, HISTORICAL_PROFILE)

    def test_profile_preserves_historical_scope_and_thresholds(self):
        args = argparse.Namespace(control_profile=HISTORICAL_PROFILE)
        configure_profile(args)
        self.assertTrue(args.freeze_cooling_policy)
        self.assertTrue(args.unoccupied_cooling_gate)
        self.assertEqual(args.unoccupied_cooling_gate_bins, 2)
        self.assertEqual(args.unoccupied_cooling_gate_training_min_unoccupied_steps, 5)
        self.assertEqual(args.unoccupied_cooling_gate_training_comfort_margin, 1.5)
        self.assertEqual(args.unoccupied_cooling_gate_training_max_demand, 2.)
        self.assertIsNone(args.unoccupied_cooling_gate_building_index)
        self.assertEqual(args.high_price_discharge_building_index, 1)
        self.assertEqual(args.high_price_discharge_post_soc_floor_override, .3)
        self.assertEqual(args.predicted_price_charge_rule_override, 'on')
        self.assertIsNone(args.predicted_price_charge_training_building_index)
        self.assertEqual(args.predicted_price_charge_training_max_current_price, .03025)
        self.assertEqual(args.predicted_price_charge_training_min_spread, .005)

    def test_default_profile_leaves_existing_behavior_unchanged(self):
        args = argparse.Namespace(control_profile='none', freeze_cooling_policy=False)
        configure_profile(args)
        self.assertEqual(vars(args), dict(control_profile='none', freeze_cooling_policy=False))


if __name__ == '__main__':
    unittest.main()
