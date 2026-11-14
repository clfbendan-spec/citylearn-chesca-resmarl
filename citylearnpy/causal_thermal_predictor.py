"""Current-interval forward prediction using the installed known LSTM model.

This does not fit a model or read an outcome temperature at decision index t.
Only normalized completed history, prior model state, current exogenous signals
and the proposed cooling action enter the forward calculation. Accuracy against
this simulator is model-consistency evidence, not real-world forecast validation.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
import torch


INPUT_NAMES = (
    'direct_solar_irradiance', 'diffuse_solar_irradiance',
    'outdoor_dry_bulb_temperature', 'indoor_dry_bulb_temperature_cooling_set_point',
    'occupant_count', 'cooling_demand', 'month_sin', 'month_cos',
    'hour_sin', 'hour_cos', 'day_type_sin', 'day_type_cos',
    'indoor_dry_bulb_temperature',
)


@dataclass(frozen=True)
class ThermalSnapshot:
    decision_step: int
    history_end_step: int
    model: object
    history: tuple
    hidden_state: tuple
    current: tuple
    minimum: tuple
    maximum: tuple
    lookback: int
    nominal_power_kw: float
    available_power_kw: float
    cooling_cop: float
    hvac_mode: int
    cooling_action_active: bool


def capture(building):
    """Capture current information only. Return None for outages/unready history."""
    if building.power_outage:
        return None
    model = building.dynamics
    if tuple(model.input_observation_names) != INPUT_NAMES:
        raise ValueError('Unverified thermal model input schema')
    if building.seconds_per_time_step != 3600 or building.algorithm_action_based_time_step_hours_ratio != 1 or building.cooling_storage.capacity != 0:
        raise ValueError('Unverified cooling device/time resolution')
    lookback = int(model.lookback)
    history = tuple(tuple(v[-lookback:]) for v in model._model_input)
    if any(len(v) != lookback or any(x is None for x in v) for v in history):
        return None
    if any(isinstance(m, torch.nn.Dropout) and m.training and m.p > 0 for m in model.modules()):
        raise ValueError('Stochastic training-mode dropout is not supported')
    if model.l_lstm.training and model.l_lstm.dropout > 0:
        raise ValueError('Stochastic LSTM dropout is not supported')
    obs = building.observations(include_all=True, normalize=False, periodic_normalization=True)
    # The current indoor slot is explicitly excluded; no value from it is stored.
    current = tuple(0. if k == 'indoor_dry_bulb_temperature' else float(obs[k]) for k in INPUT_NAMES)
    t = int(building.time_step)
    outside = float(obs['outdoor_dry_bulb_temperature'])
    return ThermalSnapshot(t, t-1, model, history,
        tuple(h.detach().clone() for h in model._hidden_state), current,
        tuple(model.input_normalization_minimum), tuple(model.input_normalization_maximum),
        lookback, float(building.cooling_device.nominal_power),
        float(building.cooling_device.available_nominal_power),
        float(building.cooling_device.get_cop(outside, heating=False)),
        int(building.energy_simulation.hvac_mode[t]), bool(building.simulate_dynamics))


def predict(snapshot, cooling_action):
    if snapshot is None:
        return None
    s = snapshot
    action = float(np.float32(cooling_action))
    if not -1e-7 <= action <= 1.+1e-7:
        raise ValueError('Cooling action outside [0,1]')
    current = list(s.current)
    if s.cooling_action_active:
        demand = min(action*s.nominal_power_kw, s.available_power_kw)*s.cooling_cop if s.hvac_mode in (1,3) else 0.
        current[INPUT_NAMES.index('cooling_demand')] = float(np.float32(demand))
    rows = []
    for k, past, value, low, high in zip(INPUT_NAMES,s.history,current,s.minimum,s.maximum):
        if k == 'indoor_dry_bulb_temperature':
            rows.append(past)
        else:
            rows.append(tuple(past[1:])+((value-low)/(high-low),))
    x = torch.tensor(np.asarray(rows,dtype=np.float32).T)[None,:,:]
    hidden = tuple(h.detach().clone() for h in s.hidden_state)
    before_rng = torch.get_rng_state().clone()
    with torch.no_grad():
        normalized, _ = s.model(x.float(), hidden)
        ix = INPUT_NAMES.index('indoor_dry_bulb_temperature')
        temperature = float((normalized*(s.maximum[ix]-s.minimum[ix])+s.minimum[ix]).item())
    if not torch.equal(before_rng,torch.get_rng_state()):
        raise AssertionError('Thermal forward consumed simulation RNG')
    if not math.isfinite(temperature):
        raise ValueError('Nonfinite thermal prediction')
    return temperature
