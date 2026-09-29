"""Load optimisation engine.

Rules (spec section 13):
 1. Essential loads are never shifted - only dishwasher, washing machine and
    device charging are moved.
 2. Appliance cycles are scheduled as contiguous, non-interruptible blocks.
 3. Primary goal: solar self-consumption window 10:00-16:00.
    Zero-PV / bad-weather fallback: when no hour of the solar window is
    forecast to produce >= 0.1 kWh, flexible loads go to the cheapest
    off-peak window 00:00-06:00 (EUR 0.18).
 4. Rest window: noisy appliances (dishwasher, washing machine) are never
    placed between 22:00 and 07:00 unless the user disables the constraint.
    When the rest window blocks the night fallback, the cheapest allowed
    daytime slot is used (07:00-17:00 at EUR 0.28, never the 0.40 peak).
 5. The 6.9 kW connection limit is respected in every hour.
A move is only recommended when it lowers the household's energy cost.
"""
from __future__ import annotations

import numpy as np

from .. import config as C

TARIFF = C.tariff_for_hour(np.arange(24)).astype(float)


def _in_rest(h: int) -> bool:
    start, end = C.REST_WINDOW
    return h >= start or h < end


def _cost(load: np.ndarray, pv: np.ndarray) -> float:
    net = load - pv
    return float(np.sum(np.maximum(net, 0) * TARIFF) - np.sum(np.maximum(-net, 0)) * C.EXPORT_TARIFF)


def _fmt(h: int) -> str:
    return f"{h % 24:02d}:00"


def optimize_day(base: np.ndarray, pv: np.ndarray, jobs: list[dict], available: np.ndarray | None = None,
                 enforce_rest_window: bool = True) -> dict:
    """Place flexible jobs for one day.

    base: 24 h load without the flexible jobs (kWh); pv: 24 h PV (kWh);
    available: bool[24] hours inside the planning horizon.
    """
    base = np.asarray(base, dtype=float).copy()
    pv = np.nan_to_num(np.asarray(pv, dtype=float))
    available = np.ones(24, dtype=bool) if available is None else np.asarray(available, dtype=bool)
    lo, hi = C.SOLAR_WINDOW
    solar_hours = [h for h in range(lo, hi) if available[h]]
    # bad weather is only judged when the solar window lies inside the horizon
    bad_weather = bool(solar_hours) and float(np.max(pv[solar_hours])) < C.BAD_WEATHER_PV_KWH
    use_fallback = bad_weather or not solar_hours

    load = base.copy()
    for j in jobs:  # unmanaged schedule, used for 'before' figures
        load[j["start"]:j["start"] + j["duration_h"]] += j["energy_kwh"] / j["duration_h"]
    cost_before = _cost(np.where(available, load, 0), np.where(available, pv, 0))

    load = base.copy()
    placements = []
    for j in sorted(jobs, key=lambda x: -x["energy_kwh"]):
        dur, per_h = j["duration_h"], j["energy_kwh"] / j["duration_h"]
        noisy = j.get("noisy", False) and enforce_rest_window

        def allowed(s: int) -> bool:
            hrs = range(s, s + dur)
            if s < 0 or s + dur > 24 or not all(available[h] for h in hrs):
                return False
            if noisy and any(_in_rest(h) for h in hrs):
                return False
            return all(load[h] + per_h <= C.MAX_POWER_KW for h in hrs)

        def incr(s: int) -> float:
            trial = load.copy()
            trial[s:s + dur] += per_h
            return _cost(trial, pv) - _cost(load, pv)

        starts = [s for s in range(0, 25 - dur) if allowed(s)]
        if use_fallback:
            off_lo, off_hi = C.OFFPEAK_WINDOW
            cands = [s for s in starts if s >= off_lo and s + dur <= off_hi]
            strategy = "offpeak_fallback"
            if not cands:
                cands = [s for s in starts if all(C.tariff_for_hour(h) < 0.40 for h in range(s, s + dur))]
                strategy = "cheapest_allowed"
        else:
            cands = [s for s in starts if s >= lo and s + dur <= hi]
            strategy = "solar_window"
        orig = j["start"]
        orig_cost = incr(orig)
        best = min(cands, key=lambda s: (round(incr(s), 6), abs(s - orig))) if cands else None
        if best is None or incr(best) >= orig_cost - 1e-6 or best == orig:
            new, strategy_used = orig, "keep"
        else:
            new, strategy_used = best, strategy
        new_cost = incr(new)
        load[new:new + dur] += per_h

        if strategy_used == "solar_window":
            reason = (f"Run during the 10:00-16:00 solar window to use PV "
                      f"({float(np.sum(pv[new:new + dur])):.2f} kWh forecast) instead of buying at "
                      f"{C.tariff_label(orig)} EUR {C.tariff_for_hour(orig):.2f}/kWh"
                      + (" (use the appliance's delay-start timer if nobody is home)." if j.get("noisy") else "."))
        elif strategy_used == "offpeak_fallback":
            why = ("PV forecast below 0.1 kWh in the solar window (heavy cloud/rain)" if bad_weather
                   else "Solar window outside the forecast horizon")
            reason = f"{why}: moved to the cheapest night off-peak window 00:00-06:00 at EUR 0.18/kWh."
        elif strategy_used == "cheapest_allowed":
            why = ("PV forecast below 0.1 kWh in the solar window" if bad_weather
                   else "Solar window outside the forecast horizon")
            if noisy:
                block = "the 22:00-07:00 rest window blocks night operation"
            else:
                block = "the 00:00-06:00 off-peak window is not available in the horizon"
            reason = (f"{why} and {block}: moved to the cheapest allowed slot "
                      f"(EUR {C.tariff_for_hour(new):.2f}/kWh), avoiding the EUR 0.40 evening peak.")
        else:
            reason = "Already at the lowest-cost feasible time - no change recommended."
        placements.append({
            **{k: j[k] for k in ("appliance", "label", "duration_h", "energy_kwh", "noisy") if k in j},
            "date": j.get("date"), "original_start": orig, "recommended_start": new,
            "original_window": f"{_fmt(orig)}-{_fmt(orig + dur)}",
            "recommended_window": f"{_fmt(new)}-{_fmt(new + dur)}",
            "shifted": new != orig, "strategy": strategy_used, "reason": reason,
            "cost_before_eur": round(orig_cost, 4), "cost_after_eur": round(new_cost, 4),
            "saving_eur": round(orig_cost - new_cost, 4),
        })

    cost_after = _cost(np.where(available, load, 0), np.where(available, pv, 0))
    return {"optimized_load": load, "placements": placements, "bad_weather": bad_weather,
            "cost_before": cost_before, "cost_after": cost_after}


def optimize_series(base: np.ndarray, pv: np.ndarray, hours: np.ndarray, day_index: np.ndarray,
                    jobs_by_day: dict, enforce_rest_window: bool = True) -> tuple[np.ndarray, list[dict], dict]:
    """Optimise a multi-day hourly series.

    base/pv: hourly arrays (flexible jobs removed from base)
    hours: hour-of-day per row; day_index: day key per row
    jobs_by_day: {day_key: [job, ...]}
    """
    out = np.asarray(base, dtype=float).copy()
    all_placements, day_flags = [], {}
    for key in dict.fromkeys(day_index):  # preserves order
        rows = np.where(day_index == key)[0]
        b = np.zeros(24)
        p = np.zeros(24)
        avail = np.zeros(24, dtype=bool)
        b[hours[rows]] = base[rows]
        p[hours[rows]] = pv[rows]
        avail[hours[rows]] = True
        res = optimize_day(b, p, jobs_by_day.get(key, []), avail, enforce_rest_window)
        out[rows] = res["optimized_load"][hours[rows]]
        all_placements.extend(res["placements"])
        day_flags[str(key)] = bool(res["bad_weather"])
    return out, all_placements, day_flags
