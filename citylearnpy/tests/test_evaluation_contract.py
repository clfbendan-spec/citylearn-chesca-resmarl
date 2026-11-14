import copy
import json
from pathlib import Path
import tempfile
import unittest

import evaluation_contract as contract
from evaluation_contract import (validate_manifest, register_anchor, load_anchor,
                                 protocol_id, find_independent_nocontrol)


class EvaluationContractTest(unittest.TestCase):
    def test_publishing_uses_project_anchor_registry_when_no_override_is_supplied(self):
        from unittest.mock import patch
        from tests.test_evaluation_scoring import fixture
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / 'candidate'
            output.mkdir()
            self.manifest(output)
            result, anchor = fixture()
            for row in (result, anchor):
                row['protocol'] = dict(row['protocol'], simulation_window=[10, 12],
                                       building_ids=['B1'])
                row['per_building'].pop('B2')
                row['algorithm'] = 'Test'
            anchor_path = root / 'anchor.json'
            anchor_path.write_text(json.dumps(anchor), encoding='utf-8')
            checkpoint = root / 'model.pt'
            checkpoint.write_bytes(b'explicit-test-reference')
            registry = root / 'registry'
            register_anchor(registry, 'test-anchor', anchor_path, checkpoint,
                            expected_checkpoint_sha256=contract.file_sha256(checkpoint))
            context = dict(protocol=result['protocol'], runtime_versions={},
                           evaluation_sources_sha256={})
            with patch.object(contract, 'DEFAULT_ANCHOR_REGISTRY', registry, create=True):
                manifest = contract.finalize_recorded_evaluation(
                    result, context, output, True, task_id='candidate')
            self.assertEqual(manifest['artifact_status'], 'complete')
            score = json.loads((output / 'score_result.json').read_text(encoding='utf-8'))
            self.assertEqual(score['status'], 'available')
            self.assertEqual(score['anchor_id'], 'test-anchor')
            self.assertAlmostEqual(score['score'], -23.)

    def write_nocontrol(self, directory, result):
        manifest = self.manifest(directory)
        manifest.update(task_id=result['task_id'], algorithm='NoControl',
                        artifact_status='complete', protocol=result['protocol'])
        path = directory / 'evaluation_result.json'
        path.write_text(json.dumps(result), encoding='utf-8')
        manifest['artifacts'][path.name] = {
            'sha256': contract.file_sha256(path), 'bytes': path.stat().st_size}
        (directory / 'evaluation_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return manifest

    def manifest(self, directory):
        trace = directory / 'decision_trace.json'
        trace.write_text(json.dumps({'steps': [
            {'episode': 1, 'step': step, 'reward': [-1], 'info': {},
             'terminated': step == 11, 'truncated': False,
             'buildings': [{'building': 0, 'observations': {'hour': step},
                            'next_observations': {'hour': step + 1},
                            'actions': {'named': {}}}]} for step in (10, 11)
        ]}), encoding='utf-8')
        import hashlib
        return dict(schema_version=1, task_id='task', algorithm='test',
                    protocol={'simulation_window': [10, 12], 'building_ids': ['B1']},
                    artifacts={'decision_trace.json': {
                        'sha256': hashlib.sha256(trace.read_bytes()).hexdigest(),
                        'bytes': trace.stat().st_size}},
                    coverage={'expected_transitions': 2, 'recorded_transitions': 2,
                              'terminated': True, 'truncated': False})

    def test_real_artifact_hash_and_contiguous_step_coverage_are_required(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = self.manifest(root)
            self.assertTrue(validate_manifest(manifest, root)['valid'])
            (root / 'decision_trace.json').write_text('{}', encoding='utf-8')
            report = validate_manifest(manifest, root)
            self.assertFalse(report['valid'])
            self.assertIn('artifact_hash_mismatch:decision_trace.json', report['errors'])

    def test_parent_path_and_symlink_artifacts_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = self.manifest(root)
            manifest['artifacts']['../outside.json'] = {'sha256': 'x'}
            self.assertIn('unsafe_artifact_path:../outside.json', validate_manifest(manifest, root)['errors'])

    def test_missing_feedback_or_next_state_is_not_complete_even_with_all_steps(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = self.manifest(root)
            path = root / 'decision_trace.json'
            trace = json.loads(path.read_text())
            trace['steps'][0].pop('reward')
            trace['steps'][1]['buildings'][0].pop('next_observations')
            path.write_text(json.dumps(trace))
            import hashlib
            manifest['artifacts'][path.name]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            report = validate_manifest(manifest, root)
            self.assertFalse(report['valid'])
            self.assertIn('missing_transition_feedback', report['errors'])
            self.assertIn('missing_building_transition_evidence', report['errors'])

    def test_declared_counts_do_not_hide_missing_or_duplicated_transitions(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = self.manifest(root)
            path = root / 'decision_trace.json'
            trace = json.loads(path.read_text())
            trace['steps'][1]['step'] = 10
            path.write_text(json.dumps(trace))
            import hashlib
            manifest['artifacts'][path.name]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            report = validate_manifest(manifest, root)
            self.assertFalse(report['valid'])
            self.assertIn('noncontiguous_trace_steps', report['errors'])
            manifest['coverage']['terminated'] = False
            self.assertIn('incomplete_episode', validate_manifest(manifest, root)['errors'])

    def test_anchor_registration_verifies_weights_and_every_load_checks_result_hash(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            checkpoint = root / 'model.pt'
            checkpoint.write_bytes(b'not-the-frozen-model')
            result = root / 'evaluation_result.json'
            result.write_text(json.dumps({'protocol': {'dataset_files_sha256': 'data'},
                                          'per_building': {'B1': {'cost_total': 1}}}))
            with self.assertRaisesRegex(ValueError, 'anchor_checkpoint_hash_mismatch'):
                register_anchor(root / 'registry', 'anchor', result, checkpoint)
            # A separately approved protocol can explicitly pin another weight hash.
            import hashlib
            weight_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
            register_anchor(root / 'registry', 'anchor', result, checkpoint,
                            expected_checkpoint_sha256=weight_hash)
            current = load_anchor(root / 'registry', {'dataset_files_sha256': 'data'})
            self.assertEqual(current['anchor_id'], 'anchor')
            result.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'anchor_result_hash_mismatch'):
                load_anchor(root / 'registry', {'dataset_files_sha256': 'data'})

    def test_protocol_identity_is_order_independent_but_not_window_independent(self):
        self.assertEqual(protocol_id({'a': 1, 'b': 2}), protocol_id({'b': 2, 'a': 1}))
        self.assertNotEqual(protocol_id({'simulation_window': [0, 10]}),
                            protocol_id({'simulation_window': [1, 11]}))

    def test_independent_nocontrol_discovery_requires_one_complete_same_physical_protocol(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            candidate = root / 'candidate'
            baseline = root / 'baseline'
            candidate.mkdir()
            baseline.mkdir()
            protocol = {
                'dataset_files_sha256': {'load.csv': 'x'},
                'simulation_window': [10, 12],
                'seconds_per_time_step': 3600.,
                'building_ids': ['B1'],
                'equipment_sha256': 'e',
                'initial_state_sha256': 's',
                'evaluator_version': 'v',
                'cost_definition': 'c',
                'information_access': 'current',
                'warmup': 'none',
                'action_contract': {'cooling_device': {'active': True}},
                'environment_step_order': 'apply_then_advance',
            }
            result = {
                'task_id': 'baseline-task', 'algorithm': 'NoControl',
                'protocol': protocol,
                'per_building': {'B1': {'positive_bill': 10,
                                       'discomfort_proportion': .01,
                                       'occupied_samples': 1}},
            }
            self.write_nocontrol(baseline, result)
            self.assertEqual(find_independent_nocontrol(candidate, protocol)['task_id'],
                             'baseline-task')
            # A second matching baseline makes automatic selection ambiguous.
            duplicate = root / 'baseline-2'
            duplicate.mkdir()
            duplicate_result = dict(result, task_id='baseline-task-2')
            self.write_nocontrol(duplicate, duplicate_result)
            self.assertIsNone(find_independent_nocontrol(candidate, protocol))

    def test_nocontrol_discovery_rejects_corrupted_or_unverified_evidence(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            candidate, baseline = root / 'candidate', root / 'baseline'
            candidate.mkdir()
            baseline.mkdir()
            protocol = {'simulation_window': [10, 12], 'building_ids': ['B1']}
            result = dict(task_id='baseline', algorithm='NoControl', protocol=protocol,
                          per_building={'B1': {'positive_bill': 10}})
            for corruption in ('result_bytes', 'trace_bytes', 'unlisted_result',
                               'manifest_protocol', 'manifest_algorithm'):
                with self.subTest(corruption=corruption):
                    manifest = self.write_nocontrol(baseline, result)
                    if corruption == 'result_bytes':
                        changed = copy.deepcopy(result)
                        changed['per_building']['B1']['positive_bill'] = 1000
                        (baseline / 'evaluation_result.json').write_text(json.dumps(changed))
                    elif corruption == 'trace_bytes':
                        (baseline / 'decision_trace.json').write_text('{}')
                    elif corruption == 'unlisted_result':
                        manifest['artifacts'].pop('evaluation_result.json')
                    elif corruption == 'manifest_protocol':
                        manifest['protocol'] = dict(protocol, information_access='other')
                    else:
                        manifest['algorithm'] = 'Other'
                    (baseline / 'evaluation_manifest.json').write_text(json.dumps(manifest))
                    self.assertIsNone(find_independent_nocontrol(candidate, protocol))

    def test_real_environment_exports_unrounded_metrics_and_explicit_missing_anchor(self):
        from citylearn.citylearn import CityLearnEnv
        from assessment_trace import AssessmentTrace
        dataset = Path(__file__).resolve().parents[3] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1'
        schema = json.loads((dataset / 'schema.json').read_text())
        schema.update(root_directory=str(dataset), simulation_start_time_step=10,
                      simulation_end_time_step=12, episode_time_steps=None)
        env = CityLearnEnv(schema, central_agent=False)
        try:
            env.reset()
            capture = getattr(contract, 'capture_context', None)
            self.assertTrue(callable(capture), 'Reset-time protocol capture is missing')
            context = capture(env, information_access='test-current-observations', warmup='none')
            self.assertEqual(context['protocol']['simulation_window'], [10, 12])
            trace = AssessmentTrace(env, {'simulation_start_time_step': 10}, {'label': 'Test'})
            for _ in range(2):
                before = trace.before()
                action = [[0.] * len(building.active_actions) for building in env.buildings]
                transition = env.step(action)
                trace.record(before, action, transition)
            with tempfile.TemporaryDirectory() as name:
                root = Path(name)
                trace.save(root)
                manifest = contract.finalize_evaluation(env, context, root, 'Test', task_id='real-task')
                self.assertTrue(validate_manifest(manifest, root)['valid'])
                result = json.loads((root / 'evaluation_result.json').read_text(encoding='utf-8'))
                official = env.evaluate()
                for building in env.buildings:
                    row = result['per_building'][building.name]
                    value = official[(official['name'] == building.name)
                                     & (official['cost_function'] == 'cost_total')]['value'].iloc[0]
                    self.assertAlmostEqual(row['cost_total'], value, places=10)
                    self.assertGreater(row['occupied_samples'], 0)
                score = json.loads((root / 'score_result.json').read_text())
                self.assertIsNone(score['score'])
                self.assertIn('missing_anchor', score['reason_codes'])
                self.assertEqual(manifest['task_id'], 'real-task')
                self.assertEqual(manifest['physical_protocol_id'], contract.physical_protocol_id(manifest['protocol']))
                self.assertEqual(manifest['coverage']['recorded_transitions'], 2)
                self.assertIn('headroom_result.json', manifest['artifacts'])
                self.assertIn('runtime_audit.json', manifest['artifacts'])
                runtime = json.loads((root / 'runtime_audit.json').read_text(encoding='utf-8'))
                self.assertEqual(runtime['outages']['Building_1']['source_steps'], [10, 11, 12])
                self.assertGreater(runtime['equipment_at_reset']['Building_1']['cooling_device']['nominal_power'], 0)
                self.assertIn('ai_analysis_bundle.json', manifest['artifacts'])
                bundle = json.loads((root / 'ai_analysis_bundle.json').read_text(encoding='utf-8'))
                self.assertEqual(bundle['evidence']['task_id'], 'real-task')
                self.assertIn('B', json.dumps(bundle['evidence']['metrics']))
                changed = copy.deepcopy(context['protocol'])
                changed['simulation_window'] = [0, 2]
                self.assertNotEqual(manifest['protocol_id'], protocol_id(changed))
                replay_output = root / 'adapter'
                trace.save(replay_output)
                adapter = getattr(contract, 'finalize_recorded_evaluation', None)
                self.assertTrue(callable(adapter), 'Child-process evidence adapter is missing')
                adapted = adapter(result, context, replay_output, True, task_id='adapter-task')
                self.assertEqual(adapted['task_id'], 'adapter-task')
                self.assertEqual(adapted['artifact_status'], 'complete')
        finally:
            env.close()

    def test_protocol_fingerprint_ignores_runtime_component_uids_and_derived_optional_fields(self):
        from citylearn.citylearn import CityLearnEnv
        dataset = Path(__file__).resolve().parents[3] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1'
        contexts = []
        environments = []
        try:
            for _ in range(2):
                env = CityLearnEnv(
                    str(dataset / 'schema.json'),
                    central_agent=True,
                    simulation_start_time_step=0,
                    simulation_end_time_step=3,
                    random_seed=49,
                )
                env.reset()
                environments.append(env)
                contexts.append(contract.capture_context(env, information_access='test'))
            self.assertEqual(
                contexts[0]['protocol']['equipment_sha256'],
                contexts[1]['protocol']['equipment_sha256'],
            )
            self.assertEqual(
                contexts[0]['protocol']['initial_state_sha256'],
                contexts[1]['protocol']['initial_state_sha256'],
            )
        finally:
            for env in environments:
                env.close()


if __name__ == '__main__':
    unittest.main()
