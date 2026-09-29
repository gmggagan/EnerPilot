"""PV scenario comparison + economics engine.

For every capacity two scenarios are evaluated on a full year of hourly data
(the household's simulated 365-day demand aligned with PVGIS hourly output):
  A - PV without changing habits
  B - PV + recommended flexible-load shifting (same optimiser as the dispatch)
Economics use the official assumptions: EUR 1,300/kWp, export EUR 0.08/kWh,
OPEX 1 %/yr of the investment, time-of-use tariff 0.18/0.28/0.40.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C
from .optimizer import optimize_series


class AnnualProfile:
    """Pre-aligned annual demand + 1 kWp PV series."""

    def __init__(self, hist: pd.DataFrame, jobs: list[dict], pv_keyed: pd.Series):
        year = hist.iloc[-365 * 24:] if len(hist) >= 365 * 24 else hist
        year = year[year.index >= year.index[0].ceil("D")] if year.index[0].hour else year  # whole days only
        self.scale = 365 * 24 / len(year)  # annualise shorter histories
        self.index = year.index
        self.demand = year["total"].to_numpy()
        keys = pd.MultiIndex.from_arrays([year.index.month, year.index.day, year.index.hour])
        self.pv1 = pv_keyed.reindex(keys).fillna(0.0).to_numpy()
        self.hours = year.index.hour.to_numpy()
        self.day_key = np.array([d.isoformat() for d in year.index.date])
        # only whole cycles inside the window are shiftable; the rest stays in the base load
        self.jobs_by_day: dict = {}
        schedulable = np.zeros(len(year))
        for j in jobs:
            slots = pd.date_range(pd.Timestamp(j["date"]) + pd.Timedelta(hours=j["start"]), periods=j["duration_h"], freq="h")
            if slots.isin(year.index).all():
                self.jobs_by_day.setdefault(j["date"], []).append(j)
                schedulable[year.index.get_indexer(slots)] += j["energy_kwh"] / j["duration_h"]
        self.base = self.demand - schedulable
        self._shift_cache: dict = {}

    def shifted_demand(self, capacity: float, enforce_rest_window: bool) -> tuple[np.ndarray, list[dict]]:
        key = (round(capacity, 3), enforce_rest_window)
        if key not in self._shift_cache:
            pv = self.pv1 * capacity
            out, placements, _ = optimize_series(self.base, pv, self.hours, self.day_key, self.jobs_by_day,
                                                 enforce_rest_window)
            self._shift_cache[key] = (out, placements)
        return self._shift_cache[key]


def _scenario(demand: np.ndarray, pv: np.ndarray, baseline_demand: np.ndarray, tariff: np.ndarray,
              capex: float, scale: float) -> dict:
    self_cons = np.minimum(demand, pv)
    grid = np.maximum(demand - pv, 0)
    export = np.maximum(pv - demand, 0)
    baseline_cost = float(np.sum(baseline_demand * tariff)) * scale
    import_cost = float(np.sum(grid * tariff)) * scale
    export_rev = float(np.sum(export)) * C.EXPORT_TARIFF * scale
    opex = capex * C.PV_OPEX_PCT
    gross = baseline_cost - import_cost + export_rev
    net = gross - opex
    prod = float(np.sum(pv)) * scale
    dem = float(np.sum(demand)) * scale
    base_grid = float(np.sum(baseline_demand)) * scale
    grid_kwh = float(np.sum(grid)) * scale
    payback = capex / net if net > 0 and capex > 0 else None
    return {
        "annual_production_kwh": round(prod, 1),
        "annual_demand_kwh": round(dem, 1),
        "self_consumed_kwh": round(float(np.sum(self_cons)) * scale, 1),
        "self_sufficiency_pct": round(float(np.sum(self_cons)) * scale / dem * 100, 1) if dem else 0.0,
        "self_consumption_pct": round(float(np.sum(self_cons)) * scale / prod * 100, 1) if prod else 0.0,
        "grid_purchased_kwh": round(grid_kwh, 1),
        "grid_reduction_kwh": round(base_grid - grid_kwh, 1),
        "grid_reduction_pct": round((base_grid - grid_kwh) / base_grid * 100, 1) if base_grid else 0.0,
        "grid_dependency_pct": round(grid_kwh / dem * 100, 1) if dem else 0.0,
        "exported_kwh": round(float(np.sum(export)) * scale, 1),
        "export_revenue_eur": round(export_rev, 2),
        "baseline_cost_eur": round(baseline_cost, 2),
        "import_cost_eur": round(import_cost, 2),
        "net_energy_cost_eur": round(import_cost - export_rev + opex, 2),
        "gross_annual_savings_eur": round(gross, 2),
        "annual_opex_eur": round(opex, 2),
        "net_annual_savings_eur": round(net, 2),
        "capital_investment_eur": round(capex, 2),
        "payback_years": round(payback, 1) if payback is not None else None,
        "net_benefit_25y_eur": round(net * 25 - capex, 0),
    }


def simulate_capacity(profile: AnnualProfile, capacity: float, enforce_rest_window: bool = True,
                      detail: bool = False) -> dict:
    tariff = C.tariff_for_hour(profile.hours).astype(float)
    pv = profile.pv1 * capacity
    capex = capacity * C.PV_COST_PER_KWP
    shifted, placements = profile.shifted_demand(capacity, enforce_rest_window)
    a = _scenario(profile.demand, pv, profile.demand, tariff, capex, profile.scale)
    b = _scenario(shifted, pv, profile.demand, tariff, capex, profile.scale)
    res = {"capacity_kwp": capacity, "scenario_a": a, "scenario_b": b,
           "shifting_benefit_eur": round(b["net_annual_savings_eur"] - a["net_annual_savings_eur"], 2),
           "payback_gain_years": (round(a["payback_years"] - b["payback_years"], 1)
                                  if a["payback_years"] and b["payback_years"] else None)}
    if detail:
        idx = profile.index
        df = pd.DataFrame({"demand_a": profile.demand, "demand_b": shifted, "pv": pv}, index=idx)
        df["self_a"] = np.minimum(df["demand_a"], df["pv"])
        df["self_b"] = np.minimum(df["demand_b"], df["pv"])
        df["grid_a"] = np.maximum(df["demand_a"] - df["pv"], 0)
        df["grid_b"] = np.maximum(df["demand_b"] - df["pv"], 0)
        monthly = df.groupby(idx.month).sum() * profile.scale
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        res["monthly"] = [{"month": month_names[m - 1], **{k: round(float(v), 1) for k, v in r.items()}}
                          for m, r in monthly.iterrows()]
        hourly = df.groupby(idx.hour).mean()
        res["typical_day"] = [{"hour": f"{h:02d}:00", **{k: round(float(v), 3) for k, v in r.items()}}
                              for h, r in hourly.iterrows()]
        moved = [p for p in placements if p["shifted"]]
        by_app: dict = {}
        for p in moved:
            a_ = by_app.setdefault(p["label"], {"appliance": p["label"], "cycles_shifted": 0, "saving_eur": 0.0})
            a_["cycles_shifted"] += 1
            a_["saving_eur"] += p["saving_eur"]
        res["shift_summary"] = [{**v, "saving_eur": round(v["saving_eur"] * profile.scale, 2)} for v in by_app.values()]
        res["cycles_total"] = len(placements)
        res["cycles_shifted"] = len(moved)
    return res


def shifting_only(profile: AnnualProfile, enforce_rest_window: bool = True) -> dict:
    """Load shifting without any PV (tariff arbitrage only)."""
    tariff = C.tariff_for_hour(profile.hours).astype(float)
    shifted, _ = profile.shifted_demand(0.0, enforce_rest_window)
    before = float(np.sum(profile.demand * tariff)) * profile.scale
    after = float(np.sum(shifted * tariff)) * profile.scale
    return {"annual_cost_before_eur": round(before, 2), "annual_cost_after_eur": round(after, 2),
            "annual_saving_eur": round(before - after, 2)}
