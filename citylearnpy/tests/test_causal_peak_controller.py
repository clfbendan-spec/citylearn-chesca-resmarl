import os
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from causal_peak_controller import (CausalPeakConfig, battery_post_energy, completed_district_peak,
    guard_residual, prepare_causal_peak)


def battery():
    return SimpleNamespace(time_step_ratio=1, time_step=0, energy_init=3.2, capacity=4.,
        nominal_power=3., available_nominal_power=3., degraded_capacity=4., depth_of_discharge=.8,
        round_trip_efficiency=.9, soc=[.8], get_max_input_power=lambda:3., get_max_output_power=lambda:3.,
        get_current_efficiency=lambda _: .81)


def building(outage=False):
    device = type('ElectricHeater', (), {'get_input_power':lambda self, q:q,
        'get_max_output_power':lambda self, **kwargs:10.})()
    return SimpleNamespace(electrical_storage=battery(), power_outage=outage,
        net_electricity_consumption=np.r_[np.ones(24), 999., 999.],
        heating_storage=SimpleNamespace(capacity=0.), dhw_device=device,
        seconds_per_time_step=3600, simulate_dynamics=True,
        cooling_device=SimpleNamespace(nominal_power=3.))


class CausalPeakControllerTests(unittest.TestCase):
    def test_completed_peak_excludes_current_and_future(self):
        b=building()
        self.assertEqual(completed_district_peak([b], 24), 1.)
        b.net_electricity_consumption[24:]=1e9
        self.assertEqual(completed_district_peak([b], 24), 1.)
        self.assertEqual(completed_district_peak([b], 0), 0.)

    def test_extra_discharge_guard_preserves_zero_and_reserve(self):
        b=building();base=np.array([-.83, 0., .5])
        final,diag=guard_residual([b], np.array([-.83, -1., .5]), base)
        self.assertTrue(diag['guarded_buildings'][0])
        json.dumps(diag)
        self.assertGreaterEqual(battery_post_energy(b.electrical_storage,final[1]*3), .6*4-1e-8)
        np.testing.assert_array_equal(guard_residual([b],base,base)[0],base)

    def test_outage_cannot_change_battery_baseline(self):
        base=np.array([-.83, -.4, .5])
        final,_=guard_residual([building(True)],np.array([-.83, 1., .5]),base)
        np.testing.assert_array_equal(final,base)

    def test_baseline_below_reserve_is_not_rewritten(self):
        b=building();base=np.array([-.83, -.5, .5])
        np.testing.assert_array_equal(guard_residual([b],base,base)[0],base)
        self.assertEqual(guard_residual([b],np.array([-.83,-1.,.5]),base)[0][1],base[1])

    def test_preparation_is_readonly_and_warmup_is_identity(self):
        b=building();base=np.array([-.83,0.,.5]);raw={'outdoor_dry_bulb_temperature':30.,
            'dhw_demand_0':2.,'non_shiftable_load_0':4.,'solar_generation_0':0.}
        with patch.dict(os.environ, {'CITYLEARN_DHW_STORAGE_FIX':'0'}):
            before=(b.electrical_storage.soc.copy(),b.electrical_storage.energy_init)
            warm,_=prepare_causal_peak([b],raw,base,0)
            np.testing.assert_array_equal(warm,base)
            a,d=prepare_causal_peak([b],raw,base,24)
            again,_=prepare_causal_peak([b],raw,base,24)
            np.testing.assert_array_equal(a,again)
            self.assertLess(a[1],base[1]);self.assertEqual(a[0],base[0]);self.assertEqual(a[2],base[2])
            self.assertEqual((b.electrical_storage.soc,b.electrical_storage.energy_init),before)

    def test_unverified_configuration_fails_explicitly(self):
        b=building();b.heating_storage.capacity=1.
        with patch.dict(os.environ, {'CITYLEARN_DHW_STORAGE_FIX':'0'}):
            with self.assertRaises(ValueError):prepare_causal_peak([b],{},[0,0,0],0)
        with self.assertRaises(ValueError):CausalPeakConfig(reserve_soc=1.1)


if __name__=='__main__':unittest.main()
