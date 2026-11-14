import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.audit_algorithm_protocols import audit, compare, load_entry


class AlgorithmProtocolAuditTest(unittest.TestCase):
    def test_matching_protocol_does_not_assert_unchecked_ranking_gates(self):
        left = dict(label='a', status='available', protocol_id='same',
                    physical_protocol_id='physics', information_access='current',
                    manifest_valid=True)
        right = dict(left, label='b')
        pair = compare(left, right)
        self.assertFalse(pair['rankable'])
        self.assertTrue(pair['protocol_comparable'])
        self.assertEqual(pair['ranking_status'], 'not_assessed')
        self.assertEqual(audit([left, right])['conclusion'], 'protocol_comparable_group_exists')

    def test_invalid_or_unavailable_records_cannot_create_a_comparable_group(self):
        invalid = dict(label='a', status='available', protocol_id='same',
                       physical_protocol_id='physics', manifest_valid=False)
        unavailable = dict(label='b', status='unavailable', protocol_id='same', manifest_valid=True)
        report = audit([invalid, unavailable])
        self.assertFalse(report['pairs']['a__vs__b']['rankable'])
        self.assertEqual(report['conclusion'], 'no_multi_algorithm_valid_protocol_group')
        self.assertEqual(report['valid_full_protocol_groups'], [])

    def test_audit_separates_full_and_physical_protocols(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protocol = {
                'dataset_files_sha256': {'x': '1'},
                'simulation_window': [0, 2],
                'seconds_per_time_step': 3600.,
                'building_ids': ['B1'],
                'equipment_sha256': 'e',
                'initial_state_sha256': 's',
                'evaluator_version': 'v',
                'cost_definition': 'c',
                'information_access': 'current',
                'warmup': 'none',
                'action_contract': {'x': 1},
                'environment_step_order': 'apply_then_advance',
            }
            for name, info in (('a', 'current'), ('b', 'no_control')):
                item = dict(protocol, information_access=info)
                task = root / name
                task.mkdir()
                result = {
                    'task_id': name, 'algorithm': name,
                    'protocol': item,
                    'per_building': {'B1': {'positive_bill': 1,
                                           'discomfort_proportion': .01,
                                           'occupied_samples': 1}},
                }
                (task / 'evaluation_result.json').write_text(json.dumps(result), encoding='utf-8')
                (task / 'evaluation_manifest.json').write_text(json.dumps({
                    'task_id': name, 'protocol': item,
                    'artifacts': {}, 'artifact_status': 'complete',
                }), encoding='utf-8')
            report = audit([load_entry('a', root / 'a'), load_entry('b', root / 'b')])
            pair = report['pairs']['a__vs__b']
            self.assertFalse(pair['full_protocol'])
            self.assertTrue(pair['physical_protocol'])
            self.assertFalse(pair['rankable'])


if __name__ == '__main__':
    unittest.main()
