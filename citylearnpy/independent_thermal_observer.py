"""Control-owned known-model state advanced from public, completed measurements.

Only static model metadata/layers are copied at construction. No simulator
history or hidden state is retained or read during initialization or execution.
"""
from __future__ import annotations
import copy
from dataclasses import replace
import numpy as np
import torch
from causal_thermal_predictor import INPUT_NAMES, ThermalSnapshot, predict


class FrozenThermalNetwork(torch.nn.Module):
    def __init__(self, template):
        super().__init__()
        self.l_lstm=copy.deepcopy(template.l_lstm)
        self.dropout=copy.deepcopy(template.dropout)
        self.l_linear=copy.deepcopy(template.l_linear)
        if self.l_lstm.bidirectional or self.l_lstm.proj_size:
            raise ValueError('Unverified LSTM structure')
        if self.dropout.training and self.dropout.p or self.l_lstm.training and self.l_lstm.dropout:
            raise ValueError('Stochastic dropout is unsupported')
        self.requires_grad_(False)

    def forward(self,x,h):
        sequence,h=self.l_lstm(x,h)
        sequence=self.dropout(sequence)
        return self.l_linear(sequence[:,-1,:]),h


def public_context(building, cooling_action_active):
    """Read explicitly current public signals; never call dynamics or observations."""
    t=int(building.time_step);weather=building.weather;sim=building.energy_simulation
    current={name:float(getattr(weather,name)[t]) for name in ['direct_solar_irradiance','diffuse_solar_irradiance','outdoor_dry_bulb_temperature']}
    current['indoor_dry_bulb_temperature_cooling_set_point']=float(building.indoor_dry_bulb_temperature_cooling_set_point[t])
    current['occupant_count']=float(building.occupant_count[t])
    current['cooling_demand']=0. if cooling_action_active else float(building.cooling_demand[t])
    for name,period in [('month',12),('hour',24),('day_type',7)]:
        angle=2*np.pi*float(getattr(sim,name)[t])/period
        current[name+'_sin']=float(np.sin(angle));current[name+'_cos']=float(np.cos(angle))
    current['indoor_dry_bulb_temperature']=0.  # Never read the unrealized slot.
    return dict(step=t,current=tuple(current[k] for k in INPUT_NAMES),
        nominal_power_kw=float(building.cooling_device.nominal_power),
        available_power_kw=float(building.cooling_device.available_nominal_power),
        cooling_cop=float(building.cooling_device.get_cop(current['outdoor_dry_bulb_temperature'],heating=False)),
        hvac_mode=int(sim.hvac_mode[t]),outage=bool(building.power_outage))


class IndependentThermalObserver:
    def __init__(self, template):
        if tuple(template.input_observation_names)!=INPUT_NAMES:
            raise ValueError('Unverified thermal input schema')
        self.model=FrozenThermalNetwork(template)
        self.minimum=tuple(template.input_normalization_minimum)
        self.maximum=tuple(template.input_normalization_maximum)
        self.lookback=int(template.lookback)
        self.reset()

    def reset(self):
        self.step=0;self.pending=None
        self.history=[[None]*(self.lookback+1) for _ in INPUT_NAMES]
        weight=next(self.model.parameters())
        shape=(self.model.l_lstm.num_layers,1,self.model.l_lstm.hidden_size)
        self.hidden=tuple(torch.zeros(shape,dtype=weight.dtype,device=weight.device) for _ in range(2))

    @property
    def cooling_action_active(self):
        return self.history[0][0] is not None

    def snapshot(self, context, allow_outage=False):
        if context['step']!=self.step:
            raise ValueError('Decision timestamp mismatch')
        history=tuple(tuple(v[-self.lookback:]) for v in self.history)
        if any(x is None for row in history for x in row) or context['outage'] and not allow_outage:
            return None
        return ThermalSnapshot(self.step,self.step-1,self.model,history,
            tuple(h.detach().clone() for h in self.hidden),tuple(context['current']),
            self.minimum,self.maximum,self.lookback,context['nominal_power_kw'],
            context['available_power_kw'],context['cooling_cop'],context['hvac_mode'],self.cooling_action_active)

    def begin(self, context):
        if self.pending is not None:
            raise ValueError('Previous transition not committed')
        if context['step']!=self.step:
            raise ValueError('Decision timestamp mismatch')
        self.pending=copy.deepcopy(context)

    def preview(self, context, action):
        return predict(self.snapshot(context),action)

    def commit(self, temperature_c, cooling_demand):
        if self.pending is None:
            raise ValueError('No pending transition')
        current=list(self.pending['current'])
        current[INPUT_NAMES.index('cooling_demand')]=float(cooling_demand)
        snapshot=self.snapshot(self.pending,allow_outage=True)
        if snapshot is not None:
            rows=[]
            for k,past,value,low,high in zip(INPUT_NAMES,snapshot.history,current,self.minimum,self.maximum):
                rows.append(past if k=='indoor_dry_bulb_temperature' else tuple(past[1:])+((value-low)/(high-low),))
            x=torch.tensor(np.asarray(rows,dtype=np.float32).T)[None,:,:]
            with torch.no_grad():
                _,hidden=self.model(x.float(),tuple(h.detach().clone() for h in self.hidden))
            self.hidden=tuple(h.detach().clone() for h in hidden)
        # Anchor temperature history to the now completed measurement, never to
        # an unavailable current slot. Small inverse-normalization rounding is
        # deliberately retained and measured in the consistency experiment.
        current[-1]=float(temperature_c)
        self.history=[past[-self.lookback:]+[(value-low)/(high-low)]
            for past,value,low,high in zip(self.history,current,self.minimum,self.maximum)]
        self.step+=1;self.pending=None
