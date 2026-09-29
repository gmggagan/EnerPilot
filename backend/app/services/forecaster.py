"""Energy forecast ML engine (HistGradientBoostingRegressor).

* Target: hourly household consumption (kWh).
* Features: time, weather, occupancy context, lags (1, 2, 24, 168 h) and the
  24 h rolling mean.
* Chronological split (last TEST_DAYS days held out, no shuffling).
* Evaluation: one-step and honest day-ahead recursive MAE/RMSE, compared with
  naive baselines (same hour previous day / previous week).
* Forecasting: recursive multi-step for 24 h, 3 d and 7 d horizons.
"""
from __future__ import annotations

import logging
import time
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from threadpoolctl import threadpool_limits

from .. import config as C

log = logging.getLogger("enerpilot.ml")
warnings.filterwarnings("ignore", message="Could not find the number of physical cores")

EXOG = ["hour", "hour_sin", "hour_cos", "day_of_week", "weekend", "month",
        "temperature", "humidity", "cloud_cover", "radiation", "heating_degree", "cooling_degree",
        "people_home", "awake", "wfh_count", "travel", "dog_home", "meal_period"]
LAGS = ["lag_1", "lag_2", "lag_24", "lag_168", "roll_mean_24"]
FEATURES = EXOG + LAGS

FEATURE_GROUPS = {
    "Time": ["hour", "hour_sin", "hour_cos", "day_of_week", "weekend", "month"],
    "Weather": ["temperature", "humidity", "cloud_cover", "radiation", "heating_degree", "cooling_degree"],
    "Context": ["people_home", "awake", "wfh_count", "travel", "dog_home", "meal_period"],
    "Lags": LAGS,
}


def exogenous(weather: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    idx = weather.index
    X = pd.DataFrame(index=idx)
    X["hour"] = idx.hour
    X["hour_sin"] = np.sin(2 * np.pi * idx.hour / 24)
    X["hour_cos"] = np.cos(2 * np.pi * idx.hour / 24)
    X["day_of_week"] = idx.dayofweek
    X["weekend"] = (idx.dayofweek >= 5).astype(int)
    X["month"] = idx.month
    for col in ["temperature", "humidity", "cloud_cover", "radiation"]:
        X[col] = weather[col].values
    X["heating_degree"] = np.maximum(0, 17 - weather["temperature"].values)
    X["cooling_degree"] = np.maximum(0, weather["temperature"].values - 25)
    for col in ["people_home", "awake", "wfh_count", "travel", "dog_home", "meal_period"]:
        X[col] = context[col].values
    return X


def add_lags(X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    X = X.copy()
    X["lag_1"] = y.shift(1).values
    X["lag_2"] = y.shift(2).values
    X["lag_24"] = y.shift(24).values
    X["lag_168"] = y.shift(168).values
    X["roll_mean_24"] = y.shift(1).rolling(24).mean().values
    return X


def _new_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                                         min_samples_leaf=20, l2_regularization=0.1, random_state=C.SEED)


def _metrics(y_true, y_pred) -> dict:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    mask = y_true > 0.05
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
        "mape_pct": round(float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100), 2),
    }


def recursive_forecast(model, X_exog: pd.DataFrame, y_hist: np.ndarray) -> np.ndarray:
    """Multi-step recursive forecast. y_hist must hold >= 168 past values."""
    series = list(np.asarray(y_hist, dtype=float))
    exog = X_exog[EXOG].to_numpy(dtype=float)
    preds = np.empty(len(exog))
    with threadpool_limits(1):  # single-row predictions are faster without OpenMP fan-out
        _recurse(model, exog, series, preds)
    return preds


def _recurse(model, exog: np.ndarray, series: list, preds: np.ndarray) -> None:
    for i in range(len(exog)):
        n = len(series)
        lags = [series[n - 1], series[n - 2], series[n - 24], series[n - 168], float(np.mean(series[n - 24:n]))]
        row = np.concatenate([exog[i], lags])[None, :]
        p = float(model.predict(row)[0])
        p = min(max(p, 0.05), C.MAX_POWER_KW)
        preds[i] = p
        series.append(p)


class Forecaster:
    def __init__(self):
        self.model: HistGradientBoostingRegressor | None = None
        self.metrics: dict = {}
        self.residual_sigma = 0.25
        self.trained_at: str | None = None

    def fit(self, weather: pd.DataFrame, sim: pd.DataFrame) -> dict:
        t0 = time.time()
        y = sim["total"]
        X = add_lags(exogenous(weather, sim), y)
        data = X.assign(y=y.values).iloc[168:]
        n_test = C.TEST_DAYS * 24
        train, test = data.iloc[:-n_test], data.iloc[-n_test:]

        model = _new_model().fit(train[FEATURES].to_numpy(float), train["y"].to_numpy())
        one_step = model.predict(test[FEATURES].to_numpy(float))

        # honest day-ahead evaluation: recursive 24 h forecasts for each test day
        offset = len(data) - n_test
        y_full = y.to_numpy()
        base = len(y_full) - len(data)  # rows dropped by the 168 h warm-up
        day_ahead = np.empty(n_test)
        for d in range(C.TEST_DAYS):
            s = offset + d * 24
            hist = y_full[: base + s]
            day_ahead[d * 24:(d + 1) * 24] = recursive_forecast(model, data.iloc[s:s + 24], hist)
        y_test = test["y"].to_numpy()
        naive_day = test["lag_24"].to_numpy()
        naive_week = test["lag_168"].to_numpy()

        imp = permutation_importance(model, test[FEATURES].to_numpy(float), test["y"].to_numpy(), n_repeats=5, random_state=C.SEED,
                                     scoring="neg_mean_absolute_error")
        importances = sorted(({"feature": f, "importance": round(float(v), 4)}
                              for f, v in zip(FEATURES, imp.importances_mean)), key=lambda r: -r["importance"])
        groups = {g: round(float(sum(max(0.0, r["importance"]) for r in importances if r["feature"] in fs)), 4)
                  for g, fs in FEATURE_GROUPS.items()}

        # refit on the whole history for production forecasting
        self.model = _new_model().fit(data[FEATURES].to_numpy(float), data["y"].to_numpy())
        self.residual_sigma = float(np.std(y_test - day_ahead))
        m_day = _metrics(y_test, day_ahead)
        m_naive_day = _metrics(y_test, naive_day)
        m_naive_week = _metrics(y_test, naive_week)
        self.trained_at = pd.Timestamp.now().isoformat(timespec="seconds")
        self.metrics = {
            "model": "HistGradientBoostingRegressor",
            "params": {k: v for k, v in self.model.get_params().items()
                       if k in ("max_iter", "learning_rate", "max_leaf_nodes", "min_samples_leaf", "l2_regularization", "random_state")},
            "target": "Hourly household consumption (kWh)",
            "split": "chronological",
            "train_rows": int(len(train)), "test_rows": int(len(test)),
            "train_period": [str(train.index[0]), str(train.index[-1])],
            "test_period": [str(test.index[0]), str(test.index[-1])],
            "features": FEATURES, "feature_groups": FEATURE_GROUPS,
            "evaluation": {
                "model_one_step": _metrics(y_test, one_step),
                "model_day_ahead": m_day,
                "naive_same_hour_previous_day": m_naive_day,
                "naive_same_hour_previous_week": m_naive_week,
            },
            "improvement_vs_naive_day_pct": round((1 - m_day["mae"] / m_naive_day["mae"]) * 100, 1),
            "improvement_vs_naive_week_pct": round((1 - m_day["mae"] / m_naive_week["mae"]) * 100, 1),
            "feature_importance": importances[:12],
            "feature_group_importance": groups,
            "residual_sigma_kwh": round(self.residual_sigma, 4),
            "test_series": [{"time": t.strftime("%Y-%m-%d %H:%M"), "actual": round(float(a), 3),
                             "predicted": round(float(p), 3), "naive_day": round(float(n), 3)}
                            for t, a, p, n in zip(test.index, y_test, day_ahead, naive_day)],
            "trained_at": self.trained_at,
            "training_seconds": round(time.time() - t0, 2),
        }
        try:
            joblib.dump(self.model, C.DATA_DIR / "enerpilot_hgb.joblib")
        except Exception as exc:  # persistence is best-effort
            log.warning("could not persist model: %s", exc)
        return self.metrics

    def predict(self, weather: pd.DataFrame, context: pd.DataFrame, y_hist: pd.Series) -> pd.DataFrame:
        X = exogenous(weather, context)
        pred = recursive_forecast(self.model, X, y_hist.to_numpy())
        band = 1.28 * self.residual_sigma
        return pd.DataFrame({"predicted": pred, "lower": np.maximum(pred - band, 0.05),
                             "upper": np.minimum(pred + band, C.MAX_POWER_KW)}, index=weather.index)
