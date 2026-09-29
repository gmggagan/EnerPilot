"""Peak intelligence + explanation engine.

The ML model supplies *how much*; the rule-based context drivers
(occupancy, meals, weather-driven HVAC, pet loads, appliances) supply *why*.
All outputs are deterministic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C
from .household import DAY_TYPES
from .simulator import COMPONENTS, LABELS

_DRIVER_TEXT = {
    "kitchen": "cooking / kettle & coffee",
    "hvac_comfort": "heating/AC for the residents' comfort",
    "hvac_essential": "heating/AC kept on for the dog",
    "dishwasher": "the dishwasher cycle",
    "washing": "the washing machine cycle",
    "entertainment": "TV and gaming",
    "computing": "laptops for work from home",
    "lighting": "lighting",
    "charging": "device charging",
}


def _drivers(row: pd.Series, top: int = 3) -> list[dict]:
    vals = [(k, float(row[k])) for k in _DRIVER_TEXT if row.get(k, 0) > 0.04]
    vals.sort(key=lambda kv: -kv[1])
    return [{"component": k, "label": LABELS[k], "kwh": round(v, 3)} for k, v in vals[:top]]


def _hour_reason(row: pd.Series) -> str:
    parts = [_DRIVER_TEXT[d["component"]] for d in _drivers(row)]
    people = int(row["people_home"])
    who = {0: "nobody home", 1: "one resident home", 2: "both residents home"}[min(people, 2)]
    if row["travel"]:
        who = "residents travelling"
    t = f"{row['temperature']:.0f}°C outside"
    if not parts:
        base = "only essential loads (fridge, Wi-Fi, ventilation, standby"
        base += ", pet camera & feeder)" if row["dog_home"] else ")"
        return f"{base} - {who}, {t}."
    return f"{', '.join(parts).capitalize()} - {who}, {t}."


def peaks(fc: pd.DataFrame, col: str = "predicted") -> dict:
    s = fc[col]
    top = s.nlargest(3)
    top3 = []
    for rank, (ts, v) in enumerate(top.items(), 1):
        row = fc.loc[ts]
        top3.append({"rank": rank, "time": ts.strftime("%Y-%m-%d %H:%M"), "hour": ts.hour,
                     "day": ts.strftime("%a %d %b"), "kwh": round(float(v), 3),
                     "tariff": float(C.tariff_for_hour(ts.hour)), "tariff_label": C.tariff_label(ts.hour),
                     "drivers": _drivers(row), "explanation": _hour_reason(row)})

    threshold = float(max(s.quantile(0.85), s.mean() + 0.5 * s.std()))
    periods, cur = [], None
    for ts, v in s.items():
        if v >= threshold:
            if cur and ts - cur["end_ts"] == pd.Timedelta(hours=1):
                cur["end_ts"] = ts
                cur["values"].append(v)
            else:
                cur = {"start_ts": ts, "end_ts": ts, "values": [v]}
                periods.append(cur)
    peak_periods = [{
        "start": p["start_ts"].strftime("%Y-%m-%d %H:%M"),
        "end": (p["end_ts"] + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),
        "label": f"{p['start_ts']:%a} {p['start_ts']:%H}:00-{(p['end_ts'] + pd.Timedelta(hours=1)):%H}:00",
        "hours": len(p["values"]), "energy_kwh": round(float(sum(p["values"])), 3),
        "max_kwh": round(float(max(p["values"])), 3)} for p in periods]

    daily = []
    for d, g in fc.groupby(fc.index.date):
        ts = g[col].idxmax()
        daily.append({"date": d.isoformat(), "day": pd.Timestamp(d).strftime("%a %d %b"),
                      "peak_hour": f"{ts:%H}:00", "peak_kwh": round(float(g[col].max()), 3),
                      "total_kwh": round(float(g[col].sum()), 2), "hours": int(len(g))})

    by_hour = fc.groupby(fc.index.hour)[col].mean()
    return {"threshold_kwh": round(threshold, 3), "top3": top3, "peak_periods": peak_periods,
            "daily_peaks": daily, "peak_hours_of_day": [int(h) for h in by_hour.nlargest(3).index],
            "peak_in_evening_tariff_pct": round(float(np.mean([p["tariff"] >= 0.40 for p in top3]) * 100), 0)}


def explanations(fc: pd.DataFrame, hist: pd.DataFrame) -> dict:
    """Natural-language explanation of the forecast and of changes in demand."""
    total = float(fc["predicted"].sum())
    hours = len(fc)
    per_day = total / hours * 24
    recent = hist.iloc[-28 * 24:]
    hist_day = float(recent["total"].sum()) / len(recent) * 24
    delta = (per_day - hist_day) / hist_day * 100

    reasons = []
    t_fc, t_hist = float(fc["temperature"].mean()), float(recent["temperature"].mean())
    hvac_fc = float((fc["hvac_comfort"] + fc["hvac_essential"]).sum()) / hours * 24
    hvac_hist = float((recent["hvac_comfort"] + recent["hvac_essential"]).sum()) / len(recent) * 24
    if abs(hvac_fc - hvac_hist) > 0.3:
        ref_t = t_fc if hvac_fc > hvac_hist else t_hist  # the period that needs the HVAC decides the mode
        mode = "cooling" if ref_t > 20 else "heating"
        reasons.append(f"{'more' if hvac_fc > hvac_hist else 'less'} {mode} ({t_fc:.1f}°C average vs "
                       f"{t_hist:.1f}°C over the last 4 weeks, {hvac_fc:.1f} vs {hvac_hist:.1f} kWh/day of HVAC)")
    occ_fc, occ_hist = float(fc["people_home"].mean()), float(recent["people_home"].mean())
    if abs(occ_fc - occ_hist) > 0.1:
        reasons.append(f"{'higher' if occ_fc > occ_hist else 'lower'} expected occupancy "
                       f"({occ_fc:.1f} vs {occ_hist:.1f} residents at home on average)")
    travel_h = int(fc["travel"].sum())
    if travel_h:
        reasons.append(f"{travel_h} h of planned travel when the apartment runs on essential loads only")
    if not fc["dog_home"].all():
        reasons.append("the dog travels with the residents, so pet camera, feeder and pet-safety climate control are switched off")
    flex_fc = float(fc["flexible"].sum()) / hours * 24
    if flex_fc > 0.4:
        reasons.append(f"dishwasher/washing machine cycles planned ({flex_fc:.1f} kWh/day of flexible load)")

    direction = "higher than" if delta > 3 else "lower than" if delta < -3 else "in line with"
    summary = (f"Expected consumption is {total:.1f} kWh over the next {hours} h ({per_day:.1f} kWh/day), "
               f"{abs(delta):.0f}% {direction} the recent average of {hist_day:.1f} kWh/day"
               if direction != "in line with" else
               f"Expected consumption is {total:.1f} kWh over the next {hours} h ({per_day:.1f} kWh/day), "
               f"in line with the recent average of {hist_day:.1f} kWh/day")
    summary += (" because of " + "; ".join(reasons) + ".") if reasons else "."

    peak_ts = fc["predicted"].idxmax()
    peak_row = fc.loc[peak_ts]
    peak_text = (f"Demand peaks at {peak_ts:%H}:00 on {peak_ts:%A} ({peak_row['predicted']:.2f} kWh) due to "
                 f"{_hour_reason(peak_row)[0].lower()}{_hour_reason(peak_row)[1:]}")
    low_ts = fc["predicted"].idxmin()
    low_text = (f"The lowest demand is at {low_ts:%H}:00 on {low_ts:%A} ({fc.loc[low_ts, 'predicted']:.2f} kWh). "
                f"Even then consumption never drops to zero: essential loads draw "
                f"{fc.loc[low_ts, 'essential']:.2f} kWh/h to keep the apartment safe"
                f"{' and comfortable for the dog' if fc.loc[low_ts, 'dog_home'] else ''}.")

    essential_share = float(fc["essential"].sum()) / max(float((fc["essential"] + fc["flexible"] + fc["comfort"]).sum()), 1e-9) * 100
    absent = fc[fc["people_home"] == 0]
    absence_text = None
    if len(absent):
        absence_text = (f"During {len(absent)} h with nobody at home the apartment still uses "
                        f"{absent['predicted'].mean():.2f} kWh/h on average - fridge, Wi-Fi, ventilation, standby"
                        f"{', pet camera, feeder and pet-safety heating/AC' if absent['dog_home'].any() else ''}. "
                        f"This is essential consumption, not waste.")

    day_changes = []
    prev = None
    for d, g in fc.groupby(fc.index.date):
        kwh = float(g["predicted"].sum()) / len(g) * 24
        dt = str(g["day_type"].iloc[0])
        info = {"date": d.isoformat(), "day": pd.Timestamp(d).strftime("%a %d %b"), "kwh_per_day": round(kwh, 2),
                "kwh_in_horizon": round(float(g["predicted"].sum()), 2), "hours": int(len(g)),
                "day_type": dt, "day_type_label": DAY_TYPES.get(dt, dt), "dog_home": bool(g["dog_home"].iloc[0]),
                "temp_mean": round(float(g["temperature"].mean()), 1), "partial_day": len(g) < 24}
        if info["partial_day"] and prev is not None:
            info["change_pct"] = None
            info["explanation"] = (f"Only {len(g)} h ({g.index[0]:%H}:00-{g.index[-1] + pd.Timedelta(hours=1):%H}:00) of this day "
                                   f"fall inside the horizon: {info['kwh_in_horizon']:.1f} kWh, mostly "
                                   f"{'overnight essential load' if g.index[-1].hour < 8 else 'daytime activity'}.")
        elif prev is not None and prev["partial_day"]:
            info["change_pct"] = None
            info["explanation"] = f"{DAY_TYPES.get(dt, dt)}, {info['temp_mean']}°C average, {kwh:.1f} kWh expected."
        elif prev is not None:
            ch = (kwh - prev["kwh_per_day"]) / prev["kwh_per_day"] * 100
            why = []
            if dt != prev["day_type"]:
                why.append(f"{DAY_TYPES.get(dt, dt).lower()} (was: {DAY_TYPES.get(prev['day_type'], prev['day_type']).lower()})")
            if abs(info["temp_mean"] - prev["temp_mean"]) >= 1.5:
                why.append(f"outdoor temperature {'up' if info['temp_mean'] > prev['temp_mean'] else 'down'} "
                           f"{abs(info['temp_mean'] - prev['temp_mean']):.1f}°C")
            if info["dog_home"] != prev["dog_home"]:
                why.append("dog " + ("back home" if info["dog_home"] else "travelling - pet loads off"))
            info["change_pct"] = round(ch, 1)
            info["explanation"] = (f"{'Increase' if ch > 0 else 'Decrease'} of {abs(ch):.0f}% vs previous day"
                                   + (": " + "; ".join(why) if why else ": normal day-to-day variation in routines") + ".")
        else:
            info["change_pct"] = None
            info["explanation"] = (f"{DAY_TYPES.get(dt, dt)}, {info['temp_mean']}°C average"
                                   + (f" ({len(g)} h from {g.index[0]:%H}:00 in the horizon)." if info["partial_day"] else "."))
        day_changes.append(info)
        prev = info

    return {"summary": summary, "peak": peak_text, "lowest": low_text, "absence": absence_text,
            "essential_share_pct": round(essential_share, 1), "change_vs_recent_pct": round(delta, 1),
            "recent_avg_kwh_per_day": round(hist_day, 2), "day_changes": day_changes,
            "hourly": {ts.strftime("%Y-%m-%d %H:%M"): _hour_reason(r) for ts, r in fc.iterrows()}}


def component_totals(df: pd.DataFrame) -> list[dict]:
    from .simulator import ESSENTIAL, FLEXIBLE
    out = []
    for k in COMPONENTS:
        cat = "essential" if k in ESSENTIAL else "flexible" if k in FLEXIBLE else "comfort"
        out.append({"component": k, "label": LABELS[k], "category": cat, "kwh": round(float(df[k].sum()), 3)})
    return sorted(out, key=lambda r: -r["kwh"])
