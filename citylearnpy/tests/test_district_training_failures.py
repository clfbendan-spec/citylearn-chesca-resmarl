"""Failure contracts at the real training entrypoint, without starting Ray."""
from pathlib import Path
import json

import pytest


def test_missing_explicit_resume_fails_before_starting_runtime(tmp_path, monkeypatch):
    from district_marl import district_train as train
    import utils.train as runtime

    def forbidden_runtime(**kwargs):
        raise AssertionError('Ray must not start for a missing resume source')

    monkeypatch.setattr(runtime, 'ensure_ray_initialized', forbidden_runtime)
    output = tmp_path / 'task'
    with pytest.raises(FileNotFoundError):
        train.main(['--resume', str(tmp_path / 'missing'),
                    '--output-dir', str(output)])
    assert not output.exists()


@pytest.mark.parametrize('completed', [0, 1])
def test_training_exception_is_not_success_and_does_not_publish_evaluation(
        tmp_path, monkeypatch, completed):
    from district_marl import district_train as train
    from ray.rllib.algorithms.sac import SACConfig
    import ray
    import utils.train as runtime

    class FailingLearner:
        def __init__(self):
            self.calls = 0
            self.stopped = False

        def train(self):
            self.calls += 1
            if self.calls > completed:
                raise RuntimeError('injected learner failure')
            return {}

        def save(self, checkpoint_dir):
            destination = Path(checkpoint_dir)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / 'incorrect-success-model').write_bytes(b'not a model')
            return str(destination)

        def stop(self):
            self.stopped = True

    learner = FailingLearner()
    monkeypatch.setattr(runtime, 'ensure_ray_initialized', lambda **kwargs: None)
    monkeypatch.setattr(SACConfig, 'build', lambda self: learner)
    monkeypatch.setattr(ray, 'shutdown', lambda: None)
    # The failure is in learning, not in CityLearn rollout. Old code continued
    # here and published a success summary; keep that route executable for RED.
    monkeypatch.setattr(train, 'rollout_district', lambda *args, **kwargs: {})
    schema = Path(__file__).resolve().parents[3] / (
        'datasets/citylearn_challenge_2023_phase_2_local_evaluation/schema.json')
    output = tmp_path / 'task'
    with pytest.raises(RuntimeError, match='injected learner failure'):
        train.main(['--output-dir', str(output), '--train-schema', str(schema),
                    '--eval-schema', str(schema), '--train-epochs', '3',
                    '--eval-every', '3', '--no-diag', '--peak-stop-patience', '0'])
    status = json.loads((output / 'training_status.json').read_text(encoding='utf-8'))
    assert status['execution_status'] == 'failed'
    assert status['epochs_done'] == completed
    assert status['failed_epoch'] == completed + 1
    assert status['error_type'] == 'RuntimeError'
    assert status['error'] == 'injected learner failure'
    assert learner.stopped
    assert not (output / 'district_summary.json').exists()
    assert not (output / 'exported_kpis.csv').exists()
    assert not list(output.rglob('incorrect-success-model'))
