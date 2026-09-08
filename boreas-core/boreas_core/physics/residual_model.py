"""Residual correction model: learns the gap between the physics drift
baseline and observed drift (BOREAS design doc §5.3).

Gradient-boosted trees (XGBoost) rather than a neural net, per the design
doc's feasibility argument: the residual-learning task is small-data-friendly
and doesn't need representation learning, so a GBM gets SHAP-explainable
attributions "for free" (explain/shap_explain.py) at a fraction of the
training cost and data requirement of a deep model.
"""

from dataclasses import dataclass, field

import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

from boreas_core.data.synthetic_drift import FEATURE_COLUMNS, SyntheticDriftDataset


@dataclass
class ResidualModelMetrics:
    mae_baseline_ms: float  # error of "assume zero residual" (pure physics)
    mae_model_ms: float
    improvement_pct: float


@dataclass
class ResidualDriftModel:
    """Two independent XGBoost regressors (east/north components)."""

    n_estimators: int = 200
    max_depth: int = 4
    learning_rate: float = 0.05
    model_east_: xgb.XGBRegressor | None = field(default=None, repr=False)
    model_north_: xgb.XGBRegressor | None = field(default=None, repr=False)

    def _new_regressor(self) -> xgb.XGBRegressor:
        return xgb.XGBRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            objective="reg:squarederror",
        )

    def fit(self, dataset: SyntheticDriftDataset, *, test_size: float = 0.2, seed: int = 0) -> ResidualModelMetrics:
        X = dataset.X
        y = dataset.y  # (N, 2): [residual_east, residual_north]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=seed
        )

        self.model_east_ = self._new_regressor().fit(X_train, y_train[:, 0])
        self.model_north_ = self._new_regressor().fit(X_train, y_train[:, 1])

        pred = self.predict(X_test)
        mae_model = mean_absolute_error(y_test, pred)
        mae_baseline = mean_absolute_error(y_test, np.zeros_like(y_test))
        improvement = 100.0 * (mae_baseline - mae_model) / mae_baseline

        return ResidualModelMetrics(
            mae_baseline_ms=float(mae_baseline),
            mae_model_ms=float(mae_model),
            improvement_pct=float(improvement),
        )

    def _check_fitted(self) -> None:
        if self.model_east_ is None or self.model_north_ is None:
            raise RuntimeError("ResidualDriftModel must be fit() before use.")

    def predict(self, X: np.ndarray) -> np.ndarray:
        self._check_fitted()
        X = np.atleast_2d(X)
        east = self.model_east_.predict(X)
        north = self.model_north_.predict(X)
        return np.stack([east, north], axis=1)

    def predict_single(self, feature_row: dict) -> np.ndarray:
        x = np.array([[feature_row[col] for col in FEATURE_COLUMNS]])
        return self.predict(x)[0]

    def as_residual_correction_fn(self):
        """Adapts this model to the `residual_correction` hook expected by
        `physics.drift.PhysicsDriftModel.simulate`.
        """

        def _correction(ctx: dict) -> np.ndarray:
            geometry = ctx["geometry"]
            velocity = ctx["velocity"]
            wind = ctx["wind"]
            current = ctx["current"]
            row = {
                "physics_vel_east": velocity[0],
                "physics_vel_north": velocity[1],
                "wind_east": wind[0],
                "wind_north": wind[1],
                "current_east": current[0],
                "current_north": current[1],
                "latitude": ctx["lat"],
                "length_m": geometry.length_m,
                "width_m": geometry.width_m,
                "thickness_m": geometry.thickness_m,
                "sail_area_m2": geometry.sail_area_m2,
                "draft_area_m2": geometry.draft_area_m2,
            }
            return self.predict_single(row)

        return _correction
