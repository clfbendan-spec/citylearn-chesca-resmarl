from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest

from timestamped_control_state import (ControlAccount,ControllerPlan,ForecastInput,
                                      FEATURE_NAMES,OBS_DIM,bounds,extract_district)


class PrefixOnly:
    def __init__(self,values):self.values=values
    def __len__(self):return len(self.values)
    def __getitem__(self,i):
        if i<0 or i>=len(self.values):raise AssertionError('Unrealized outcome accessed')
        return self.values[i]


def building(t=2):
    battery=NS(capacity=4.,nominal_power=3.,energy_init=2.,soc=PrefixOnly([.4,.51]),get_max_input_power=lambda:2.8)
    dhw=NS(capacity=3.,energy_init=1.,soc=PrefixOnly([.2,.35]))
    return NS(time_step=t,electrical_storage=battery,dhw_storage=dhw,
              indoor_dry_bulb_temperature=PrefixOnly([25.,27.]),
              net_electricity_consumption=PrefixOnly([1.,2.]),
              energy_from_cooling_device=PrefixOnly([2.,3.]),energy_from_cooling_storage=PrefixOnly([0.,0.]),
              energy_from_dhw_device=PrefixOnly([.1,.2]),energy_from_dhw_storage=PrefixOnly([0.,.3]),
              cooling_device=NS(electricity_consumption=PrefixOnly([.5,.7])),
              indoor_dry_bulb_temperature_cooling_set_point=[25.,25.,24.],
              indoor_dry_bulb_temperature_heating_set_point=[20.,20.,21.],comfort_band=[2.],occupant_count=[1.,1.,0.],power_outage=False,
              solar_generation=[-.1,-.2,-.3],
              weather=NS(outdoor_dry_bulb_temperature=[30.,31.,32.],direct_solar_irradiance=[100.,200.,300.],diffuse_solar_irradiance=[20.,30.,40.]),
              energy_simulation=NS(month=[1.,1.,1.],day_type=[2.,2.,2.],hour=[1.,2.,3.],non_shiftable_load=[1.,2.,3.],dhw_demand=[.1,.2,.3]))


def district(t=2):return [building(t) for _ in range(3)]


def test_completed_feedback_current_schedule_and_physical_snapshot_have_separate_times():
    frame=extract_district(district(),state_count=10)[0]
    assert (frame.decision_step,frame.completed_outcome_step,frame.initial_state_step)==(2,1,None)
    assert frame.raw['last_temperature_c']==27. and frame.raw['cooling_setpoint_c']==24.
    assert frame.raw['last_battery_soc']==.51 and frame.raw['battery_before_fraction']==.5
    assert frame.raw['last_net_kwh']==2. and frame.raw['last_dhw_supplied_kwh']==.5
    assert frame.raw['completed_district_peak_kw']==6.
    assert frame.raw['past_exogenous_samples']==2
    assert frame.raw['past_district_nonshiftable_minus_pv_lag3']==0.


def test_future_and_current_placeholder_outcomes_are_not_read():
    a=district();before=extract_district(a,state_count=10)
    for b in a:
        for name in ['indoor_dry_bulb_temperature','net_electricity_consumption','energy_from_cooling_device','energy_from_dhw_device']:
            old=getattr(b,name).values;setattr(b,name,old+[999.,-999.])
        b.electrical_storage.soc=[.4,.51,999.];b.dhw_storage.soc=[.2,.35,999.]
        b.cooling_device.electricity_consumption=[.5,.7,999.]
        b.energy_simulation.non_shiftable_load += [999.]
        b.weather.outdoor_dry_bulb_temperature += [999.]
        b.solar_generation += [999.]
    after=extract_district(a,state_count=10)
    for x,y in zip(before,after):np.testing.assert_array_equal(x.vector,y.vector)


def test_measured_outcomes_do_change_the_input():
    a=district();before=extract_district(a,state_count=10)[0]
    a[0].indoor_dry_bulb_temperature.values[1]=28.
    after=extract_district(a,state_count=10)[0]
    assert before.raw['last_temperature_c']!=after.raw['last_temperature_c']
    assert before.vector[FEATURE_NAMES.index('last_temperature_c')]!=after.vector[FEATURE_NAMES.index('last_temperature_c')]


def test_initial_state_is_explicit_and_no_energy_outcome_is_claimed():
    f=extract_district(district(0),state_count=10)[0]
    assert f.completed_outcome_step is None and f.initial_state_step==0
    assert f.raw['has_completed_measurement']==0 and f.raw['last_net_kwh']==0.
    assert f.raw['last_cooling_supplied_kwh']==0. and f.raw['last_temperature_c']==25.
    assert f.raw['last_battery_soc']==.4 and f.raw['past_exogenous_samples']==0


def test_account_history_and_forecast_require_matching_timestamps():
    a=district();accounts=[ControlAccount(2,bank_next_step=10,bank_deadline=12,thermal_recovery_open=True)]*3
    plans=[ControllerPlan(2,(-.8,.1,.2),-.1,.3,1.,2.,.15,.2,True,26.)]*3
    f=extract_district(a,state_count=20,accounts=accounts,plans=plans,forecast=ForecastInput(2,5.,7.))[0]
    assert f.raw['b1_bank_cooldown_steps']==8 and f.raw['plan_next_discharge_gain_ratio']==pytest.approx(.05)
    assert f.raw['has_plan']==1 and f.raw['has_forecast']==1
    assert f.vector[FEATURE_NAMES.index('b1_bank_cooldown_steps')]==np.float32(8/13)
    for kwargs in [dict(accounts=[replace(accounts[0],step=1)]*3),dict(plans=[replace(plans[0],step=1)]*3),dict(forecast=ForecastInput(1,5.,7.)),dict(reference=district(1))]:
        with pytest.raises(ValueError,match='timestamp'):extract_district(a,state_count=20,**kwargs)


def test_nonfinite_and_missing_history_are_rejected():
    a=district();a[0].indoor_dry_bulb_temperature.values[1]=float('nan')
    with pytest.raises(ValueError,match='nonfinite'):extract_district(a,state_count=10)
    a=district();a[0].net_electricity_consumption=PrefixOnly([1.])
    with pytest.raises(ValueError,match='incomplete history'):extract_district(a,state_count=10)
    a=district();a[0].electrical_storage.capacity=0.
    with pytest.raises(ValueError,match='Nonpositive'):extract_district(a,state_count=10)


def test_registered_account_limits_and_energy_bands_are_enforced():
    with pytest.raises(ValueError,match='contract'):extract_district(district(),state_count=20,accounts=[ControlAccount(2,bank_next_step=20)]*3)
    with pytest.raises(ValueError,match='energy band'):extract_district(district(),state_count=20,plans=[ControllerPlan(2,(0.,0.,0.),-1.,1.,2.,1.)]*3)


def test_schema_fixed_scaling_clipping_and_stateless_reset():
    a=district();f=extract_district(a,state_count=10)[0];low,high=bounds()
    assert f.vector.shape==low.shape==high.shape==(OBS_DIM,) and len(set(FEATURE_NAMES))==OBS_DIM
    assert np.isfinite(f.vector).all() and np.all(f.vector>=low) and np.all(f.vector<=high)
    assert not f.vector.flags.writeable and not f.clipped_features
    a[0].weather.outdoor_dry_bulb_temperature[2]=999.
    clipped=extract_district(a,state_count=10)[0]
    assert 'outdoor_temperature_c' in clipped.clipped_features
    reset1=extract_district(district(0),state_count=10);reset2=extract_district(district(0),state_count=10)
    for x,y in zip(reset1,reset2):np.testing.assert_array_equal(x.vector,y.vector)
