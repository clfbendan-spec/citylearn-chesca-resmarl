import copy
import unittest
from types import SimpleNamespace

import evaluation_contract as contract


class RuntimeAuditTest(unittest.TestCase):
    def test_runtime_equipment_ignores_instance_uid_but_preserves_physical_changes(self):
        building = SimpleNamespace(name='Building_1', get_metadata=lambda: copy.deepcopy(metadata))
        metadata = {'uid': 'first', 'cooling_device': {'uid': 'device-a', 'nominal_power': 4.1,
                                                      'efficiency': .25},
                    'heating_device': {'nominal_power': 0., 'efficiency': .27}}
        env = SimpleNamespace(buildings=[building])
        first = contract.capture_runtime_equipment(env)
        metadata['uid'] = 'second'
        metadata['cooling_device']['uid'] = 'device-b'
        self.assertEqual(first, contract.capture_runtime_equipment(env))
        metadata['cooling_device']['nominal_power'] = 5.
        self.assertNotEqual(first, contract.capture_runtime_equipment(env))
        self.assertEqual(first['Building_1']['heating_device']['efficiency'], .27)

    def test_final_outage_audit_reads_observed_history_without_regenerating_events(self):
        building = SimpleNamespace(name='Building_1', power_outage_signal=[0., 1., 1.])
        env = SimpleNamespace(buildings=[building])
        context = {'runtime_equipment': {'Building_1': {'cooling_device': {'nominal_power': 4.1}}},
                   'protocol': {'simulation_window': [10, 12]}}
        audit = contract.collect_runtime_audit(env, context)
        self.assertEqual(audit['outages']['Building_1']['source_steps'], [10, 11, 12])
        self.assertEqual(audit['outages']['Building_1']['values'], [0., 1., 1.])
        self.assertEqual(audit['outages']['Building_1']['outage_source_steps'], [11, 12])
        building.power_outage_signal = [0., 0., 0.]
        self.assertNotEqual(audit['outages']['Building_1']['sha256'],
                            contract.collect_runtime_audit(env, context)['outages']['Building_1']['sha256'])


if __name__ == '__main__':
    unittest.main()
