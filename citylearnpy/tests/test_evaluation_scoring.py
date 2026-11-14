import copy
import math
import unittest

from evaluation_scoring import compute_score, penalty, aggregate_online


def fixture():
    protocol = dict(dataset_files_sha256='dataset', simulation_window=[0, 99],
                    seconds_per_time_step=3600, building_ids=['B1', 'B2'],
                    equipment_sha256='equipment', initial_state_sha256='state',
                    evaluator_version='native-local', cost_definition='positive-step-cost',
                    information_access='current-and-declared-forecasts', warmup='none',
                    action_contract='dhw,battery,cooling', environment_step_order='apply_then_advance',
                    outage_model_sha256='dataset-outage-model')
    result = dict(protocol=protocol, policy_id='frozen-policy', per_building={
        'B1': dict(cost_total=.8, positive_bill=80., discomfort_proportion=.04, occupied_samples=100),
        'B2': dict(cost_total=2., positive_bill=200., discomfort_proportion=.05, occupied_samples=100)})
    anchor = copy.deepcopy(result)
    anchor.update(anchor_id='registered-reference', anchor_checkpoint_sha256='frozen-weights')
    anchor['per_building']['B1'].update(cost_total=1., positive_bill=100., discomfort_proportion=.05)
    anchor['per_building']['B2'].update(cost_total=2., positive_bill=200., discomfort_proportion=.05)
    return result, anchor


class EvaluationScoringTest(unittest.TestCase):
    def test_different_or_unrecorded_runtime_outage_models_cannot_be_ranked(self):
        result, anchor = fixture()
        result['protocol']['outage_model_sha256'] = 'legacy-forced-seed'
        self.assertIn('incomparable_protocol:outage_model_sha256',
                      compute_score(result, anchor)['reason_codes'])
        result['protocol'].pop('outage_model_sha256')
        self.assertIn('missing_protocol:outage_model_sha256',
                      compute_score(result, anchor)['reason_codes'])

    def test_different_executable_step_order_cannot_be_ranked_together(self):
        result, anchor = fixture()
        result['protocol']['environment_step_order'] = 'advance_then_apply'
        anchor['protocol']['environment_step_order'] = 'apply_then_advance'
        score = compute_score(result, anchor)
        self.assertFalse(score['rankable'])
        self.assertIn('incomparable_protocol:environment_step_order', score['reason_codes'])

    def test_piecewise_knots_and_ranges(self):
        for d, expected in ((0, 0), (3, 3), (5, 9), (8, 24), (10, 44), (100, 944)):
            self.assertEqual(penalty(d), expected)
        for d in (-1, 101, math.nan, math.inf):
            with self.assertRaises(ValueError):
                penalty(d)

    def test_buildings_are_scored_before_equal_weight_aggregation(self):
        result, anchor = fixture()
        score = compute_score(result, anchor)
        self.assertEqual(score['status'], 'available')
        self.assertTrue(score['rankable'])
        self.assertAlmostEqual(score['per_building']['B1']['cost_term'], -20.)
        self.assertEqual(score['per_building']['B1']['comfort_term'], -3.)
        self.assertAlmostEqual(score['score'], -11.5)
        self.assertAlmostEqual(score['cash_trial']['score'], -11.5)
        self.assertEqual([v['alpha'] for v in score['sensitivity']], [.5, 1., 2.])
        self.assertAlmostEqual(score['sensitivity'][0]['score'], -10.75)

    def test_anchor_compared_with_itself_is_zero(self):
        _, anchor = fixture()
        self.assertEqual(compute_score(anchor, anchor)['score'], 0.)

    def test_unqualified_anchor_remains_reference_but_cannot_qualify_itself(self):
        result, anchor = fixture()
        anchor['per_building']['B1']['discomfort_proportion'] = .2
        candidate = compute_score(result, anchor)
        self.assertEqual(candidate['status'], 'available')
        self.assertTrue(candidate['rankable'])
        self.assertFalse(candidate['anchor_comfort_qualified'])
        self.assertEqual(candidate['anchor_checkpoint_sha256'], 'frozen-weights')
        self_reference = compute_score(anchor, anchor)
        self.assertEqual(self_reference['score'], 0.)
        self.assertFalse(self_reference['rankable'])

    def test_exact_ten_percent_has_diagnostic_score_but_cannot_rank(self):
        result, anchor = fixture()
        result['per_building']['B1']['discomfort_proportion'] = .10
        score = compute_score(result, anchor)
        self.assertEqual(score['status'], 'available')
        self.assertFalse(score['comfort_qualified'])
        self.assertFalse(score['rankable'])
        self.assertIsNotNone(score['score'])

    def test_missing_nonfinite_and_incomparable_inputs_have_no_score(self):
        for mutation in ('no_anchor', 'zero_denominator', 'nan_denominator', 'no_occupancy',
                         'missing_protocol', 'other_initial_state', 'missing_building',
                         'bad_d', 'empty_buildings', 'invalid_alpha'):
            result, anchor = fixture()
            alpha = 1.
            if mutation == 'no_anchor': anchor = None
            elif mutation == 'zero_denominator': anchor['per_building']['B1']['cost_total'] = 0.
            elif mutation == 'nan_denominator': anchor['per_building']['B1']['cost_total'] = math.nan
            elif mutation == 'no_occupancy': result['per_building']['B1']['occupied_samples'] = 0
            elif mutation == 'missing_protocol': result['protocol'].pop('evaluator_version')
            elif mutation == 'other_initial_state': result['protocol']['initial_state_sha256'] = 'other'
            elif mutation == 'missing_building': result['per_building'].pop('B2')
            elif mutation == 'bad_d': result['per_building']['B1']['discomfort_proportion'] = -1
            elif mutation == 'empty_buildings': result['per_building'] = {}
            elif mutation == 'invalid_alpha': alpha = math.inf
            with self.subTest(mutation=mutation):
                score = compute_score(result, anchor, alpha)
                self.assertFalse(score['rankable'])
                self.assertIsNone(score['score'])
                self.assertTrue(score['reason_codes'])

    def test_missing_cash_does_not_destroy_valid_native_score(self):
        result, anchor = fixture()
        result['per_building']['B1'].pop('positive_bill')
        score = compute_score(result, anchor)
        self.assertEqual(score['status'], 'available')
        self.assertIsNone(score['cash_trial']['score'])

    def test_finite_inputs_cannot_produce_infinite_scores(self):
        result, anchor = fixture()
        result['per_building']['B1']['cost_total'] = 1.e308
        anchor['per_building']['B1']['cost_total'] = 1.e-308
        score = compute_score(result, anchor)
        self.assertEqual(score['status'], 'unavailable')
        self.assertIsNone(score['score'])

    def test_unhashable_building_ids_are_unavailable_instead_of_crashing(self):
        result, anchor = fixture()
        result['protocol']['building_ids'] = [['B1'], ['B2']]
        self.assertEqual(compute_score(result, anchor)['status'], 'unavailable')

    def test_online_requires_all_scenes_same_policy_and_matching_buildings(self):
        result, anchor = fixture()
        score = compute_score(result, anchor)
        score['policy_id'] = result['policy_id']
        scenes = {name: copy.deepcopy(score) for name in ('online1', 'online2', 'online3')}
        self.assertAlmostEqual(aggregate_online(scenes)['score'], -11.5)
        self.assertIsNone(aggregate_online({'online1': score})['score'])
        scenes['online3']['policy_id'] = 'picked-different-policy'
        self.assertIsNone(aggregate_online(scenes)['score'])
        scenes['online3']['policy_id'] = result['policy_id']
        scenes['online3']['per_building'].pop('B2')
        self.assertIsNone(aggregate_online(scenes)['score'])


if __name__ == '__main__':
    unittest.main()
