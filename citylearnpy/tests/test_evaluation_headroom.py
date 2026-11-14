import copy
import unittest

from evaluation_headroom import compute_headroom


def evidence(bill, d=.02, algorithm='CHESCA'):
    return {'task_id': algorithm + str(bill), 'algorithm': algorithm,
            'protocol': {'building_ids': ['B1'], 'simulation_window': [0, 99], 'data': 'same'},
            'per_building': {'B1': {'positive_bill': bill, 'discomfort_proportion': d,
                                    'occupied_samples': 20, 'terminal_state': {'battery_soc': .5},
                                    'service_diagnostics': {'unserved_energy': 0.}}}}


class HeadroomTest(unittest.TestCase):
    def test_verified_saving_and_observed_remaining_are_not_a_global_optimality_claim(self):
        report = compute_headroom(evidence(85), evidence(100, algorithm='NoControl'), evidence(80))
        self.assertEqual(report['verified_saving'], 15)
        self.assertEqual(report['verified_saving_fraction'], .15)
        self.assertEqual(report['observed_candidate_delta'], 5)
        self.assertIsNone(report['optimistic_bound'])
        self.assertIn('whole_building_remaining_unknown', report['unknown_reasons'])

    def test_zero_bill_negative_saving_and_failed_comfort_are_not_hidden(self):
        current = evidence(5, d=.10)
        current['per_building']['B1']['terminal_state']['battery_soc'] = .1
        report = compute_headroom(current, evidence(0, algorithm='NoControl'))
        self.assertEqual(report['verified_saving'], -5)
        self.assertIsNone(report['verified_saving_fraction'])
        self.assertFalse(report['current_comfort_qualified'])
        self.assertAlmostEqual(report['terminal_deltas']['B1']['battery_soc'], -.4)

    def test_wrong_protocol_invalid_bill_or_non_nocontrol_reference_is_unavailable(self):
        current, baseline = evidence(85), evidence(100, algorithm='NoControl')
        for mutation in ('protocol', 'nan', 'identity'):
            changed = copy.deepcopy(baseline)
            if mutation == 'protocol': changed['protocol']['simulation_window'] = [1, 100]
            if mutation == 'nan': changed['per_building']['B1']['positive_bill'] = float('nan')
            if mutation == 'identity': changed['algorithm'] = 'Anchor'
            report = compute_headroom(current, changed)
            self.assertEqual(report['status'], 'unavailable')
            self.assertIsNone(report['verified_saving'])

    def test_fixed_load_battery_bound_never_becomes_whole_building_headroom(self):
        bound = {'status': 'verified', 'scope': 'fixed_load_battery', 'lower_bill': 65}
        report = compute_headroom(evidence(85), evidence(100, algorithm='NoControl'), evidence(80), bound)
        self.assertIsNone(report['optimistic_bound'])
        self.assertIn('conditional_bound_not_whole_building', report['unknown_reasons'])

    def test_nocontrol_reference_can_have_different_information_access_but_is_labeled(self):
        current = evidence(85)
        baseline = evidence(100, algorithm='NoControl')
        current['protocol']['information_access'] = 'current_observations_and_local_history'
        baseline['protocol']['information_access'] = 'no_control_no_policy_observations'
        report = compute_headroom(current, baseline)
        self.assertEqual(report['status'], 'available')
        self.assertEqual(report['comparison_scope'], 'physical_protocol_only')
        self.assertIn('different_information_access_reference', report['unknown_reasons'])


if __name__ == '__main__':
    unittest.main()
