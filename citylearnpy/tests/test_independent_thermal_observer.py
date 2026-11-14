import torch
from independent_thermal_observer import IndependentThermalObserver
from causal_thermal_predictor import INPUT_NAMES


class StaticTemplate:
    input_observation_names=INPUT_NAMES
    input_normalization_minimum=(0.,)*len(INPUT_NAMES)
    input_normalization_maximum=(40.,)*len(INPUT_NAMES)
    lookback=2
    def __init__(self):
        self.l_lstm=torch.nn.LSTM(len(INPUT_NAMES),3,batch_first=True)
        self.dropout=torch.nn.Dropout(0)
        self.l_linear=torch.nn.Linear(3,1)
    def __getattr__(self,name):
        if name in ['_hidden_state','_model_input']:
            raise AssertionError('Simulator internal state read')
        raise AttributeError(name)


def context(t):
    return dict(step=t,current=(1.,)*len(INPUT_NAMES),nominal_power_kw=4.,available_power_kw=4.,cooling_cop=3.,hvac_mode=1,outage=False)


def test_static_initialization_owns_weights_without_internal_state():
    template=StaticTemplate();observer=IndependentThermalObserver(template)
    assert observer.model.l_lstm.weight_ih_l0.data_ptr()!=template.l_lstm.weight_ih_l0.data_ptr()
    assert observer.step==0 and not observer.cooling_action_active


def test_sequence_reset_and_completed_measurement_history():
    o=IndependentThermalObserver(StaticTemplate())
    for t in range(3):
        c=context(t);o.begin(c);o.preview(c,.2);o.commit(25.+t,3.)
    assert o.step==3 and o.history[-1][-1]==27./40.
    o.reset();assert o.step==0 and o.pending is None and all(v is None for v in o.history[-1])


def test_no_mutation_from_preview_and_independent_weight_changes():
    template=StaticTemplate();o=IndependentThermalObserver(template)
    for t in range(3):o.begin(context(t));o.commit(25.,3.)
    c=context(3);o.begin(c);h=[x.clone() for x in o.hidden];rng=torch.get_rng_state().clone();y=o.preview(c,.2)
    with torch.no_grad():template.l_linear.weight.add_(100.)
    assert y==o.preview(c,.2) and all(torch.equal(a,b) for a,b in zip(h,o.hidden))
    assert torch.equal(rng,torch.get_rng_state())


def test_timestamp_protocol_rejects_missing_or_duplicate_transitions():
    o=IndependentThermalObserver(StaticTemplate())
    for call in [lambda:o.commit(25.,0.),lambda:o.begin(context(1))]:
        try:call()
        except ValueError:pass
        else:raise AssertionError('Invalid sequence accepted')
    o.begin(context(0))
    try:o.begin(context(0))
    except ValueError:pass
    else:raise AssertionError('Duplicate begin accepted')


if __name__=='__main__':
    tests=[v for k,v in list(globals().items()) if k.startswith('test_') and callable(v)]
    for test in tests:test()
    print(f'{len(tests)} independent observer unit tests passed')
