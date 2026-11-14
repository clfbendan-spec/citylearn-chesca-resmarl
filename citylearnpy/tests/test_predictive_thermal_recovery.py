from types import SimpleNamespace as NS
from unittest.mock import patch
from predictive_thermal_recovery import PredictiveThermalRecovery
from causal_thermal_predictor import INPUT_NAMES


def inputs(occupied=0):
    b=NS(electrical_storage=NS(nominal_power_kw=1.))
    raw={'non_shiftable_load_0':0.,'solar_generation_0':0.}
    current=[0.]*len(INPUT_NAMES);current[INPUT_NAMES.index('occupant_count')]=occupied
    context=dict(current=tuple(current),outage=False)
    state=NS(temperature_c=25.1,reference_temperature_c=25.,current_setpoint_c=25.,current_comfort_band_c=2.)
    return [b],raw,[context],[state]


def physics(peak):
    return (patch('predictive_thermal_recovery.completed_district_peak',return_value=peak),
        patch('predictive_thermal_recovery.estimate',side_effect=lambda b,j,raw,a:(float(a[2])*20.,0.)),
        patch('predictive_thermal_recovery.snapshot',side_effect=lambda s:s),
        patch('predictive_thermal_recovery.predict',return_value={'predicted_ac_flow_kwh':0.}))


def run(rule,args,action,model,target,mode,peak):
    b,raw,contexts,states=args;p=physics(peak)
    with p[0],p[1],p[2],p[3]:
        return rule.apply(b,raw,[0.,0.,action],[NS(preview=model)],contexts,[target],states,40,mode)


def test_unoccupied_prediction_cut_and_occupied_rejection():
    rule=PredictiveThermalRecovery(1)
    result,diag=run(rule,inputs(),.55,lambda c,a:26.8,25.,'cut_only',10.)
    assert abs(result[2]-.5)<1e-7 and rule.active==[True] and diag['changes'][0]['kind']=='cut'
    rule.reset();result,diag=run(rule,inputs(1),.55,lambda c,a:26.8,25.,'cut_only',10.)
    assert result[2]==.55 and not diag['changes']


def test_recovery_picks_smallest_candidate_reaching_target():
    rule=PredictiveThermalRecovery(1);rule.active=[True]
    result,diag=run(rule,inputs(),.4,lambda c,a:25.1-2*(a-.4),25.05,'cut_recover',10.)
    assert abs(result[2]-.425)<1e-7 and diag['changes'][0]['kind']=='recover'


def test_recovery_cannot_create_a_new_peak_and_reset_clears_episode():
    rule=PredictiveThermalRecovery(1);rule.active=[True]
    result,diag=run(rule,inputs(),.4,lambda c,a:25.1-2*(a-.4),25.,'cut_recover',8.05)
    assert result[2]==.4 and not diag['changes']
    rule.reset();assert rule.active==[False] and rule.events==[]


def test_out_of_band_prediction_rejects_cut():
    rule=PredictiveThermalRecovery(1)
    result,diag=run(rule,inputs(),.55,lambda c,a:27.1,25.,'cut_only',10.)
    assert result[2]==.55 and not diag['changes']


if __name__=='__main__':
    tests=[v for k,v in list(globals().items()) if k.startswith('test_') and callable(v)]
    for test in tests:test()
    print(f'{len(tests)} predictive recovery unit tests passed')
