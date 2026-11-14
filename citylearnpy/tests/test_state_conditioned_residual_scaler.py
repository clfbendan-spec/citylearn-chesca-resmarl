import joblib
import numpy as np

from state_conditioned_residual_scaler import StateConditionedResidualScaler


class ConstantModel:
    def __init__(self, value):
        self.value = value

    def predict(self, x):
        return np.full(len(x), self.value)


def test_scaler_clips_prediction_and_preserves_zero(tmp_path):
    path = tmp_path / 'model.joblib'
    joblib.dump(ConstantModel(-2.0), path)
    scaler = StateConditionedResidualScaler(path)
    assert scaler.predict([1, 2]) == -0.5
    assert scaler.scale(0.0, [1, 2]) == 0.0


def test_scaler_clips_positive_prediction_to_zero(tmp_path):
    path = tmp_path / 'model.joblib'
    joblib.dump(ConstantModel(1.0), path)
    scaler = StateConditionedResidualScaler(path)
    assert scaler.predict([1, 2]) == 0.0
