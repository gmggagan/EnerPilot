# Requirements Traceability — HackoWatt 2026 Scenario 5

Source of truth: *HackoWatt 2026 – Scenario 5 "Home Alone – But Not Really"* and *Common Challenge
Assumptions*. Each requirement is mapped to the component that implements it and where it is visible.
The **Compliance** tab shows this checklist with live evidence.

## Required outcome (Scenario 5 §08)

| # | Requirement | Implementation | Visible in |
|---|---|---|---|
| 1 | Historical hourly consumption profile, ≥ 30 consecutive days | `simulator.simulate()` over 365 days of real Open-Meteo archive weather; routines from `household.plan_for_day()` | Compliance → Historical profile (30/90/365 D); `GET /api/v1/historical` |
| 2 | Energy consumption forecasting model | `forecaster.Forecaster` (HistGradientBoostingRegressor) | Compliance → Model validation; `GET /api/v1/model/metrics` |
| 3 | Hourly forecast for the next 24 h | Recursive forecast from the current hour | Metrics tab, 24H; `/forecast/24h` |
| 4 | Forecasts for the next 3 and 7 days | Same model, 72 / 168 steps | Header 3D / 7D; `/forecast/3d`, `/forecast/7d` |
| 5 | Application presenting the results | React dashboard served by FastAPI | whole UI |
| 6 | Hours with the highest expected demand | `insights.peaks()` — top-3 hours, peak periods, daily peaks | Metrics → Highest-Demand Hours, chart markers; `/peaks` |
| 7 | Brief explanation of changes in consumption | `insights.explanations()` — vs recent average, peak, lowest, absence, day-to-day | Metrics → Why Demand Changes; `/explanations` |
| 8 | Simulator of renewable investment impact | `pv_economics.simulate_capacity()` | PV Sizing tab; `/pv/simulate` |

## Historical profile (§04.1)

| Requirement | Implementation |
|---|---|
| Daily routines (6:30–9, 9–17, 17–23, 23–6:30) | `household.occupancy_profile()`; kettle/coffee at wake-up, WFH laptops, lunch, dinner, TV/gaming |
| Appliance & system operation | 15 components (`simulator.COMPONENTS`), values inside the §03 ranges (unit-tested) |
| Impact of outdoor temperature | Duty-cycled heat pump / AC driven by hourly temperature |
| Differences between days | Seeded per-day plans: WFH mix, meal times, oven use, appliance days, gaming, outings |
| Residents at home and away | Hourly `people_home`; office days; weekend travel |
| Essential pet consumption | Pet camera, feeder, pet-safety HVAC (10–28 °C band); never zero during absence (tested) |
| Behavioural variability (§07) | Hybrid work, weekend travel (45 %), dog travels on 35 % of trips, washing/dishwasher on selected days, weekday vs weekend entertainment |

## Forecast (§04.2)

| Requirement | Implementation |
|---|---|
| Account for predicted weather | Open-Meteo forecast temperature, humidity, cloud cover, radiation as features |
| Account for expected presence/absence | Context features from the day plan; what-if overrides in the sidebar |

## Application display (§04.3)

| Must display | Where |
|---|---|
| Forecast hourly consumption | Metrics → Hourly Energy Demand Forecast (80 % interval) |
| Forecast total for selected period | Metrics → Total Forecast card; Compliance → Q1 |
| Outdoor temperature forecast | Forecast chart (right axis) + Outdoor Weather Forecast card |
| Highest-demand hours | Highest-Demand Hours panel + chart markers |
| Explanation of increase/decrease | Why Demand Changes panel |

## Renewable Energy Simulator (§05)

| Requirement | Implementation |
|---|---|
| Select capacity (kWp) | 2/4/6/8/10/12 kWp (sidebar, slider, buttons, table rows) |
| Shared rooftop / community PV | Assumed, as permitted by Scenario 5 |
| 01 Annual production | PVGIS hourly series × kWp |
| 02 Self-generated share of demand | `self_sufficiency_pct` |
| 03 Reduction in grid purchase | `grid_reduction_kwh` / `grid_reduction_pct` |
| 04 Savings | Gross / net annual savings, export revenue, OPEX |
| 05 Payback A (no habit change) & B (with shifting) | `scenario_a.payback_years`, `scenario_b.payback_years` |
| Compare several capacities | Capacity Comparison chart + table |

## Final objective (§09)

| Question | Answered by |
|---|---|
| Q1 Demand over 24 h / 3 d / 7 d | Metrics total + Compliance Q1 |
| Q2 Hours of highest demand | Peaks panel + Compliance Q2 |
| Q3 Habit changes | Dispatch schedule + recommendations + Compliance Q3 |
| Q4 PV effect on grid purchases, costs, payback | PV Sizing + Compliance Q4 |

## Common Challenge Assumptions

| Requirement | Implementation |
|---|---|
| ≥ 30 days hourly history | 365 days (configurable, min 30) |
| Real historical + forecast weather for the location | Open-Meteo archive + forecast APIs, Lisbon 38.7223 N, 9.1393 W |
| At minimum outdoor temperature | temperature_2m (+ humidity, cloud cover, shortwave radiation) |
| Tariff 0.18 / 0.28 / 0.40 / 0.28 | `config.TARIFF_BANDS` (unit-tested) |
| PV €1,300/kWp, export €0.08/kWh, OPEX 1 % | `config.py` (unit-tested) |
| PV production reflects the location | JRC PVGIS v5.3 hourly series, Lisbon, 35°, south, 14 % loss |
| Document additional assumptions | [ASSUMPTIONS.md](ASSUMPTIONS.md) + Compliance → Assumptions Register |

## Project brief extras

| Brief item | Implementation |
|---|---|
| Seed 42, noise N(0, 0.05²), 6.9 kW cap | `simulator.py` (tests: determinism, σ, cap) |
| Duty-cycle formula kWh = kW × min/60 | `simulator.burst()` (tested) |
| Chronological split, naive baselines, MAE/RMSE | `forecaster.fit()` |
| Lags 1/2/24/168 + 24 h rolling mean | `forecaster.add_lags()` |
| Never shift essential; contiguous cycles; solar 10–16; zero-PV fallback 00–06; rest window 22–07 | `optimizer.optimize_day()` (a test per rule) |
| All listed endpoints | `backend/main.py` (API test per endpoint) |
