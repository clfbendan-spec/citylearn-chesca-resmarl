"""Optional local-trained residual scaler for CHESCA residual actions.

The scaler is deliberately independent of the environment.  It clips every
prediction to the audited deployment interval [-0.5, 0] and exposes a small
feature builder so callers can log the exact input used for a decision.
"""
from pathlib import Path
from typing import Sequence

import numpy as np


class StateConditionedResidualScaler:
    def __init__(self, model_path, minimum=-0.5, maximum=0.0):
        self.model_path = str(model_path)
        self.minimum = float(minimum)
        self.maximum = float(maximum)
        if self.minimum > self.maximum:
            raise ValueError('minimum must not exceed maximum')
        try:
            import joblib
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError('joblib is required to load a residual scaler') from exc
        self.model = joblib.load(Path(self.model_path))

    def predict(self, features: Sequence[float]) -> float:
        x = np.asarray(features, dtype=np.float32).reshape(1, -1)
        value = float(np.asarray(self.model.predict(x)).reshape(-1)[0])
        return float(np.clip(value, self.minimum, self.maximum))

    def scale(self, raw_residual: float, features: Sequence[float]) -> float:
        return self.predict(features) * float(raw_residual)

