"""Unit tests for the ENERPILOT engines (run offline, seed 42)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app import config as C
from app.services.household import occupancy_profile, plan_for_day
from app.services.optimizer import optimize_day
from app.services.simulator import burst, simulate
from app.services.weather import synthetic_weather


def _weather(days=14, start="2026-01-05"):
    idx = pd.date_range(start, periods=days * 24, freq="h")
    return synthetic_weather(idx)


# ---------------------------------------------------------------- tariff
@pytest.mark.parametrize("hour,rate", [(0, 0.18), (5, 0.18), (6, 0.28), (16, 0.28), (17, 0.40), (21, 0.40), (22, 0.28), (23, 0.28)])
def test_official_tariff(hour, rate):
    assert C.tariff_for_hour(hour) == rate


def test_official_pv_economics():
    assert C.PV_COST_PER_KWP == 1300 and C.EXPORT_TARIFF == 0.08 and C.PV_OPEX_PCT == 0.01
    assert (C.PV_TILT, C.PV_AZIMUTH, C.PV_SYSTEM_LOSS_PCT) == (35, 0, 14)
    assert C.PV_CAPACITIES == [2, 4, 6, 8, 10, 12]


def test_burst_formula():
    assert burst(2.0, 4) == pytest.approx(0.1333, abs=1e-3)   # kettle 2 kW x 4 min
    assert 0.08 <= burst(1.2, 7) <= 0.25                     # coffee machine


# ---------------------------------------------------------------- simulator
def test_simulation_is_deterministic():
    w = _weather()
    a, _ = simulate(w)
    b, _ = simulate(w)
    assert np.allclose(a["total"], b["total"])


def test_absence_never_zero_and_cap():
    w = _weather(days=30)
    sim, _ = simulate(w, occupancy_mode="weekend_travel", dog_mode="home")
    assert (sim["people_home"] == 0).all()
    assert sim["total"].min() > 0.08          # fridge, Wi-Fi, ventilation, standby, pet loads
    full, _ = simulate(w)
    assert full["total"].max() <= C.MAX_POWER_KW + 1e-9


def test_dog_away_scales_pet_loads_down():
    w = _weather()
    home, _ = simulate(w, dog_mode="home", noise=False)
    away, _ = simulate(w, dog_mode="away", noise=False)
    assert home["pet_camera"].sum() > 0 and away["pet_camera"].sum() == 0
    assert away["pet_feeder"].sum() == 0
    assert away["essential"].sum() < home["essential"].sum()


def test_indicative_ranges():
    w = _weather(days=30)
    sim, jobs = simulate(w, dog_mode="home", noise=False)
    fridge_day = sim["fridge"].resample("D").sum()
    assert fridge_day.between(0.8, 1.2).all()
    feeder_day = sim["pet_feeder"].resample("D").sum()
    assert feeder_day.between(0.005, 0.02).all()
    assert sim["ventilation"].between(0.01, 0.03).all()
    for j in jobs:
        if j["appliance"] == "dishwasher":
            assert 0.8 <= j["energy_kwh"] <= 1.2
        if j["appliance"] == "washing":
            assert 0.6 <= j["energy_kwh"] <= 1.0


def test_noise_sigma():
    w = _weather(days=60)
    sim, _ = simulate(w)
    unclipped = sim["noise"][(sim["total"] > sim["essential"] + 0.3) & (sim["total"] < C.MAX_POWER_KW)]
    assert abs(unclipped.std() - C.NOISE_SIGMA_KWH) < 0.01


def test_weather_drives_hvac():
    idx = pd.date_range("2026-01-05", periods=48, freq="h")
    cold = pd.DataFrame({"temperature": 5.0, "humidity": 80.0, "cloud_cover": 90.0, "radiation": 0.0}, index=idx)
    mild = cold.assign(temperature=20.0)
    c, _ = simulate(cold, noise=False, occupancy_mode="both_wfh")
    m, _ = simulate(mild, noise=False, occupancy_mode="both_wfh")
    assert c["hvac_comfort"].sum() + c["hvac_essential"].sum() > m["hvac_comfort"].sum() + m["hvac_essential"].sum()


# ---------------------------------------------------------------- context
def test_plans_reproducible_and_varied():
    days = [date(2026, 3, 1) + pd.Timedelta(days=i) for i in range(56)]
    plans = [plan_for_day(d) for d in days]
    assert plans[0] == plan_for_day(days[0])
    types = {p.day_type for p in plans}
    assert {"both_wfh", "one_wfh", "both_away", "weekend_home", "weekend_travel"} <= types
    assert any(not p.dog_home for p in plans)          # dog sometimes travels
    assert any(p.dishwasher_start is None for p in plans) and any(p.dishwasher_start for p in plans)


def test_occupancy_profile_hybrid():
    p = plan_for_day(date(2026, 3, 3), occupancy_mode="both_away")
    people, _ = occupancy_profile(p)
    assert people[12] == 0 and people[2] == 2 and people[21] == 2


# ---------------------------------------------------------------- optimiser
def _job(app="dishwasher", start=20, kwh=1.0, dur=2, noisy=True):
    return {"appliance": app, "label": app, "start": start, "duration_h": dur, "energy_kwh": kwh, "noisy": noisy}


def test_optimizer_moves_to_solar_window_contiguously():
    base = np.full(24, 0.2)
    pv = np.zeros(24)
    pv[9:17] = 1.5
    res = optimize_day(base, pv, [_job()])
    p = res["placements"][0]
    assert p["strategy"] == "solar_window"
    assert 10 <= p["recommended_start"] and p["recommended_start"] + 2 <= 16
    added = res["optimized_load"] - base
    nz = np.nonzero(added > 1e-9)[0]
    assert list(nz) == list(range(nz[0], nz[0] + 2))      # contiguous block
    assert added.sum() == pytest.approx(1.0)
    assert res["cost_after"] < res["cost_before"]


def test_optimizer_bad_weather_fallback_offpeak():
    base = np.full(24, 0.2)
    pv = np.zeros(24)
    pv[11:14] = 0.05                                        # < 0.1 kWh everywhere
    res = optimize_day(base, pv, [_job()], enforce_rest_window=False)
    p = res["placements"][0]
    assert res["bad_weather"] and p["strategy"] == "offpeak_fallback"
    assert p["recommended_start"] + 2 <= 6


def test_optimizer_respects_rest_window():
    base = np.full(24, 0.2)
    res = optimize_day(base, np.zeros(24), [_job()], enforce_rest_window=True)
    p = res["placements"][0]
    hours = range(p["recommended_start"], p["recommended_start"] + 2)
    assert not any(h >= 22 or h < 7 for h in hours)
    assert all(C.tariff_for_hour(h) < 0.40 for h in hours)


def test_optimizer_never_exceeds_limit():
    base = np.full(24, 0.2)
    base[10:16] = 6.5
    pv = np.zeros(24)
    pv[10:16] = 0.5
    res = optimize_day(base, pv, [_job(start=20)])
    assert res["optimized_load"].max() <= C.MAX_POWER_KW + 1e-9
