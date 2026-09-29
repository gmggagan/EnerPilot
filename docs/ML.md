# Forecasting Engine (ML)

## Target and data
- **Target:** hourly household consumption (kWh).
- **Training data:** the 365-day simulated historical profile (real Open-Meteo Lisbon weather + context engine), about 8,600 hourly rows after the 168 h lag warm-up.

## Model
`sklearn.ensemble.HistGradientBoostingRegressor` with `max_iter=300`, `learning_rate=0.06`, `max_leaf_nodes=31`,
`min_samples_leaf=20`, `l2_regularization=0.1` and `random_state=42`. The trained model is persisted with joblib to `backend/data/enerpilot_hgb.joblib`.

## Features (23)
| Group | Features |
|---|---|
| Time | hour, hour_sin, hour_cos, day_of_week, weekend, month |
| Weather | temperature, humidity, cloud_cover, radiation, heating_degree (17 − T)+, cooling_degree (T − 25)+ |
| Context | people_home, awake, wfh_count, travel, dog_home, meal_period |
| Lags | lag_1, lag_2, lag_24, lag_168, roll_mean_24 (mean of the previous 24 h) |

Context features for future hours come from the occupancy plan, or from the user's what-if choice. This is how the forecast accounts for "the expected presence or absence of the residents".

## Training and evaluation
- **Chronological split:** the last 14 days (336 h) are held out, with no shuffling.
- **One-step metrics:** the lags use actual values.
- **Day-ahead recursive metrics (the honest number):** for every test day, a 24 h forecast is made recursively from that day's midnight, feeding predictions back as lags.
- **Baselines:** same hour previous day (naive-24) and same hour previous week (naive-168).
- **Final model:** after evaluation, the model is refit on the full history.

Results from the live run on 29 Sep 2026 (they change slightly as the weather window moves):

| Model | MAE (kWh) | RMSE (kWh) | R² |
|---|---|---|---|
| HGB day-ahead recursive | 0.089 | 0.169 | 0.92 |
| HGB one-step | 0.080 | 0.161 | 0.93 |
| Naive previous day | 0.304 | 0.595 | −0.01 |
| Naive previous week | 0.318 | 0.632 | −0.14 |

Day-ahead MAE is **≈71 % lower** than the previous-day baseline and **≈72 % lower** than the previous-week baseline.

**Permutation importance on the test set:** context features (meal period, awake, occupancy) matter most, followed by weather (temperature, cooling degree) and then the lags. This is consistent with Scenario 5: the household's presence and routines drive demand.

## Forecasting
- Recursive multi-step forecast from the current Lisbon hour: 24 h (primary), 72 h and 168 h. The first 24 h of the 7-day run are identical to the 24 h forecast.
- The forecast is never below the essential load of that hour, and is capped at 6.9 kW.
- An 80 % interval of ±1.28 σ is shown, where σ is the std of the day-ahead test residuals.
- Single-row predictions run with one OpenMP thread (about 2× faster). All what-if combinations are pre-computed after training.

## Explanation engine
- Rule-based context drivers are decoupled from the ML output.
- For each hour, the dominant simulated components (cooking, HVAC, appliances…) plus occupancy and temperature give the reason.
- Horizon-level text compares the forecast with the last 4 weeks, covering HVAC need, occupancy, travel, dog location and planned appliance cycles.
- Day-to-day changes are explained by day type, temperature and dog status.
