"""Appliance-level household load simulator (Scenario 5 indicative parameters).

Produces hourly energy (kWh) per appliance/system, classified as
  * essential  - never shifted (fridge, Wi-Fi, ventilation, standby, pet
                 devices, pet-safety HVAC)
  * flexible   - shiftable (dishwasher, washing machine, device charging)
  * comfort    - occupant-driven, not shifted (cooking, kettle/coffee,
                 lighting, TV, gaming, computers, comfort HVAC)

Short bursts use: Hourly Energy (kWh) = Power (kW) x minutes / 60.
Noise: N(0, 0.05^2) kWh per hour, seed 42. Hourly draw capped at 6.9 kW.
"""
from __future__ import annotations

import random
from datetime import date

import numpy as np
import pandas as pd

from .. import config as C
from .household import DayPlan, occupancy_profile, plan_for_day

random.seed(C.SEED)
np.random.seed(C.SEED)

# Indicative parameters (value chosen inside the official range)
P = {
    "fridge_kwh_day": 1.0,        # 0.8-1.2 kWh/day
    "wifi_kw": 0.012,             # 0.008-0.015 kW
    "ventilation_kw": 0.020,      # 0.01-0.03 kW
    "standby_kw": 0.040,          # 0.02-0.06 kW
    "pet_camera_kw": 0.010,       # 0.005-0.015 kW
    "pet_feeder_idle_kw": 0.0003,  # -> ~0.015 kWh/day incl. 2 feeds (0.005-0.02)
    "pet_feeder_feed_kwh": 0.004,
    "kettle_kw": 2.0, "kettle_min": 4,          # 2.0 kW, 3-5 min
    "coffee_kw": 1.2, "coffee_min": 7,          # 1.0-1.5 kW, 5-10 min
    "induction_kw": 2.2, "dinner_min": 40,      # 1.5-3.5 kW
    "lunch_kw": 1.8, "lunch_min": 20,
    "oven_kw": 2.2, "oven_min": 45,             # 2.0-2.5 kW
    "lighting_kw": 0.10,          # 0.05-0.15 kW total
    "tv_kw": 0.12,                # 0.08-0.15 kW
    "gaming_kw": 0.15,            # 0.10-0.20 kW
    "laptop_kw": 0.12,            # 0.05-0.25 kW per person working
    "charging_kwh": 0.012, "devices": 4,        # 0.005-0.02 kWh per charge
    "dishwasher_kwh": 1.0, "dishwasher_h": 2,   # 0.8-1.2 kWh/cycle
    "washing_kwh": 0.8, "washing_h": 2,         # 0.6-1.0 kWh/cycle
    "heat_rated_kw": 1.5,         # heat pump 1.0-2.5 kW during operation (duty-cycled)
    "cool_rated_kw": 1.2,         # AC 0.8-2.0 kW during operation (duty-cycled)
}

COMPONENTS = ["fridge", "wifi", "ventilation", "standby", "pet_camera", "pet_feeder", "hvac_essential",
              "hvac_comfort", "kitchen", "lighting", "computing", "entertainment",
              "charging", "dishwasher", "washing"]
ESSENTIAL = ["fridge", "wifi", "ventilation", "standby", "pet_camera", "pet_feeder", "hvac_essential"]
FLEXIBLE = ["charging", "dishwasher", "washing"]
COMFORT = ["hvac_comfort", "kitchen", "lighting", "computing", "entertainment"]

LABELS = {
    "fridge": "Refrigerator", "wifi": "Wi-Fi router", "ventilation": "Continuous ventilation",
    "standby": "Standby devices", "pet_camera": "Pet camera", "pet_feeder": "Automatic pet feeder",
    "hvac_essential": "Pet-safety heating/AC", "hvac_comfort": "Comfort heating/AC",
    "kitchen": "Cooking, kettle & coffee", "lighting": "Lighting", "computing": "Laptops / computers",
    "entertainment": "TV & gaming", "charging": "Device charging", "dishwasher": "Dishwasher",
    "washing": "Washing machine",
}


# Shiftable appliances a user can plan manually (same indicative values as the routine)
APPLIANCES = {
    "dishwasher": {"label": LABELS["dishwasher"], "energy_kwh": P["dishwasher_kwh"], "duration_h": P["dishwasher_h"], "noisy": True},
    "washing": {"label": LABELS["washing"], "energy_kwh": P["washing_kwh"], "duration_h": P["washing_h"], "noisy": True},
    "charging": {"label": LABELS["charging"], "energy_kwh": round(P["charging_kwh"] * P["devices"], 3), "duration_h": 1, "noisy": False},
}


def burst(kw: float, minutes: float) -> float:
    """Deterministic short-burst duty cycle: kWh = kW x min / 60."""
    return kw * minutes / 60.0


def hvac_kw(temp: float, mode: str) -> float:
    """Average electrical HVAC energy for one hour (kWh) = rated kW x duty cycle.

    mode: comfort (residents awake), night (residents asleep, setback),
          pet (only the dog is home), off (empty apartment, protection only)
    """
    # (outdoor temp below which heating runs, above which cooling runs,
    #  duty-cycle gain per degC for heating / cooling)
    heat_on, cool_on, k_heat, k_cool = {
        "comfort": (15.0, 26.0, 0.08, 0.12),
        "night": (11.0, 27.0, 0.05, 0.08),
        "pet": (10.0, 28.0, 0.06, 0.10),   # dog-safe band, wider than human comfort
        "off": (3.0, 36.0, 0.05, 0.05),    # frost / overheat protection only
    }[mode]
    if temp < heat_on:
        return P["heat_rated_kw"] * min(1.0, 0.10 + k_heat * (heat_on - temp))
    if temp > cool_on:
        return P["cool_rated_kw"] * min(1.0, 0.10 + k_cool * (temp - cool_on))
    return 0.0


def simulate_day(plan: DayPlan, weather_day: pd.DataFrame) -> tuple[np.ndarray, dict, list[dict]]:
    """Return (component matrix [24 x len(COMPONENTS)], context arrays, flexible jobs)."""
    temps = weather_day["temperature"].values
    rad = weather_day["radiation"].values
    people, awake = occupancy_profile(plan)
    comp = {k: np.zeros(24) for k in COMPONENTS}
    meal = np.zeros(24)

    comp["fridge"][:] = np.clip(P["fridge_kwh_day"] / 24 * (1 + 0.02 * (temps - 20)), 0.033, 0.05)
    comp["wifi"][:] = P["wifi_kw"]
    comp["ventilation"][:] = P["ventilation_kw"]
    comp["standby"][:] = P["standby_kw"]
    if plan.dog_home:  # pet loads disabled when the dog travels with the residents
        comp["pet_camera"][:] = P["pet_camera_kw"]
        comp["pet_feeder"][:] = P["pet_feeder_idle_kw"]
        comp["pet_feeder"][[7, 18]] += P["pet_feeder_feed_kwh"]

    for h in range(24):
        t = temps[h]
        home = people[h] > 0
        if home and awake[h]:
            total = hvac_kw(t, "comfort")
        elif home:
            total = hvac_kw(t, "night")
        elif plan.dog_home:
            total = hvac_kw(t, "pet")
        else:
            total = hvac_kw(t, "off")
        essential = min(total, hvac_kw(t, "pet")) if plan.dog_home else min(total, hvac_kw(t, "off"))
        comp["hvac_essential"][h] = essential
        comp["hvac_comfort"][h] = total - essential

        if awake[h]:
            dark = rad[h] < 80
            if dark:
                comp["lighting"][h] = P["lighting_kw"] * (0.6 if people[h] == 1 else 1.0)
            if h >= 20 and h <= 22:
                comp["entertainment"][h] += P["tv_kw"]
                comp["computing"][h] += 0.5 * P["laptop_kw"]
        if h in plan.gaming_hours and awake[h]:
            comp["entertainment"][h] += P["gaming_kw"]

    # morning routine: kettle + coffee for each person (6:30-9:00)
    if not plan.travel:
        wh = plan.wake_hour
        comp["kitchen"][wh] += burst(P["kettle_kw"], P["kettle_min"]) + 2 * burst(P["coffee_kw"], P["coffee_min"])
        comp["computing"][wh] += 0.05  # checking feeder/camera app, phones
        meal[wh] = 1
        # daytime: work from home computers + lunch + afternoon coffee
        for h in range(9, 17):
            if awake[h] and people[h] > 0 and plan.wfh_count:
                comp["computing"][h] += P["laptop_kw"] * min(people[h], plan.wfh_count)
        if people[13] > 0:
            comp["kitchen"][13] += burst(P["lunch_kw"], P["lunch_min"])
            meal[13] = 1
        if plan.wfh_count and people[15] > 0:
            comp["kitchen"][15] += plan.wfh_count * burst(P["coffee_kw"], P["coffee_min"])
        # dinner (variable meal time)
        dh = plan.dinner_hour
        comp["kitchen"][dh] += burst(P["induction_kw"], P["dinner_min"])
        if plan.oven:
            comp["kitchen"][dh] += burst(P["oven_kw"], P["oven_min"])
        meal[dh] = 1

    jobs: list[dict] = []

    def add_job(key: str, start: int | None, kwh: float, dur: int):
        if start is None:
            return
        start = max(0, min(start, 24 - dur))
        comp[key][start:start + dur] += kwh / dur
        jobs.append({"appliance": key, "label": LABELS[key], "start": start, "duration_h": dur,
                     "energy_kwh": kwh, "noisy": key in ("dishwasher", "washing")})

    add_job("dishwasher", plan.dishwasher_start, P["dishwasher_kwh"], P["dishwasher_h"])
    add_job("washing", plan.washing_start, P["washing_kwh"], P["washing_h"])
    if not plan.travel:
        add_job("charging", 22, P["charging_kwh"] * P["devices"], 1)

    matrix = np.column_stack([comp[k] for k in COMPONENTS])
    ctx = {"people": people, "awake": awake.astype(int), "meal": meal}
    return matrix, ctx, jobs


def simulate(weather: pd.DataFrame, plans: dict[date, DayPlan] | None = None, noise: bool = True,
             occupancy_mode: str = "auto", dog_mode: str = "auto") -> tuple[pd.DataFrame, list[dict]]:
    """Simulate hourly load for every hour in `weather` (index = local hours).

    Returns (frame, jobs). Frame columns: context, all COMPONENTS, essential,
    flexible, comfort, noise, total (kWh).
    """
    weather = weather.sort_index()
    days = sorted(set(weather.index.date))
    rng = np.random.default_rng(C.SEED)
    rows, all_jobs = [], []
    for d in days:
        wd = weather.loc[weather.index.date == d]
        full = wd.reindex(pd.date_range(pd.Timestamp(d), periods=24, freq="h")).ffill().bfill()
        plan = plans[d] if plans and d in plans else plan_for_day(d, occupancy_mode, dog_mode)
        matrix, ctx, jobs = simulate_day(plan, full)
        frame = pd.DataFrame(matrix, index=full.index, columns=COMPONENTS)
        frame["people_home"] = ctx["people"]
        frame["awake"] = ctx["awake"]
        frame["meal_period"] = ctx["meal"]
        frame["day_type"] = plan.day_type
        frame["dog_home"] = int(plan.dog_home)
        frame["travel"] = int(plan.travel)
        frame["wfh_count"] = plan.wfh_count
        rows.append(frame.loc[frame.index.isin(wd.index)])
        for j in jobs:
            j["date"] = d.isoformat()
            hours = pd.date_range(pd.Timestamp(d) + pd.Timedelta(hours=j["start"]), periods=j["duration_h"], freq="h")
            if hours.isin(wd.index).all():
                all_jobs.append(j)
    df = pd.concat(rows)

    df["essential"] = df[ESSENTIAL].sum(axis=1)
    df["flexible"] = df[FLEXIBLE].sum(axis=1)
    df["comfort"] = df[COMFORT].sum(axis=1)
    gross = df["essential"] + df["flexible"] + df["comfort"]
    # co-occurrence constraint: never exceed the 6.9 kW connection
    over = gross > C.MAX_POWER_KW
    if over.any():
        scale = (C.MAX_POWER_KW - df.loc[over, "essential"] - df.loc[over, "flexible"]) / df.loc[over, "comfort"]
        for k in COMFORT:
            df.loc[over, k] *= scale
        df["comfort"] = df[COMFORT].sum(axis=1)
        gross = df["essential"] + df["flexible"] + df["comfort"]
    df["noise"] = rng.normal(0, C.NOISE_SIGMA_KWH, len(df)) if noise else 0.0
    # absence never drops consumption to zero: floor at the essential load
    df["total"] = np.clip(gross + df["noise"], df["essential"], C.MAX_POWER_KW)
    df["noise"] = df["total"] - gross
    return df, all_jobs
