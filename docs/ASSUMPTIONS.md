# Assumptions

Priority rule: **official HackoWatt requirements > project assumptions > generic industry assumptions.**

## A. Official challenge parameters (not changed)

| Item | Value |
|---|---|
| Location | Lisbon, Portugal (38.7223 N, 9.1393 W) |
| History | ≥ 30 consecutive days, hourly (we use 365) |
| Weather | Real historical + forecast (Open-Meteo), at minimum outdoor temperature |
| Tariff | 00–06 €0.18 · 06–17 €0.28 · 17–22 €0.40 · 22–24 €0.28 per kWh |
| PV cost | €1,300 per kWp |
| Export | €0.08 per kWh |
| PV OPEX | 1 % of initial investment per year |
| Appliance ranges | Scenario 5 §03 table — every simulator value lies inside its range |

## B. Model assumptions (ours, documented)

### Household & behaviour
- Two adults (Ola, Tomek) and one dog in a city apartment.
- Weekday mix: 25 % both WFH, 40 % one WFH, 35 % both at the office. Wake-up 06:00–07:00 on weekdays, 07:00–09:00 on weekends.
- 45 % of weekends are trips (Saturday + Sunday, apartment empty). The dog joins 35 % of trips; otherwise it stays home with a carer and pet systems keep running.
- Dinner at 18–21 h (variable). Oven on 40 % of days. Dishwasher on 55 % of days (after dinner). Washing machine on 30 % of weekdays (evening) and 60 % of home weekends (morning).
- Gaming on 30 % of weekday evenings and 70 % of home weekends. Weekend outings from 11:00 to 16:00 on half of the home weekends.
- Every day plan is deterministic (seed 42 + date), so history and forecast context are reproducible.

### Appliances (chosen inside the official ranges)
| Appliance | Value |
|---|---|
| Fridge | 1.0 kWh/day (±2 %/°C around 20 °C) |
| Wi-Fi / ventilation / standby | 0.012 / 0.020 / 0.040 kW continuous |
| Pet camera | 0.010 kW when the dog is home, off otherwise |
| Pet feeder | ≈0.015 kWh/day (idle + two feeds), off when the dog travels |
| Kettle / coffee | 2.0 kW × 4 min, 1.2 kW × 7 min (duty-cycle formula) |
| Dinner | Induction 2.2 kW × 40 min, + oven 2.2 kW × 45 min on oven days |
| Lighting / TV / gaming / laptop | 0.10 / 0.12 / 0.15 / 0.12 kW |
| Dishwasher / washing machine | 1.0 / 0.8 kWh per cycle, as 2-hour contiguous blocks |
| Device charging | 4 devices × 0.012 kWh (flexible) |
| Heat pump / AC | Rated 1.5 kW / 1.2 kW, duty-cycled by outdoor temperature |

### HVAC bands (outdoor temperature thresholds)
- Residents awake: heat below 15 °C, cool above 26 °C.
- Residents asleep: heat below 11 °C, cool above 27 °C.
- Dog alone (pet-safety, **essential**): heat below 10 °C, cool above 28 °C.
- Empty apartment: frost/overheat protection only (below 3 °C, above 36 °C).
- The share of HVAC equal to the pet-safety level is classed as essential; the rest is comfort.

### Load classes
- **Essential (never shifted):** fridge, Wi-Fi, ventilation, standby, pet camera, pet feeder, pet-safety HVAC.
- **Flexible (shiftable):** dishwasher, washing machine, device charging.
- **Comfort / activity (not shifted, residents' comfort):** cooking, kettle/coffee, lighting, TV/gaming, computers, comfort HVAC.

### Data & noise
- Noise N(0, 0.05²) kWh per hour, seed 42. Hourly total floored at the essential load (absence never reaches zero) and capped at 6.9 kW (single-phase limit in Portugal).
- The history is synthetic by necessity (no smart meter data) but driven by **real** Lisbon weather.

### Optimiser
- Shifts are intra-day. A cycle moved earlier represents a routine change (e.g. load the dishwasher in the evening, start it the next day at midday using its delay-start timer).
- "Bad weather" = no hour of the 10:00–16:00 solar window is forecast to produce ≥ 0.1 kWh.
- If the rest window blocks the 00:00–06:00 fallback, the cheapest allowed slot outside the €0.40 peak is used.
- A move is recommended only if it lowers cost.

### PV
- PVGIS v5.3 (SARAH3) hourly series for 2023, 35° tilt, south, 14 % loss → about 1,610 kWh/kWp/yr for Lisbon.
- Annual PV production is aligned by month/day/hour with the simulated 365-day demand.
- Forecast-horizon PV = GHI × 1.10 (tilt gain) × 0.86 (losses) × kWp.
- Shared-rooftop / community PV assumed, as permitted by Scenario 5. No battery, no degradation, no discounting (the 25-year benefit is simple, not NPV).
- Scenario B savings include the tariff benefit of shifting. Both scenarios are compared with the same baseline: no PV and current habits.

### What-if weather presets
- Presets replace the forecast weather for scenario exploration: Sunny Summer (29 °C, clear, July sun), Mild Spring, and Cloudy/Rainy Winter (10 °C, 100 % cloud, 2 % of clear-sky irradiance → zero-PV fallback).
- "Live" always uses the real Open-Meteo forecast.
