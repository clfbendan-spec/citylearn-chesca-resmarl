"""Finite causal thermal cut/recovery rule around an unchanged battery controller."""
import numpy as np
from causal_peak_controller import completed_district_peak
from v20_battery_capability import snapshot,predict
from dhw_grid_estimator import estimate
from causal_thermal_predictor import INPUT_NAMES


class PredictiveThermalRecovery:
    def __init__(self, buildings):
        self.buildings=buildings
        self.reset()

    def reset(self):
        self.active=[False]*self.buildings;self.events=[]

    def apply(self,buildings,raw,submitted,observers,contexts,reference_predictions,states,step,mode):
        action=np.asarray(submitted,dtype=float).copy()
        original=action.copy();past=completed_district_peak(buildings,step)
        diag=dict(step=int(step),mode=mode,past_peak_kw=float(past),changes=[],closures=[])
        def net(actions):
            total=0.
            for j,b in enumerate(buildings):
                cooling,dhw=estimate(b,j,raw,actions)
                total+=float(raw[f'non_shiftable_load_{j}'])-float(raw[f'solar_generation_{j}'])+cooling+dhw
                s=snapshot(b.electrical_storage)
                total+=predict(s,float(np.float32(actions[3*j+1]))*s.nominal_power_kw)['predicted_ac_flow_kwh']
            return total
        if mode=='identity' or step<24 or any(c['outage'] for c in contexts):
            diag['skip']='identity_warmup_or_outage';diag['active']=self.active.copy()
            return action,diag
        targets=reference_predictions
        baseline=[o.preview(c,float(action[3*j+2])) for j,(o,c) in enumerate(zip(observers,contexts))]
        diag['projected_before_kw']=net(action)
        for j,(state,temperature,target) in enumerate(zip(states,baseline,targets)):
            delta=state.temperature_c-state.reference_temperature_c
            if self.active[j] and temperature is not None and target is not None and delta<=1e-4 and temperature-target<=1e-4:
                self.active[j]=False
                event=dict(step=int(step),building=j+1,event='closed',last_temperature_delta_c=delta,predicted_delta_c=temperature-target)
                self.events.append(event);diag['closures'].append(event)
        if mode=='cut_recover':
            for j,(observer,context,base_temperature,target) in enumerate(zip(observers,contexts,baseline,targets)):
                if not self.active[j] or base_temperature is None or target is None or base_temperature<=target+1e-4:
                    continue
                lower=context['current'][INPUT_NAMES.index('indoor_dry_bulb_temperature_cooling_set_point')]-states[j].current_comfort_band_c
                choices=[]
                for extra in [.025,.05]:
                    value=min(1.,float(original[3*j+2])+extra)
                    if value<=action[3*j+2]+1e-8:continue
                    candidate=action.copy();candidate[3*j+2]=value
                    temperature=observer.preview(context,value);projected=net(candidate)
                    if temperature is not None and temperature>=lower-1e-4 and temperature<base_temperature-1e-4 and projected<=past+1e-6:
                        choices.append(dict(value=value,temperature=temperature,projected=projected))
                if choices:
                    meets=[c for c in choices if c['temperature']<=target+1e-4]
                    chosen=min(meets,key=lambda c:c['value']) if meets else min(choices,key=lambda c:c['temperature'])
                    before=float(action[3*j+2]);action[3*j+2]=chosen['value']
                    diag['changes'].append(dict(building=j+1,kind='recover',before=before,after=chosen['value'],predicted_before_c=base_temperature,predicted_after_c=chosen['temperature'],reference_prediction_c=target,projected_after_kw=chosen['projected']))
        # A building with unresolved heat excess cannot open a second cut.
        for j,(observer,context,target) in enumerate(zip(observers,contexts,targets)):
            if net(action)<=past+1e-6:break
            if self.active[j] or target is None or context['current'][INPUT_NAMES.index('occupant_count')]!=0:continue
            before=float(action[3*j+2]);value=max(0.,before-.05)
            if value>=before-1e-8:continue
            temperature=observer.preview(context,value)
            setpoint=states[j].current_setpoint_c;band=states[j].current_comfort_band_c
            if temperature is None or not setpoint-band<=temperature<=setpoint+band:continue
            candidate=action.copy();candidate[3*j+2]=value
            if net(action)-net(candidate)<=1e-6:continue
            action[3*j+2]=value;self.active[j]=True
            event=dict(step=int(step),building=j+1,event='opened',before=before,after=value,predicted_temperature_c=temperature,reference_prediction_c=target)
            self.events.append(event);diag['changes'].append(dict(building=j+1,kind='cut',before=before,after=value,predicted_after_c=temperature,reference_prediction_c=target,projected_after_kw=net(action)))
        assert all(abs(action[3*j+2]-original[3*j+2])<=.05+1e-8 for j in range(len(buildings)))
        diag['projected_after_kw']=net(action);diag['active']=self.active.copy()
        return action,diag
