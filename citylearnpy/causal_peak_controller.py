"""Causal peak baseline and shared battery execution limits.

Scoped to the verified 2023 hourly, DHW-fix-OFF configuration. No policy,
simulator state or future series is mutated by this module.
"""
from dataclasses import dataclass
from typing import Mapping
import os
import numpy as np


@dataclass(frozen=True)
class CausalPeakConfig:
    reserve_soc: float = .6
    warmup_steps: int = 24
    feature_power_scale: float = 20.

    def __post_init__(self):
        if not 0 <= self.reserve_soc <= 1 or self.warmup_steps < 0 or self.feature_power_scale <= 0:
            raise ValueError('Invalid causal peak configuration')


def battery_post_energy(storage, request):
    if storage.time_step_ratio != 1:
        raise ValueError('Only hourly battery dynamics have been verified')
    initial = float(storage.energy_init)
    if request >= 0:
        limit = float(storage.get_max_input_power())
        energy = min(limit, float(storage.available_nominal_power), float(storage.degraded_capacity)-initial, request)
        efficiency = float(storage.get_current_efficiency(min(request, limit)))**.5
        return min(initial + energy*efficiency, float(storage.capacity))
    limit = float(storage.get_max_output_power())
    soc = float(storage.soc[max(0, storage.time_step-1)])
    depth_limit = -max((soc-(1-storage.depth_of_discharge))*storage.capacity*storage.round_trip_efficiency, 0)
    energy = max(-limit, depth_limit, request)
    efficiency = float(storage.get_current_efficiency(min(abs(request), limit)))**.5
    return max(0., initial + energy/efficiency)


def battery_flow(storage, action):
    request = float(action)*storage.nominal_power
    delta = battery_post_energy(storage, request)-storage.energy_init
    limit = storage.get_max_input_power() if request >= 0 else storage.get_max_output_power()
    efficiency = float(storage.get_current_efficiency(min(abs(request), limit)))**.5
    return float(delta/efficiency if delta >= 0 else delta*efficiency)


def minimum_incremental_action(storage, base_action, reserve_soc=.6):
    """Protect extra discharge; preserve an already lower baseline reserve."""
    floor = reserve_soc*storage.capacity
    if battery_post_energy(storage, base_action*storage.nominal_power) < floor:
        return float(base_action)
    low, high = -1., float(base_action)
    if battery_post_energy(storage, low*storage.nominal_power) >= floor:
        return low
    for _ in range(40):
        middle = (low+high)/2
        if battery_post_energy(storage, middle*storage.nominal_power) < floor:
            low = middle
        else:
            high = middle
    return high


def estimate_grid_devices(building, index, raw: Mapping, actions):
    if os.environ.get('CITYLEARN_DHW_STORAGE_FIX', '0').lower() not in ('0', 'false', 'off', 'no'):
        raise ValueError('Causal device estimator requires explicit DHW fix OFF')
    if building.heating_storage.capacity != 0 or type(building.dhw_device).__name__ != 'ElectricHeater':
        raise ValueError('Unverified DHW device/action-capacity configuration')
    if building.seconds_per_time_step != 3600:
        raise ValueError('Only hourly device estimates have been verified')
    temperature = float(raw['outdoor_dry_bulb_temperature'])
    device = building.dhw_device
    demand = float(raw[f'dhw_demand_{index}'])
    dhw = float(device.get_input_power(min(demand, device.get_max_output_power(max_electric_power=np.inf))))
    if building.simulate_dynamics:
        cooling = float(np.clip(actions[3*index+2], 0, 1)*building.cooling_device.nominal_power)
    else:
        output = min(float(raw[f'cooling_demand_{index}']), building.cooling_device.get_max_output_power(temperature, heating=False, max_electric_power=np.inf))
        cooling = float(building.cooling_device.get_input_power(output, temperature, heating=False))
    return cooling, dhw


def completed_district_peak(buildings, step):
    """Only inspect finalized indices strictly before the decision index."""
    if step == 0:
        return 0.
    return float(np.sum([np.asarray(b.net_electricity_consumption)[:step] for b in buildings], axis=0).max())


def prepare_causal_peak(buildings, raw, base_action, step, config=None, next_ns_forecast=0.):
    config = config or CausalPeakConfig()
    base = np.asarray(base_action, dtype=float).reshape(-1)
    if len(base) != 3*len(buildings):
        raise ValueError('Expected three actions per building')
    out = base.copy()
    estimates, minimum, capacity, base_flows = [], [], [], []
    for b, building in enumerate(buildings):
        cooling, dhw = estimate_grid_devices(building, b, raw, base)
        storage = building.electrical_storage
        action = float(base[3*b+1])
        flow = battery_flow(storage, action)
        allowed = minimum_incremental_action(storage, action, config.reserve_soc) if not building.power_outage else action
        estimates.append((cooling, dhw))
        base_flows.append(flow)
        minimum.append(allowed)
        capacity.append(max(0., flow-battery_flow(storage, allowed)))
    past = completed_district_peak(buildings, step)
    nonbattery = sum(float(raw[f'non_shiftable_load_{b}'])-float(raw[f'solar_generation_{b}'])+c+d for b, (c, d) in enumerate(estimates))
    estimated = nonbattery+sum(base_flows)
    deficit = max(0., estimated-past) if step >= config.warmup_steps else 0.
    amount = min(deficit, sum(capacity))
    if amount > 1e-6:
        for b, building in enumerate(buildings):
            if capacity[b] <= 1e-9:
                continue
            target = base_flows[b]-amount*capacity[b]/sum(capacity)
            low, high = minimum[b], base[3*b+1]
            for _ in range(40):
                middle = (low+high)/2
                if battery_flow(building.electrical_storage, middle) < target:
                    low = middle
                else:
                    high = middle
            out[3*b+1] = (low+high)/2
    diagnostics = dict(step=int(step), past_peak=past, estimated_nonbattery=nonbattery, estimated_raw_base=estimated,
                       deficit=deficit, available_extra_discharge=sum(capacity), active=amount > 1e-6,
                       raw_base=base.tolist(), strong_base=out.tolist(), next_ns_forecast=float(next_ns_forecast))
    return out, diagnostics


PRESSURE_FEATURE_NAMES = ('past_peak', 'estimated_nonbattery', 'estimated_raw_base', 'record_gap',
                          'available_extra_discharge', 'next_ns_forecast', 'own_reserve_margin',
                          'own_raw_base_battery', 'own_strong_base_battery')


def pressure_features(building, index, diagnostics, config=None):
    config = config or CausalPeakConfig()
    scale = config.feature_power_scale
    storage = building.electrical_storage
    values = [diagnostics[key]/scale for key in ('past_peak', 'estimated_nonbattery', 'estimated_raw_base', 'deficit', 'available_extra_discharge', 'next_ns_forecast')]
    values += [storage.energy_init/storage.capacity-config.reserve_soc,
               diagnostics['raw_base'][3*index+1], diagnostics['strong_base'][3*index+1]]
    return np.clip(values, -5, 5).astype(np.float32)


def guard_residual(buildings, proposed, strong_base, config=None):
    config = config or CausalPeakConfig()
    final = np.asarray(proposed, dtype=float).copy()
    base = np.asarray(strong_base, dtype=float)
    clipped = []
    for b, building in enumerate(buildings):
        index = 3*b+1
        if building.power_outage:
            allowed = float(base[index])
            final[index] = allowed
        else:
            allowed = minimum_incremental_action(building.electrical_storage, float(base[index]), config.reserve_soc)
            final[index] = max(final[index], allowed)
        clipped.append(bool(abs(final[index]-proposed[index]) > 1e-8))
    return final, dict(guarded_buildings=clipped)
