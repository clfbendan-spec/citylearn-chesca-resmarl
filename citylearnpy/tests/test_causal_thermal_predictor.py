from dataclasses import replace
import torch
from causal_thermal_predictor import INPUT_NAMES, ThermalSnapshot, predict


class ToyModel(torch.nn.Module):
    def forward(self, x, hidden):
        hidden[0].add_(100.)  # Predictor must pass an owned copy.
        t=INPUT_NAMES.index('indoor_dry_bulb_temperature')
        c=INPUT_NAMES.index('cooling_demand')
        return x[:,-1,t:t+1]+.5*x[:,-1,c:c+1],hidden


def snapshot():
    n=len(INPUT_NAMES);low=[0.]*n;high=[1.]*n
    low[-1]=10.;high[-1]=30.;high[5]=12.
    current=[0.]*n;current[-1]=99999.
    return ThermalSnapshot(20,19,ToyModel(),tuple((.2,.4) for _ in range(n)),
        (torch.zeros(1),),tuple(current),tuple(low),tuple(high),2,4.,4.,3.,1,True)


def test_manual_action_response_and_unrealized_slot_independence():
    s=snapshot()
    assert abs(predict(s,0.)-18.)<1e-6
    assert abs(predict(s,.5)-23.)<1e-6
    assert predict(replace(s,current=s.current[:-1]+(-99999.,)),.5)==predict(s,.5)


def test_hidden_state_and_rng_are_preserved():
    s=snapshot();rng=torch.get_rng_state().clone();h=s.hidden_state[0].clone()
    predict(s,.5)
    assert torch.equal(h,s.hidden_state[0]) and torch.equal(rng,torch.get_rng_state())


def test_mode_off_and_warmup_action_semantics():
    s=snapshot()
    assert predict(replace(s,hvac_mode=0),.5)==predict(s,0.)
    current=list(s.current);current[5]=6.
    initial=replace(s,cooling_action_active=False,current=tuple(current))
    assert predict(initial,0.)==predict(initial,1.) and abs(predict(initial,0.)-23.)<1e-6


def test_invalid_actions_are_rejected():
    try:
        predict(snapshot(),1.2)
    except ValueError as error:
        assert 'outside' in str(error)
    else:
        raise AssertionError('Invalid action accepted')
    assert predict(None,.5) is None


if __name__ == '__main__':
    tests=[v for k,v in list(globals().items()) if k.startswith('test_') and callable(v)]
    for test in tests:
        test()
    print(f'{len(tests)} predictor unit tests passed')
