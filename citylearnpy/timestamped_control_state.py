"""Explicit-time control inputs, independent of legacy normalized observations.

Outcome arrays are read only through t-1, except known initial T/SOC at t=0.
Current exogenous signals and storage.energy_init are explicitly distinguished
from completed measurements. Optional plans/forecasts are controller outputs;
their provenance must be verified by the caller, not inferred from timestamps.
The extractor has no cache, model, simulator reference or state to reset.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

import numpy as np

VERSION = 'explicit_time_control_v1'
BUILDINGS = 3
HISTORY = 12


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    scale: float = 1.
    offset: float = 0.
    low: float = -5.
    high: float = 5.
    source: str = 'current_exogenous'


def _specs():
    out=[]
    def add(name,scale=1.,offset=0.,low=-5.,high=5.,source='current_exogenous'):
        out.append(FeatureSpec(name,scale,offset,low,high,source))
    for n in ['month','day_type','hour']:
        for trig in ['sin','cos']:add(n+'_'+trig,low=-1.,high=1.)
    add('remaining_fraction',low=0.,high=1.,source='known_clock')
    add('remaining_hours_div24',24.,low=0.,high=5.,source='known_clock')
    add('outdoor_temperature_c',20.,25.)
    for n in ['direct_irradiance','diffuse_irradiance']:add(n,1000.)
    for n in ['nonshiftable_request_kwh','solar_generation_kwh']:add(n,10.)
    add('occupants',10.,low=0.)
    add('outage',low=0.,high=1.)
    for n in ['cooling_setpoint_c','heating_setpoint_c']:add(n,10.,25.)
    add('comfort_band_c',5.,low=0.)
    add('dhw_request_kwh',10.,low=0.)
    add('last_temperature_c',10.,25.,source='completed_or_initial')
    for n in ['last_temperature_minus_current_cooling_setpoint_c','last_temperature_minus_current_heating_setpoint_c']:
        add(n,5.,source='completed_or_initial_and_current_schedule')
    add('last_net_kwh',10.,source='completed')
    add('last_cooling_supplied_kwh',20.,source='completed')
    add('last_dhw_supplied_kwh',10.,source='completed')
    add('last_cooling_electricity_kwh',10.,source='completed')
    for n in ['last_battery_soc','last_dhw_soc']:add(n,low=0.,high=1.,source='completed_or_initial')
    add('has_completed_measurement',low=0.,high=1.,source='known_clock')
    for n in ['battery_before_fraction','dhw_before_fraction']:add(n,low=0.,high=1.,source='current_physical_snapshot')
    add('battery_capacity_kwh',10.,low=0.,source='static_device')
    add('battery_nominal_kw',10.,low=0.,source='static_device')
    add('battery_max_input_power_ratio',source='current_physical_snapshot')
    add('reference_last_temperature_c',10.,25.,source='virtual_reference_completed_or_initial')
    add('temperature_minus_reference_c',5.,source='completed_or_initial_and_virtual_reference')
    for n in ['reference_battery_before_fraction','reference_dhw_before_fraction']:
        add(n,low=0.,high=1.,source='virtual_reference_current_snapshot')
    add('reference_last_net_kwh',10.,source='virtual_reference_completed')
    add('has_reference',low=0.,high=1.,source='input_availability')
    for n in ['plan_dhw_action','plan_battery_action','plan_cooling_action','battery_action_low','battery_action_high']:
        add(n,low=-1.,high=1.,source='timestamped_controller_plan')
    for n in ['plan_floor_fraction','plan_ceiling_fraction']:add(n,low=0.,high=1.,source='timestamped_controller_plan')
    add('plan_next_discharge_gain_ratio',source='timestamped_conditional_model_probe')
    add('plan_extra_charge_cost_fraction',source='timestamped_conditional_model_probe')
    add('plan_candidate_available',low=0.,high=1.,source='timestamped_controller_plan')
    add('plan_predicted_temperature_c',10.,25.,source='timestamped_known_model_prediction')
    add('has_plan_temperature_prediction',low=0.,high=1.,source='input_availability')
    add('has_plan',low=0.,high=1.,source='input_availability')
    for j in range(BUILDINGS):add('building_identity_'+str(j+1),low=0.,high=1.,source='static_device')
    add('completed_district_peak_kw',20.,source='completed_district_history')
    add('last_district_net_kwh',20.,source='completed_district_history')
    add('current_district_nonshiftable_minus_pv_kwh',20.)
    add('all_connected',low=0.,high=1.)
    for j in range(BUILDINGS):
        prefix='b'+str(j+1)+'_'
        for n,scale in [('bank_cooldown_steps',13.),('loan_cooldown_steps',13.),('bank_remaining_steps',12.),
                        ('bank_open',1.),('bank_expired',1.),('request_remaining_steps',12.),('thermal_recovery_open',1.)]:
            add(prefix+n,scale,low=0.,high=1.,source='timestamped_control_account')
        add(prefix+'next_discharge_gain_ratio',source='timestamped_conditional_model_probe')
        add(prefix+'extra_charge_cost_fraction',source='timestamped_conditional_model_probe')
        add(prefix+'candidate_available',low=0.,high=1.,source='timestamped_controller_plan')
    for n in ['forecast_next_nonshiftable_kw','forecast_nonbattery_upper_kw']:
        add(n,20.,source='timestamped_forecast_provided_by_caller')
    add('has_forecast',low=0.,high=1.,source='input_availability')
    for k in range(1,HISTORY+1):add('past_district_nonshiftable_minus_pv_lag'+str(k),20.,source='past_exogenous_history')
    add('past_exogenous_samples',HISTORY,low=0.,high=1.,source='known_clock')
    return tuple(out)


FEATURE_SPECS = _specs()
FEATURE_NAMES = tuple(s.name for s in FEATURE_SPECS)
OBS_DIM = len(FEATURE_NAMES)
assert len(set(FEATURE_NAMES)) == OBS_DIM


def bounds():
    return (np.asarray([s.low for s in FEATURE_SPECS],dtype=np.float32),
            np.asarray([s.high for s in FEATURE_SPECS],dtype=np.float32))


@dataclass(frozen=True)
class ControlAccount:
    step: int
    bank_next_step: int = 0
    loan_next_step: int = 0
    bank_deadline: Optional[int] = None
    bank_expired: bool = False
    request_until_step: int = 0
    thermal_recovery_open: bool = False


@dataclass(frozen=True)
class ControllerPlan:
    step: int
    base_actions: tuple
    battery_low: float
    battery_high: float
    floor_kwh: float
    ceiling_kwh: float
    next_discharge_gain_kw: float = 0.
    extra_charge_cost_kwh: float = 0.
    candidate_available: bool = False
    predicted_temperature_c: Optional[float] = None


@dataclass(frozen=True)
class ForecastInput:
    step: int
    next_nonshiftable_kw: float
    nonbattery_upper_kw: float


@dataclass(frozen=True)
class ControlFrame:
    building: int
    decision_step: int
    completed_outcome_step: Optional[int]
    initial_state_step: Optional[int]
    reference_step: Optional[int]
    plan_step: Optional[int]
    raw: dict
    vector: np.ndarray
    clipped_features: tuple

    def as_dict(self):
        return dict(version=VERSION,building=self.building,decision_step=self.decision_step,
                    completed_outcome_step=self.completed_outcome_step,initial_state_step=self.initial_state_step,
                    reference_step=self.reference_step,plan_step=self.plan_step,raw=self.raw,
                    vector=self.vector.tolist(),clipped_features=list(self.clipped_features))


def _finite(value,name):
    x=float(value)
    if not math.isfinite(x):raise ValueError(name+' is nonfinite')
    return x


def _value(series,index,name,constant=False):
    try:size=len(series)
    except TypeError:
        if not constant:raise ValueError(name+' needs timestamped series')
        return _finite(series,name)
    if not size:raise ValueError(name+' is empty')
    i=0 if constant and size==1 else index
    if i<0 or i>=size:raise ValueError(name+' has incomplete history')
    return _finite(series[i],name)


def _fraction(storage,name):
    capacity=_finite(storage.capacity,name+' capacity')
    if capacity<=0:raise ValueError(name+' capacity must be positive')
    return _finite(storage.energy_init,name+' energy_init')/capacity


def _previous(building,t):
    m=max(0,t-1)
    temperature=_value(building.indoor_dry_bulb_temperature,m,'completed temperature')
    return dict(
        temperature=temperature,
        battery_soc=_value(building.electrical_storage.soc,m,'completed battery SOC'),
        dhw_soc=_value(building.dhw_storage.soc,m,'completed DHW SOC'),
        net=0. if not t else _value(building.net_electricity_consumption,m,'completed net electricity'),
        cooling=0. if not t else _value(building.energy_from_cooling_device,m,'completed cooling device')+_value(building.energy_from_cooling_storage,m,'completed cooling storage'),
        dhw=0. if not t else _value(building.energy_from_dhw_device,m,'completed DHW device')+_value(building.energy_from_dhw_storage,m,'completed DHW storage'),
        cooling_electricity=0. if not t else _value(building.cooling_device.electricity_consumption,m,'completed cooling electricity'))


def _account(account,t):
    if account.step!=t:raise ValueError('Account timestamp mismatch')
    for name in ['step','bank_next_step','loan_next_step','request_until_step']:
        value=getattr(account,name)
        if int(value)!=value or value<0:raise ValueError('Invalid account '+name)
    if account.bank_deadline is not None and (int(account.bank_deadline)!=account.bank_deadline or account.bank_deadline<0):raise ValueError('Invalid bank deadline')
    remaining=lambda value:max(0,value-t)
    values=[remaining(account.bank_next_step),remaining(account.loan_next_step),
            0 if account.bank_deadline is None else remaining(account.bank_deadline),
            float(account.bank_deadline is not None),float(account.bank_expired),remaining(account.request_until_step),float(account.thermal_recovery_open)]
    if values[0]>13 or values[1]>13 or values[2]>12 or values[5]>12:raise ValueError('Account exceeds registered13/12-step contract')
    return values


def extract_district(buildings, *, state_count, reference=None, plans=None, accounts=None, forecast=None):
    """Return one independent frame per building for this three-building contract.

    Plans/accounts/forecasts are optional current-time records. This function
    does not run a controller or certify the input provenance of those records.
    No observations(), uncontrolled cooling series, old vector or model state
    is accessed. Missing completed history is an error, never silently zeroed.
    """
    if len(buildings)!=BUILDINGS:raise ValueError('Exactly three buildings required')
    t=int(buildings[0].time_step)
    if t<0 or any(int(b.time_step)!=b.time_step or int(b.time_step)!=t for b in buildings):raise ValueError('Building timestamp mismatch')
    if int(state_count)!=state_count or not t<int(state_count)-1:raise ValueError('Invalid decision horizon')
    refs=[None]*BUILDINGS if reference is None else list(reference)
    if len(refs)!=BUILDINGS or any(r is not None and int(r.time_step)!=t for r in refs):raise ValueError('Reference timestamp mismatch')
    plans=[None]*BUILDINGS if plans is None else list(plans)
    accounts=[ControlAccount(t) for _ in buildings] if accounts is None else list(accounts)
    if len(plans)!=BUILDINGS or len(accounts)!=BUILDINGS:raise ValueError('Plan/account count mismatch')
    for p in plans:
        if p is not None and p.step!=t:raise ValueError('Plan timestamp mismatch')
    if forecast is not None and forecast.step!=t:raise ValueError('Forecast timestamp mismatch')
    previous=[_previous(b,t) for b in buildings]
    district_history=[sum(_value(b.net_electricity_consumption,i,'completed district electricity') for b in buildings) for i in range(t)]
    peak=max([0.]+district_history)
    current_ns=sum(_value(b.energy_simulation.non_shiftable_load,t,'current nonshiftable request')-abs(_value(b.solar_generation,t,'current PV')) for b in buildings)
    shared=dict(completed_district_peak_kw=peak,last_district_net_kwh=0. if not t else district_history[-1],
                current_district_nonshiftable_minus_pv_kwh=current_ns,all_connected=float(not any(bool(b.power_outage) for b in buildings)),
                forecast_next_nonshiftable_kw=0. if forecast is None else forecast.next_nonshiftable_kw,
                forecast_nonbattery_upper_kw=0. if forecast is None else forecast.nonbattery_upper_kw,has_forecast=float(forecast is not None),
                past_exogenous_samples=min(t,HISTORY))
    for k in range(1,HISTORY+1):
        shared['past_district_nonshiftable_minus_pv_lag'+str(k)]=0. if k>t else sum(_value(b.energy_simulation.non_shiftable_load,t-k,'past nonshiftable request')-abs(_value(b.solar_generation,t-k,'past PV')) for b in buildings)
    capacities=[_finite(b.electrical_storage.capacity,'battery capacity') for b in buildings]
    powers=[_finite(b.electrical_storage.nominal_power,'battery nominal power') for b in buildings]
    if min(capacities+powers)<=0:raise ValueError('Nonpositive battery capacity or nominal power')
    for j,(account,plan) in enumerate(zip(accounts,plans)):
        prefix='b'+str(j+1)+'_'
        names=['bank_cooldown_steps','loan_cooldown_steps','bank_remaining_steps','bank_open','bank_expired','request_remaining_steps','thermal_recovery_open']
        shared.update({prefix+n:v for n,v in zip(names,_account(account,t))})
        shared.update({prefix+'next_discharge_gain_ratio':0. if plan is None else plan.next_discharge_gain_kw/powers[j],
                       prefix+'extra_charge_cost_fraction':0. if plan is None else plan.extra_charge_cost_kwh/capacities[j],
                       prefix+'candidate_available':0. if plan is None else float(plan.candidate_available)})
    frames=[]
    for j,(b,past,ref,plan) in enumerate(zip(buildings,previous,refs,plans)):
        sim=b.energy_simulation;weather=b.weather
        cool=_value(b.indoor_dry_bulb_temperature_cooling_set_point,t,'current cooling setpoint',True)
        heat=_value(b.indoor_dry_bulb_temperature_heating_set_point,t,'current heating setpoint',True)
        band=_value(b.comfort_band,t,'current comfort band',True)
        if band<0:raise ValueError('Negative comfort band')
        raw=dict(shared)
        for name,period in [('month',12.),('day_type',7.),('hour',24.)]:
            angle=2*math.pi*_value(getattr(sim,name),t,'current '+name)/period
            raw[name+'_sin']=math.sin(angle);raw[name+'_cos']=math.cos(angle)
        raw.update(remaining_fraction=(state_count-1-t)/(state_count-1),remaining_hours_div24=state_count-1-t,
            outdoor_temperature_c=_value(weather.outdoor_dry_bulb_temperature,t,'current outdoor temperature'),
            direct_irradiance=_value(weather.direct_solar_irradiance,t,'current direct irradiance'),
            diffuse_irradiance=_value(weather.diffuse_solar_irradiance,t,'current diffuse irradiance'),
            nonshiftable_request_kwh=_value(sim.non_shiftable_load,t,'current nonshiftable request'),
            solar_generation_kwh=abs(_value(b.solar_generation,t,'current PV')),
            occupants=_value(b.occupant_count,t,'current occupants',True),outage=float(bool(b.power_outage)),
            cooling_setpoint_c=cool,heating_setpoint_c=heat,comfort_band_c=band,
            dhw_request_kwh=_value(sim.dhw_demand,t,'current DHW request'),
            last_temperature_c=past['temperature'],
            last_temperature_minus_current_cooling_setpoint_c=past['temperature']-cool,
            last_temperature_minus_current_heating_setpoint_c=past['temperature']-heat,
            last_net_kwh=past['net'],last_cooling_supplied_kwh=past['cooling'],last_dhw_supplied_kwh=past['dhw'],
            last_cooling_electricity_kwh=past['cooling_electricity'],last_battery_soc=past['battery_soc'],last_dhw_soc=past['dhw_soc'],
            has_completed_measurement=float(t>0),battery_before_fraction=_fraction(b.electrical_storage,'battery'),
            dhw_before_fraction=_fraction(b.dhw_storage,'DHW'),battery_capacity_kwh=capacities[j],battery_nominal_kw=powers[j],
            battery_max_input_power_ratio=_finite(b.electrical_storage.get_max_input_power(),'current battery power')/powers[j])
        r=None if ref is None else _previous(ref,t)
        raw.update(reference_last_temperature_c=25. if r is None else r['temperature'],
                   temperature_minus_reference_c=0. if r is None else past['temperature']-r['temperature'],
                   reference_battery_before_fraction=0. if ref is None else _fraction(ref.electrical_storage,'reference battery'),
                   reference_dhw_before_fraction=0. if ref is None else _fraction(ref.dhw_storage,'reference DHW'),
                   reference_last_net_kwh=0. if r is None else r['net'],has_reference=float(ref is not None))
        if plan is not None:
            actions=np.asarray(plan.base_actions,dtype=float)
            if actions.shape!=(3,) or not np.isfinite(actions).all() or min(actions)<-1 or max(actions)>1:raise ValueError('Invalid planned actions')
            if not -1<=plan.battery_low<=plan.battery_high<=1:raise ValueError('Invalid battery bounds')
            if not 0<=plan.floor_kwh<=plan.ceiling_kwh<=capacities[j]+1e-6:raise ValueError('Invalid planned energy band')
        actions=(0.,0.,0.) if plan is None else plan.base_actions
        raw.update(plan_dhw_action=actions[0],plan_battery_action=actions[1],plan_cooling_action=actions[2],
            battery_action_low=0. if plan is None else plan.battery_low,battery_action_high=0. if plan is None else plan.battery_high,
            plan_floor_fraction=0. if plan is None else plan.floor_kwh/capacities[j],plan_ceiling_fraction=0. if plan is None else plan.ceiling_kwh/capacities[j],
            plan_next_discharge_gain_ratio=0. if plan is None else plan.next_discharge_gain_kw/powers[j],
            plan_extra_charge_cost_fraction=0. if plan is None else plan.extra_charge_cost_kwh/capacities[j],
            plan_candidate_available=0. if plan is None else float(plan.candidate_available),
            plan_predicted_temperature_c=25. if plan is None or plan.predicted_temperature_c is None else plan.predicted_temperature_c,
            has_plan_temperature_prediction=float(plan is not None and plan.predicted_temperature_c is not None),has_plan=float(plan is not None))
        for k in range(BUILDINGS):raw['building_identity_'+str(k+1)]=float(k==j)
        if set(raw)!=set(FEATURE_NAMES):raise AssertionError('Feature schema drift')
        raw={name:_finite(raw[name],name) for name in FEATURE_NAMES}
        scaled=np.asarray([(raw[s.name]-s.offset)/s.scale for s in FEATURE_SPECS],dtype=float)
        low,high=bounds();clipped=tuple(FEATURE_NAMES[i] for i in np.flatnonzero((scaled<low)|(scaled>high)))
        vector=np.clip(scaled,low,high).astype(np.float32);vector.setflags(write=False)
        frames.append(ControlFrame(j+1,t,None if not t else t-1,0 if not t else None,
                                   None if ref is None else t,None if plan is None else t,raw,vector,clipped))
    return tuple(frames)
