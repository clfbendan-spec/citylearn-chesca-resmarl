import csv
import json
import tempfile
import unittest
from pathlib import Path

from aacmadrl.task import (resolve_checkpoint, select_checkpoint, export_kpis,
                              comparison_score, validate_window, no_control_baseline_costs)


class AACPlatformContractTest(unittest.TestCase):
    def test_piecewise_selector_uses_training_results_not_lower_cost_or_online(self):
        import copy
        from tests.test_evaluation_scoring import fixture
        _, anchor = fixture()
        results = {}
        rows = []
        for episode, cost_ratio, discomfort in ((1, .85, .08), (2, .9, .04)):
            result = copy.deepcopy(anchor)
            for metrics in result['per_building'].values():
                metrics['cost_total'] *= cost_ratio
                metrics['discomfort_proportion'] = discomfort
            results[episode] = result
            summary = copy.deepcopy(result['per_building'])
            for metrics in summary.values():
                metrics['electricity_consumption_total'] = .95
            rows.append({'episode': episode, 'updates': episode,
                         'training_local_per_building': summary,
                         'per_building': {'fake_online': {
                             'cost_total': 0 if episode == 1 else 999,
                             'discomfort_proportion': 0}}})
        self.assertEqual(select_checkpoint(rows, .1)['episode'], 1)
        selected = select_checkpoint(rows, .1, selector='piecewise',
                                     anchor=anchor, local_results=results)
        self.assertEqual(selected['episode'], 2)
        self.assertAlmostEqual(selected['selection_value'], -13.)
        self.assertEqual(selected['selection_metric'], 'piecewise')
        results[2]['protocol']['information_access'] = 'other-access'
        with self.assertRaises(ValueError):
            select_checkpoint(rows, .1, selector='piecewise',
                              anchor=anchor, local_results=results)

    def test_initialization_rejects_ignored_or_wrong_hash_sources_before_any_training(self):
        from aacmadrl.task import parser, resolve_initialization
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkpoint = root / 'historical.pt'
            checkpoint.write_bytes(b'known-historical-weights')
            flags = ['--output-dir', str(root / 'task'), '--init-checkpoint', str(checkpoint)]
            args = parser('train').parse_args(flags + ['--expected-init-sha256', '0' * 64])
            with self.assertRaises(ValueError):
                resolve_initialization(args)
            args = parser('train').parse_args(flags + ['--warm-start-anchor', 'off'])
            with self.assertRaises(ValueError):
                resolve_initialization(args)
            expected = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
            args = parser('train').parse_args(flags + ['--expected-init-sha256', expected])
            resolved = resolve_initialization(args)
            self.assertEqual(resolved['initialization_source'], 'explicit_checkpoint')
            self.assertEqual(resolved['initialization_checkpoint_sha256'], expected)
            self.assertEqual(Path(resolved['initialization_checkpoint']), checkpoint)

    def test_piecewise_reference_must_be_registered_and_pinned_before_training(self):
        import hashlib
        import os
        from unittest.mock import patch
        from tests.test_evaluation_scoring import fixture
        from evaluation_contract import register_anchor
        from aacmadrl.task import parser, resolve_selection_anchor
        _, reference = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = root / 'result.json'
            result.write_text(json.dumps(reference), encoding='utf-8')
            weights = root / 'weights.pt'
            weights.write_bytes(b'predeclared-reference')
            args = parser('train').parse_args([
                '--output-dir', str(root / 'task'), '--selector', 'piecewise',
                '--selection-anchor-result', str(result)])
            with patch.dict(os.environ, {'CITYLEARN_ANCHOR_REGISTRY': str(root / 'registry')}):
                with self.assertRaises(ValueError):
                    resolve_selection_anchor(args)
                register_anchor(root / 'registry', 'local-reference', result, weights,
                                expected_checkpoint_sha256=hashlib.sha256(weights.read_bytes()).hexdigest())
                loaded = resolve_selection_anchor(args)
                self.assertEqual(loaded['anchor_id'], 'local-reference')
                result.write_text(json.dumps({**reference, 'changed': True}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    resolve_selection_anchor(args)

    def test_model_resolution_uses_parent_train_child_and_never_other_global_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / 'parent-train/checkpoints/aacmadrl/model.pt'
            model.parent.mkdir(parents=True)
            model.write_bytes(b'owned-model')
            (model.parent / 'model_manifest.json').write_text(json.dumps({
                'algorithm': 'AACMADRL', 'checkpoint': 'model.pt'}))
            self.assertEqual(resolve_checkpoint(root, 'parent'), model)
            self.assertEqual(resolve_checkpoint(root, 'parent-train'), model)
            with self.assertRaises(FileNotFoundError):
                resolve_checkpoint(root, 'missing')
            with self.assertRaises(ValueError):
                resolve_checkpoint(root, '../escape')

    def test_checkpoint_choice_prefers_comfort_then_cost_and_ignores_online(self):
        rows = [
            {'episode': 0, 'updates': 0, 'per_building': {'B1': {'cost_total': .5, 'discomfort_proportion': .01}}},
            {'episode': 1, 'updates': 1, 'per_building': {'B1': {'cost_total': .6, 'discomfort_proportion': .10}}},
            {'episode': 2, 'updates': 2, 'per_building': {'B1': {'cost_total': .9, 'discomfort_proportion': .08}},
             'training_local_per_building': {'B1': {'cost_total': .85, 'discomfort_proportion': .05}}},
            {'episode': 3, 'updates': 3, 'per_building': {'B1': {'cost_total': .4, 'discomfort_proportion': .01}},
             'training_local_per_building': {'B1': {'cost_total': .95, 'discomfort_proportion': .05}}},
        ]
        selected = select_checkpoint(rows, .1)
        self.assertEqual(selected['episode'], 2)
        self.assertTrue(selected['comfort_qualified'])
        self.assertEqual(selected['mean_cost'], .85)

    def test_no_comfort_qualified_checkpoint_is_flagged_not_silently_passed(self):
        rows = [{'episode': 1, 'updates': 5, 'per_building': {
            'B1': {'cost_total': .8, 'discomfort_proportion': .2}}}]
        self.assertFalse(select_checkpoint(rows, .1)['comfort_qualified'])
        with self.assertRaises(ValueError):
            select_checkpoint([dict(rows[0], updates=0)], .1)

    def test_export_preserves_precision_and_null_does_not_become_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = {'official_kpi': [
                {'name': 'Building_1', 'cost_function': 'cost_total', 'value': .850113234567},
                {'name': 'District', 'cost_function': 'thermal_resilience_proportion', 'value': None}]}
            export_kpis(result, Path(tmp))
            with (Path(tmp) / 'exported_kpis.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]['Building_1'], '0.850113234567')
            self.assertEqual(rows[1]['District'], '')

    def test_legacy_partial_evidence_cannot_become_a_formal_score(self):
        result = {'dataset_sha256': 'abc', 'simulation_window': [0, 719],
                  'per_building': {'B1': {'cost_total': .8, 'discomfort_proportion': .04}}}
        anchor = {'dataset_sha256': 'abc', 'simulation_window': [0, 719],
                  'per_building': {'B1': {'cost_total': 1., 'discomfort_proportion': .05}}}
        with self.assertRaises(ValueError):
            comparison_score(result, anchor, 1)

    def test_aac_score_uses_shared_protocol_and_rejects_nonfinite_denominator(self):
        from tests.test_evaluation_scoring import fixture
        result, anchor = fixture()
        self.assertAlmostEqual(comparison_score(result, anchor, 1)['score'], -11.5)
        anchor['per_building']['B1']['cost_total'] = float('nan')
        with self.assertRaises(ValueError):
            comparison_score(result, anchor, 1)

    def test_window_validates_dataset_limits_and_honors_nonzero_start(self):
        self.assertEqual(validate_window({'simulation_start_time_step': 24, 'simulation_end_time_step': 95}, None, 0), (24, 95))
        self.assertEqual(validate_window({'simulation_start_time_step': 24, 'simulation_end_time_step': 95}, None, 32), (24, 55))
        with self.assertRaises(ValueError):
            validate_window({'simulation_start_time_step': 24, 'simulation_end_time_step': 95}, 0, 32)

    def test_reference_cost_is_read_only_after_complete_no_control_rollout(self):
        class Building:
            name = 'B1'
            active_actions = ['dhw_storage', 'electrical_storage', 'cooling_device']
            net_electricity_consumption_cost_without_storage_and_partial_load = [-0.1, 0.2, 0.3]

        class Env:
            buildings = [Building()]
            def reset(self):
                self.steps = 0
            def step(self, actions):
                self.assert_zero_actions(actions)
                self.steps += 1
                return None, None, self.steps == 2, False, None
            @staticmethod
            def assert_zero_actions(actions):
                if actions != [[0.0, 0.0, 0.0]]:
                    raise AssertionError(actions)

        self.assertEqual(no_control_baseline_costs(Env(), (0, 2), 2), {'B1': 0.5})

    def test_reference_cost_rejects_incomplete_rollout(self):
        class Env:
            buildings = []
            def reset(self):
                pass
            def step(self, actions):
                return None, None, False, False, None

        with self.assertRaises(RuntimeError):
            no_control_baseline_costs(Env(), (0, 2), 2)

    def test_dataset_resolution_prefers_the_aac_compatible_workspace_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compatible = root / 'datasets' / 'toy'
            incompatible = root / 'project/citylearnpy/CHESCA-copy/data/schemas/toy'
            compatible.mkdir(parents=True)
            incompatible.mkdir(parents=True)
            (compatible / 'schema.json').write_text('{"source":"canonical"}')
            (incompatible / 'schema.json').write_text('{"source":"formatted"}')
            from aacmadrl.task import resolve_dataset
            self.assertEqual(resolve_dataset('toy', root / 'project/citylearnpy').joinpath('schema.json').read_text(),
                             '{"source":"canonical"}')


if __name__ == '__main__':
    unittest.main()
