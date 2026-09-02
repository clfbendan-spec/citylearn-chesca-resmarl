import numpy as np
from pathlib import Path
from xgboost import XGBRegressor

_PRETRAINED_DIR = Path(__file__).resolve().parent / "pretrained"


class PreTrainedXGBoost:
    def __init__(self, steps_ahead, variable_name):
        self.tau = steps_ahead
        self.variable_name = variable_name

        # Load pretrained XGBoost models (for all buildings)
        self.pretrained_xgboost = []
        for i in range(steps_ahead):
            path = _PRETRAINED_DIR / f"xgboost_{variable_name}_{i}_1.json"
            model1 = XGBRegressor()
            model1.load_model(str(path))
            path = _PRETRAINED_DIR / f"xgboost_{variable_name}_{i}_2.json"
            model2 = XGBRegressor()
            model2.load_model(str(path))
            self.pretrained_xgboost.append([model1, model2])
            #self.pretrained_xgboost.append([model1])

        self.last_predictions = np.zeros(self.tau)

    def predict(self, X):
        """ X: 1D array with features for predicting variable """
        # Predict with XGBoost Pretrained models
        pred_pretrained_xgboost = np.zeros(self.tau)
        for i in range(self.tau):
            pred_pretrained_xgboost[i] = (self.pretrained_xgboost[i][0].predict(X[np.newaxis, :]) + self.pretrained_xgboost[i][1].predict(X[np.newaxis, :]))/2
            #pred_pretrained_xgboost[i] = self.pretrained_xgboost[i][0].predict(X[np.newaxis, :])

            # make sure predictions are positive
            pred_pretrained_xgboost[pred_pretrained_xgboost < 0] = 0

        self.last_predictions = pred_pretrained_xgboost

        return pred_pretrained_xgboost
