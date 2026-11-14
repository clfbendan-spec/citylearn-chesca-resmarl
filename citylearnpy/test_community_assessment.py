import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import community_assessment as assessment


class MetricTests(unittest.TestCase):
    def test_optimization_opportunities_separate_static_screen_from_savings_claim(self):
        battery = SimpleNamespace(capacity=10, nominal_power=5, round_trip_efficiency=.81, soc=[.2, .2, .2])
        cooling = SimpleNamespace(nominal_power=3, electricity_consumption=[1, 1, 1])
        heating = SimpleNamespace(nominal_power=0, electricity_consumption=[0, 0, 0])
        dhw = SimpleNamespace(nominal_power=2, electricity_consumption=[0, 1, 1])
        building = SimpleNamespace(name='B1', electrical_storage=battery, cooling_device=cooling,
            heating_device=heating, dhw_device=dhw, net_electricity_consumption=[-1, 2, 2],
            pricing=SimpleNamespace(electricity_pricing=[.1, .2, .4]), power_outage_signal=[0, 0, 0],
            occupant_count=[0, 1, 1], cooling_electricity_consumption=[1, 1, 1],
            heating_electricity_consumption=[0, 0, 0], dhw_electricity_consumption=[0, 1, 1],
            indoor_dry_bulb_temperature=[23, 24, 26],
            indoor_dry_bulb_temperature_cooling_set_point=[25, 25, 25],
            indoor_dry_bulb_temperature_heating_set_point=[20, 20, 20])
        opportunities = assessment.optimization_opportunities([building], 'USD')
        battery_row = next(row for row in opportunities if row['building'] == 'B1' and row['category'] == '电池移峰')
        thermal_row = next(row for row in opportunities if row['building'] == 'B1' and row['category'] == '冷热负荷')
        dhw_row = next(row for row in opportunities if row['building'] == 'B1' and row['category'] == '热水负荷')
        joint_row = next(row for row in opportunities if row['building'] == '社区' and row['category'] == '联合调度')
        self.assertEqual(2, battery_row['candidateChargeSteps'])
        self.assertAlmostEqual(.224, battery_row['maxUnitMargin'])
        self.assertEqual(1, thermal_row['unoccupiedCoolingSteps'])
        self.assertEqual(1, thermal_row['occupiedOvercoolSteps'])
        self.assertEqual(.4, dhw_row['highPriceExposure'])
        self.assertIn('不能直接当作可节省金额', thermal_row['caveat'])
        self.assertEqual('待完整环境回放', joint_row['status'])

    def test_absolute_totals_use_realized_positive_cost_and_emissions_and_sum_buildings(self):
        env = SimpleNamespace(net_electricity_consumption=[1, 3], buildings=[
            SimpleNamespace(name='Building_1', net_electricity_consumption_cost=[2, -1, 3], net_electricity_consumption_emission=[.4, 0, .6]),
            SimpleNamespace(name='Building_2', net_electricity_consumption_cost=[4, 0, 1], net_electricity_consumption_emission=[.2, 0, .3])])
        result = assessment.diagnostics(env, [{}, {}], [], 'USD')
        self.assertEqual(5, result['buildings'][0]['positiveCost'])
        self.assertEqual(1, result['buildings'][0]['carbonEmissions'])
        self.assertEqual(10, result['district']['positiveCost'])
        self.assertEqual(1.5, result['district']['carbonEmissions'])
        self.assertEqual({'positiveCost': 'USD', 'carbonEmissions': 'kgCO2'}, result['units'])

    def test_dataset_currency_comes_from_manifest_and_missing_currency_is_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'manifest.json').write_text(json.dumps({'building': {'currency': 'CNY'}}), encoding='utf-8')
            self.assertEqual('CNY', assessment.dataset_currency(root))
            (root / 'manifest.json').write_text(json.dumps({'building': {}}), encoding='utf-8')
            self.assertEqual('未知币种', assessment.dataset_currency(root))

    def test_absolute_totals_preserve_zero_but_never_treat_missing_as_zero(self):
        for cost, emissions in [([], []), ([float('nan')], [float('inf')]), (None, None)]:
            env = SimpleNamespace(net_electricity_consumption=[], buildings=[SimpleNamespace(
                name='Building_1', net_electricity_consumption_cost=cost, net_electricity_consumption_emission=emissions)])
            result = assessment.diagnostics(env, [{}], [])
            self.assertIsNone(result['buildings'][0]['positiveCost'])
            self.assertIsNone(result['district']['positiveCost'])
            self.assertIsNone(result['district']['carbonEmissions'])
        env.buildings[0].net_electricity_consumption_cost = [0, 0]
        env.buildings[0].net_electricity_consumption_emission = [0, 0]
        result = assessment.diagnostics(env, [{}], [])
        self.assertEqual(0, result['district']['positiveCost'])
        self.assertEqual(0, result['district']['carbonEmissions'])

    def test_atomic_progress_write_retries_transient_windows_reader_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'progress.json'
            target.write_text('{}', encoding='utf-8')
            replace = assessment.os.replace
            attempts = []
            def locked_then_replace(source, destination):
                attempts.append(destination)
                if len(attempts) <= 2:
                    raise PermissionError('Windows reader holds destination briefly')
                replace(source, destination)
            with patch.object(assessment.os, 'replace', side_effect=locked_then_replace), patch.object(assessment.time, 'sleep'):
                assessment.write_json(target, {'stage': 'running'})
            self.assertEqual(3, len(attempts))
            self.assertEqual({'stage': 'running'}, json.loads(target.read_text(encoding='utf-8')))

    def test_recommendations_identify_constraints_tradeoffs_and_soc(self):
        baseline = {'metrics': {'cost_total': 1., 'discomfort_proportion': .2,
                    'buildings': [{'name': 'Building_1', 'cost_total': 1., 'discomfort_proportion': .2}]},
                    'diagnostics': {'buildings': [{'name': 'Building_1', 'terminalSOC': {'electrical_storage': .5}}]}}
        candidate = {'id': 'rule', 'label': 'Test rule', 'status': 'succeeded',
                     'metrics': {'cost_total': .8, 'discomfort_proportion': .3, 'feasible': False},
                     'diagnostics': {'buildings': [{'name': 'Building_1', 'terminalSOC': {'electrical_storage': .1}}]}}
        text = '\n'.join(assessment.optimization_recommendations(baseline, [candidate]))
        self.assertIn('Building_1', text)
        self.assertIn('20.0%', text)
        self.assertIn('50.0%', text)
        self.assertIn('electrical_storage', text)
        self.assertIn('SOC', text)
        self.assertIn('权衡', text)
        missing = '\n'.join(assessment.optimization_recommendations({'metrics': {'buildings': [{'name': 'Missing', 'cost_total': None, 'discomfort_proportion': None}]}}, []))
        self.assertIn('Missing', missing)
        self.assertIn('不可判定', missing)

    def test_strict_gates_and_missing_values_are_not_zero(self):
        rows = [dict(level='district', name='District', cost_function='cost_total', value=.8),
                dict(level='district', name='District', cost_function='discomfort_proportion', value=.05),
                dict(level='building', name='Building_1', cost_function='cost_total', value=.90),
                dict(level='building', name='Building_1', cost_function='discomfort_proportion', value=.09)]
        result = assessment.summarize_metrics(rows, ['Building_1'])
        self.assertFalse(result['feasible'])
        self.assertAlmostEqual(result['score'], .5*.8/assessment.C_REF + .5*.05/assessment.D_REF)
        rows.pop()
        result = assessment.summarize_metrics(rows, ['Building_1'])
        self.assertIsNone(result['buildings'][0]['discomfort_proportion'])
        self.assertIsNone(result['feasible'])
        self.assertIn('missing', result['buildings'][0]['constraintStatus'])

    def test_nonfinite_and_zero_reference_are_explicit(self):
        rows = [dict(level='district', name='District', cost_function='cost_total', value=float('inf'))]
        result = assessment.summarize_metrics(rows, ['Building_1'])
        self.assertIsNone(result['cost_total'])
        self.assertIsNone(result['score'])
        self.assertIsNone(assessment.relative_change(0, 1))
        self.assertIsNone(assessment.relative_change(None, 1))


class FullEpisodeTests(unittest.TestCase):
    def fixture(self, target):
        source = Path(__file__).parent / 'datasets/community_54fb2f0f3a48482cba1a4bbaed775fda'
        if not source.exists():
            self.skipTest('Local immutable Online1 acceptance fixture is unavailable')
        schema = json.loads((source / 'schema.json').read_text(encoding='utf-8'))
        definition = copy.deepcopy(schema['buildings']['Building_1'])
        definition['type'] = 'citylearn.building.Building'
        for name in ['dynamics', 'pv', 'electrical_storage', 'dhw_storage', 'cooling_storage', 'heating_storage']:
            definition.pop(name, None)
        definition['power_outage'] = {'simulate_power_outage': False, 'stochastic_power_outage': False}
        schema['buildings'] = {'Building_1': definition}
        schema['simulation_end_time_step'] = 48
        schema['episode_time_steps'] = 8
        for signal in schema['actions'].values():
            signal['active'] = False
        for name, signal in schema['observations'].items():
            if name.endswith('_soc'):
                signal['active'] = False
        for name in ['energy_simulation', 'weather', 'pricing', 'carbon_intensity']:
            filename = definition[name]
            with (source / filename).open(encoding='utf-8', newline='') as stream:
                reader = csv.reader(stream)
                rows = [next(reader) for _ in range(50)]
            with (target / filename).open('w', encoding='utf-8', newline='') as stream:
                csv.writer(stream).writerows(rows)
        path = target / 'schema.json'
        path.write_text(json.dumps(schema), encoding='utf-8')
        (target / 'manifest.json').write_text(json.dumps({'building': {'currency': 'USD'}}), encoding='utf-8')
        return path

    def test_real_no_devices_runs_full_bounds_and_skips_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            schema = self.fixture(target)
            before = schema.read_bytes()
            result = assessment.run_assessment(schema, target / 'run')
            self.assertEqual('succeeded', result['status'])
            self.assertEqual(48, result['baseline']['steps'])
            self.assertEqual([[]], result['baseline']['effectiveActions'])
            self.assertEqual('citylearn.agents.base.BaselineAgent', result['baseline']['policyClass'])
            actual = result['baseline']['diagnostics']
            self.assertGreater(actual['buildings'][0]['positiveCost'], 0)
            self.assertGreater(actual['buildings'][0]['carbonEmissions'], 0)
            self.assertEqual(actual['buildings'][0]['positiveCost'], actual['district']['positiveCost'])
            self.assertEqual(actual['buildings'][0]['carbonEmissions'], actual['district']['carbonEmissions'])
            self.assertEqual('USD', actual['units']['positiveCost'])
            self.assertEqual({'电池移峰', '冷热负荷', '热水负荷', '联合调度'}, {item['category'] for item in actual['optimizationOpportunities']})
            self.assertTrue(all(case['status'] == 'skipped' for case in result['cases']))
            self.assertEqual(before, schema.read_bytes())
            self.assertEqual('succeeded', json.loads((target / 'run/progress.json').read_text(encoding='utf-8'))['stage'])
            self.assertTrue((target / 'run/report.md').exists())

    def test_mandatory_baseline_failure_stops_successful_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            schema = self.fixture(target)
            with patch.object(assessment, 'run_case', side_effect=ValueError('invalid dynamics')) as execute:
                result = assessment.run_assessment(schema, target / 'failed')
            self.assertEqual('failed', result['status'])
            self.assertEqual('failed', result['baseline']['status'])
            self.assertEqual(1, execute.call_count)
            self.assertEqual([], result['cases'])

    def test_real_zero_price_has_no_defined_cost_ratio_or_score(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            schema = self.fixture(target)
            definition = json.loads(schema.read_text(encoding='utf-8'))['buildings']['Building_1']
            price = target / definition['pricing']
            with price.open(encoding='utf-8', newline='') as stream:
                rows = list(csv.reader(stream))
            rows[1:] = [['0']*len(rows[0]) for _ in rows[1:]]
            with price.open('w', encoding='utf-8', newline='') as stream:
                csv.writer(stream).writerows(rows)
            result = assessment.run_assessment(schema, target / 'zero')
            self.assertIsNone(result['baseline']['metrics']['cost_total'])
            self.assertIsNone(result['baseline']['metrics']['score'])
            self.assertIsNone(result['baseline']['metrics']['feasible'])
            self.assertEqual(0, result['baseline']['diagnostics']['district']['positiveCost'])
            self.assertIn('zero', result['baseline']['metrics']['undefinedMetrics']['Building_1.cost_total'])


if __name__ == '__main__':
    unittest.main()
