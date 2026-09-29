"""Orchestrates the full ENERPILOT pipeline and caches results.

Household config -> weather (history + forecast) -> data quality -> context
engine -> simulator (historical profile) -> features -> ML forecast -> peaks
-> explanations -> load classification -> optimiser -> PV simulation ->
economics.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from .. import config as C
from ..schemas import HouseholdConfig
from . import insights
from .forecaster import Forecaster
from .household import DAY_TYPES, plan_for_day
from .optimizer import optimize_series
from .pv_economics import AnnualProfile, shifting_only, simulate_capacity
from .simulator import APPLIANCES, COMPONENTS, ESSENTIAL, FLEXIBLE, LABELS, P, simulate
from .weather import WEATHER_SCENARIOS, apply_scenario, load_pv_profile, load_weather, now_local, pv_kw_per_kwp

log = logging.getLogger("enerpilot.engine")

HORIZONS = {"24h": 24, "3d": 72, "7d": 168}


@dataclass
class State:
    now: datetime
    history: pd.DataFrame
    forecast_weather: pd.DataFrame
    weather_meta: dict
    pv_meta: dict
    forecaster: Forecaster
    profile: AnnualProfile
    built_at: str
    build_seconds: float
    cache: dict = field(default_factory=dict)


class Engine:
    def __init__(self):
        self._lock = threading.Lock()
        self._rebuilding = False
        self.state: State | None = None
        self.config = HouseholdConfig()

    # ------------------------------------------------------------------ build
    def _build(self, now: datetime) -> State:
        t0 = time.time()
        hist_w, fc_w, wmeta = load_weather(now)
        sim, jobs = simulate(hist_w, noise=True)
        history = sim.join(hist_w)
        fc = Forecaster()
        fc.fit(hist_w, sim)
        pv_keyed, pvmeta = load_pv_profile()
        profile = AnnualProfile(history, jobs, pv_keyed)
        st = State(now, history, fc_w, wmeta, pvmeta, fc, profile,
                   datetime.now().isoformat(timespec="seconds"), round(time.time() - t0, 1))
        log.info("engine built in %.1fs (weather=%s, pv=%s)", st.build_seconds, wmeta["source"], pvmeta["source"])
        return st

    def warm(self, st: State) -> None:
        """Pre-compute every what-if combination so UI toggles respond instantly."""
        from ..schemas import DogMode, OccupancyMode, WeatherScenario
        from typing import get_args
        if not C.WARM_CACHE:
            return
        t0 = time.time()
        try:
            default = self.config
            combos = [(o, d, w) for w in get_args(WeatherScenario) for o in get_args(OccupancyMode) for d in get_args(DogMode)]
            combos.sort(key=lambda c: (c[2] != default.weather_scenario, c[0] != default.occupancy_mode, c[1] != default.dog_mode))
            for rest in (True, False):
                for cap in C.PV_CAPACITIES:
                    if self.state is not st:
                        return
                    self.pv_simulate(float(cap), list(map(float, C.PV_CAPACITIES)), rest)
                if rest:
                    for o, d, w in combos:
                        if self.state is not st:
                            return
                        self._forecast_full(self.resolve(occupancy_mode=o, dog_mode=d, weather_scenario=w))
            log.info("cache warmed in %.1fs", time.time() - t0)
        except Exception:
            log.exception("cache warm-up failed")

    def _rebuild_async(self, now: datetime):
        def run():
            try:
                st = self._build(now)
                self.state = st
                self.warm(st)
            except Exception:  # keep serving the previous state
                log.exception("background rebuild failed")
            finally:
                self._rebuilding = False
        self._rebuilding = True
        threading.Thread(target=run, daemon=True).start()

    def get_state(self) -> State:
        now = now_local()
        if self.state is None:
            with self._lock:
                if self.state is None:
                    self.state = self._build(now)
                    threading.Thread(target=self.warm, args=(self.state,), daemon=True).start()
        elif self.state.now != now and not self._rebuilding:
            self._rebuild_async(now)
        return self.state

    def resolve(self, **overrides) -> HouseholdConfig:
        data = self.config.model_dump()
        data.update({k: v for k, v in overrides.items() if v is not None})
        return HouseholdConfig(**data)

    # --------------------------------------------------------------- forecast
    def _forecast_full(self, cfg: HouseholdConfig) -> tuple[pd.DataFrame, list[dict], list[dict]]:
        st = self.get_state()
        key = ("fc", cfg.occupancy_mode, cfg.dog_mode, cfg.weather_scenario)
        if key not in st.cache:
            w = apply_scenario(st.forecast_weather.iloc[:168], cfg.weather_scenario)
            days = sorted(set(w.index.date))
            plans = {d: plan_for_day(d, cfg.occupancy_mode, cfg.dog_mode) for d in days}
            sim, jobs = simulate(w, plans=plans, noise=False)
            pred = st.forecaster.predict(w, sim, st.history["total"])
            fc = sim.join(w).join(pred)
            fc["predicted"] = np.maximum(fc["predicted"], fc["essential"])  # never below essential loads
            fc["lower"] = np.minimum(fc["lower"], fc["predicted"])
            fc["tariff"] = C.tariff_for_hour(fc.index.hour)
            fc["pv_kw_per_kwp"] = pv_kw_per_kwp(fc["radiation"])
            st.cache[key] = (fc, jobs, [plans[d].to_dict() for d in days])
        return st.cache[key]

    def forecast(self, cfg: HouseholdConfig, horizon: str) -> dict:
        full, _, plans = self._forecast_full(cfg)
        fc = full.iloc[:HORIZONS[horizon]]
        pv = fc["pv_kw_per_kwp"] * cfg.pv_kwp
        records = []
        for ts, r in fc.iterrows():
            records.append({
                "time": ts.strftime("%Y-%m-%d %H:%M"), "label": ts.strftime("%a %H:%M"), "hour": ts.hour,
                "predicted_kwh": round(float(r["predicted"]), 3), "lower_kwh": round(float(r["lower"]), 3),
                "upper_kwh": round(float(r["upper"]), 3),
                "essential_kwh": round(float(r["essential"]), 3), "flexible_kwh": round(float(r["flexible"]), 3),
                "comfort_kwh": round(float(r["comfort"]), 3),
                "temperature": round(float(r["temperature"]), 1), "humidity": round(float(r["humidity"]), 0),
                "cloud_cover": round(float(r["cloud_cover"]), 0), "radiation": round(float(r["radiation"]), 0),
                "pv_kwh": round(float(r["pv_kw_per_kwp"] * cfg.pv_kwp), 3),
                "tariff": float(r["tariff"]), "is_peak_tariff": bool(r["tariff"] >= 0.40),
                "people_home": int(r["people_home"]), "dog_home": bool(r["dog_home"]),
                "day_type": str(r["day_type"]),
            })
        pk = insights.peaks(fc)
        top_times = {p["time"] for p in pk["top3"]}
        for rec in records:
            rec["is_top_peak"] = rec["time"] in top_times
        total = float(fc["predicted"].sum())
        cost = float((fc["predicted"] * fc["tariff"]).sum())
        first_days = {r["time"][:10] for r in records}
        return {
            "horizon": horizon, "hours": len(fc), "start": records[0]["time"], "end": records[-1]["time"],
            "config": cfg.model_dump(),
            "summary": {
                "total_kwh": round(total, 2), "avg_kwh_per_hour": round(total / len(fc), 3),
                "avg_kwh_per_day": round(total / len(fc) * 24, 2),
                "peak_kwh": round(float(fc["predicted"].max()), 3),
                "peak_time": fc["predicted"].idxmax().strftime("%Y-%m-%d %H:%M"),
                "min_kwh": round(float(fc["predicted"].min()), 3),
                "essential_kwh": round(float(fc["essential"].sum()), 2),
                "flexible_kwh": round(float(fc["flexible"].sum()), 2),
                "comfort_kwh": round(float(fc["comfort"].sum()), 2),
                "estimated_cost_eur": round(cost, 2),
                "temp_min": round(float(fc["temperature"].min()), 1), "temp_max": round(float(fc["temperature"].max()), 1),
                "temp_mean": round(float(fc["temperature"].mean()), 1),
                "pv_kwh": round(float(pv.sum()), 2),
                "uncertainty_kwh": round(float(1.28 * self.get_state().forecaster.residual_sigma * np.sqrt(len(fc))), 2),
            },
            "components": insights.component_totals(fc),
            "day_plans": [p for p in plans if p["day"] in first_days],
            "records": records,
            "peaks": pk,
        }

    def explanations(self, cfg: HouseholdConfig, horizon: str) -> dict:
        full, _, _ = self._forecast_full(cfg)
        return insights.explanations(full.iloc[:HORIZONS[horizon]], self.get_state().history)

    # ----------------------------------------------------------- optimisation
    def optimization(self, cfg: HouseholdConfig, horizon: str, manual_jobs: list[dict] | None = None) -> dict:
        """Optimise flexible appliance runs.

        manual_jobs=None -> runs come from the household routine (auto plan).
        manual_jobs=[...] -> the user's own plan replaces the routine's runs:
            {"appliance", "date": "YYYY-MM-DD", "start": hour, "flexible": bool}
            flexible runs may be moved by the optimiser, fixed runs stay put.
        """
        full, jobs, _ = self._forecast_full(cfg)
        fc = full.iloc[:HORIZONS[horizon]]
        pv = (fc["pv_kw_per_kwp"] * cfg.pv_kwp).to_numpy()
        hours = fc.index.hour.to_numpy()
        day_key = np.array([d.isoformat() for d in fc.index.date])
        tariff = fc["tariff"].to_numpy()

        def slots_of(j):
            return pd.date_range(pd.Timestamp(j["date"]) + pd.Timedelta(hours=j["start"]), periods=j["duration_h"], freq="h")

        # only whole cycles inside the horizon are schedulable; cycles cut by the
        # horizon start/end stay in the fixed base load where they already are
        auto_jobs, schedulable = [], np.zeros(len(fc))
        for j in jobs:
            slots = slots_of(j)
            if slots.isin(fc.index).all():
                auto_jobs.append(j)
                schedulable[fc.index.get_indexer(slots)] += j["energy_kwh"] / j["duration_h"]
        base = np.maximum(fc["predicted"].to_numpy() - schedulable, fc["essential"].to_numpy())

        warnings: list[str] = []
        fixed_jobs: list[dict] = []
        if manual_jobs is None:
            plan_jobs = [dict(j, flexible=True) for j in auto_jobs]
        else:
            plan_jobs = []
            for i, m in enumerate(manual_jobs, 1):
                spec = APPLIANCES.get(m.get("appliance"))
                if spec is None:
                    warnings.append(f"Run {i}: unknown appliance '{m.get('appliance')}' - ignored.")
                    continue
                j = {"appliance": m["appliance"], "label": spec["label"], "date": m["date"], "start": int(m["start"]),
                     "duration_h": spec["duration_h"], "energy_kwh": spec["energy_kwh"], "noisy": spec["noisy"],
                     "flexible": bool(m.get("flexible", True)), "manual": True}
                if not slots_of(j).isin(fc.index).all():
                    warnings.append(f"Run {i}: {spec['label']} on {m['date']} at {j['start']:02d}:00 "
                                    f"({spec['duration_h']} h) falls outside the {horizon} forecast horizon - ignored.")
                    continue
                if (j["noisy"] and cfg.enforce_rest_window and not j["flexible"]
                        and any(h >= C.REST_WINDOW[0] or h < C.REST_WINDOW[1] for h in range(j["start"], j["start"] + j["duration_h"]))):
                    warnings.append(f"Run {i}: fixed {spec['label']} at {j['start']:02d}:00 is inside the 22:00-07:00 "
                                    "rest window - kept because you fixed it.")
                plan_jobs.append(j)

        fixed_load = np.zeros(len(fc))
        jobs_by_day: dict = {}
        unmanaged = base.copy()
        for j in plan_jobs:
            idx = fc.index.get_indexer(slots_of(j))
            unmanaged[idx] += j["energy_kwh"] / j["duration_h"]
            if j["flexible"]:
                jobs_by_day.setdefault(j["date"], []).append(j)
            else:
                fixed_load[idx] += j["energy_kwh"] / j["duration_h"]
                fixed_jobs.append(j)
        opt_base = base + fixed_load
        if opt_base.max() > C.MAX_POWER_KW:
            warnings.append(f"Fixed runs push one hour to {opt_base.max():.2f} kWh - above the 6.9 kW connection limit.")
        optimized, placements, bad_days = optimize_series(opt_base, pv, hours, day_key, jobs_by_day, cfg.enforce_rest_window)

        for j in fixed_jobs:  # fixed runs are reported, never moved
            idx = fc.index.get_indexer(slots_of(j))
            per_h = j["energy_kwh"] / j["duration_h"]
            grid = np.maximum(optimized[idx] - pv[idx], 0)
            share = np.minimum(per_h, grid)  # energy of this run bought from the grid
            cost = float((share * tariff[idx]).sum())
            end = j["start"] + j["duration_h"]
            placements.append({
                "appliance": j["appliance"], "label": j["label"], "duration_h": j["duration_h"], "energy_kwh": j["energy_kwh"],
                "noisy": j["noisy"], "date": j["date"], "original_start": j["start"], "recommended_start": j["start"],
                "original_window": f"{j['start']:02d}:00-{end % 24:02d}:00", "recommended_window": f"{j['start']:02d}:00-{end % 24:02d}:00",
                "shifted": False, "strategy": "fixed",
                "reason": f"Fixed by you - kept at {j['start']:02d}:00 ({C.tariff_label(j['start'])} EUR {C.tariff_for_hour(j['start']):.2f}/kWh).",
                "cost_before_eur": round(cost, 4), "cost_after_eur": round(cost, 4), "saving_eur": 0.0, "manual": True})
        for p in placements:
            p.setdefault("manual", manual_jobs is not None)
        placements.sort(key=lambda p: (p["date"] or "", p["original_start"]))

        def stats(load):
            grid = np.maximum(load - pv, 0)
            exp = np.maximum(pv - load, 0)
            self_c = np.minimum(load, pv)
            return {"demand_kwh": round(float(load.sum()), 2), "grid_import_kwh": round(float(grid.sum()), 2),
                    "export_kwh": round(float(exp.sum()), 2), "pv_self_consumed_kwh": round(float(self_c.sum()), 2),
                    "self_consumption_pct": round(float(self_c.sum() / pv.sum() * 100), 1) if pv.sum() > 0 else 0.0,
                    "self_sufficiency_pct": round(float(self_c.sum() / load.sum() * 100), 1),
                    "grid_dependency_pct": round(float(grid.sum() / load.sum() * 100), 1),
                    "cost_eur": round(float((grid * tariff).sum() - exp.sum() * C.EXPORT_TARIFF), 2),
                    "peak_tariff_kwh": round(float(load[tariff >= 0.40].sum()), 2),
                    "max_hour_kwh": round(float(load.max()), 3)}

        before, after = stats(unmanaged), stats(optimized)
        series = [{"time": ts.strftime("%Y-%m-%d %H:%M"), "label": ts.strftime("%a %H:%M"), "hour": ts.hour,
                   "unmanaged_kwh": round(float(u), 3), "optimized_kwh": round(float(o), 3),
                   "essential_kwh": round(float(e), 3), "pv_kwh": round(float(p), 3),
                   "grid_before_kwh": round(float(max(u - p, 0)), 3), "grid_after_kwh": round(float(max(o - p, 0)), 3),
                   "tariff": float(t), "is_peak_tariff": bool(t >= 0.40),
                   "shifted_in_kwh": round(float(max(o - u, 0)), 3)}
                  for ts, u, o, e, p, t in zip(fc.index, unmanaged, optimized, fc["essential"], pv, tariff)]
        moved = [p for p in placements if p["shifted"]]
        return {
            "horizon": horizon, "config": cfg.model_dump(),
            "rules": {"solar_window": "10:00-16:00", "offpeak_fallback": "00:00-06:00 @ EUR 0.18",
                      "rest_window": "22:00-07:00 (no dishwasher / washing machine)",
                      "rest_window_enforced": cfg.enforce_rest_window,
                      "bad_weather_threshold": "every solar-window hour < 0.1 kWh PV",
                      "contiguous_cycles": True, "max_power_kw": C.MAX_POWER_KW},
            "before": before, "after": after,
            "savings": {"cost_eur": round(before["cost_eur"] - after["cost_eur"], 2),
                        "grid_import_kwh": round(before["grid_import_kwh"] - after["grid_import_kwh"], 2),
                        "peak_tariff_kwh": round(before["peak_tariff_kwh"] - after["peak_tariff_kwh"], 2),
                        "self_consumption_pts": round(after["self_consumption_pct"] - before["self_consumption_pct"], 1)},
            "schedule": placements, "shifted_count": len(moved),
            "planner": {
                "mode": "auto" if manual_jobs is None else "manual",
                "warnings": warnings,
                "appliances": APPLIANCES,
                "days": [{"date": str(d), "label": pd.Timestamp(str(d)).strftime("%a %d %b"),
                          "hours": sorted(int(h) for h in hours[day_key == d])} for d in dict.fromkeys(day_key)],
                "routine_jobs": [{"appliance": j["appliance"], "date": j["date"], "start": j["start"], "flexible": True}
                                 for j in auto_jobs],
            },
            "bad_weather_days": [d for d, bad in bad_days.items() if bad],
            "series": series,
            "load_classes": self._load_classes(),
            "recommendations": self._recommendations(fc, placements, before, after, cfg, bad_days),
        }

    def _load_classes(self) -> list[dict]:
        return ([{"component": k, "label": LABELS[k], "category": "essential", "shiftable": False} for k in ESSENTIAL]
                + [{"component": k, "label": LABELS[k], "category": "flexible", "shiftable": True} for k in FLEXIBLE]
                + [{"component": k, "label": LABELS[k], "category": "comfort", "shiftable": False}
                   for k in COMPONENTS if k not in ESSENTIAL and k not in FLEXIBLE])

    def _recommendations(self, fc, placements, before, after, cfg, bad_days) -> list[dict]:
        recs = []
        for p in placements:
            if p["shifted"]:
                recs.append({"type": "shift", "priority": "high" if p["saving_eur"] > 0.1 else "medium",
                             "title": f"{p['label']}: {p['original_window']} -> {p['recommended_window']} ({p['date']})",
                             "detail": p["reason"], "saving_eur": p["saving_eur"]})
        evening = fc[(fc.index.hour >= 17) & (fc.index.hour < 22)]
        hvac_eve = float(evening["hvac_comfort"].sum())
        if hvac_eve > 0.5 and cfg.pv_kwp > 0:
            recs.append({"type": "habit", "priority": "medium",
                         "title": "Pre-cool / pre-heat before 17:00",
                         "detail": (f"{hvac_eve:.1f} kWh of comfort heating/AC falls in the EUR 0.40 evening peak. "
                                    "Running the heat pump/AC harder between 14:00 and 17:00 while PV is producing "
                                    "lets the apartment coast through part of the peak."),
                         "saving_eur": round(hvac_eve * 0.3 * (0.40 - C.EXPORT_TARIFF), 2)})
        charging = float(fc["charging"].sum())
        if charging > 0:
            recs.append({"type": "habit", "priority": "low", "title": "Charge devices at midday on WFH days",
                         "detail": "Phone, tablet and laptop charging is flexible - plug in during 10:00-16:00 to use solar power.",
                         "saving_eur": round(charging * (0.28 - C.EXPORT_TARIFF), 2)})
        pet = P["pet_camera_kw"] * 24 + P["pet_feeder_idle_kw"] * 24 + 2 * P["pet_feeder_feed_kwh"]
        recs.append({"type": "context", "priority": "low", "title": "When the dog travels with you, switch to away mode",
                     "detail": (f"Pet camera, feeder and pet-safety climate control can be switched off "
                                f"(>= {pet:.2f} kWh/day plus heating/AC). When the dog stays home these loads are essential "
                                f"and are never shifted or cut."), "saving_eur": round(pet * 0.28, 2)})
        if any(bad_days.values()):
            recs.append({"type": "weather", "priority": "medium", "title": "Cloudy-day fallback active",
                         "detail": ("PV is forecast below 0.1 kWh in the solar window on "
                                    f"{', '.join(d for d, b in bad_days.items() if b)}. "
                                    + ("Cycles move to the cheapest allowed daytime slot because the 22:00-07:00 rest "
                                       "window is enforced; disable it to allow night off-peak (EUR 0.18) operation."
                                       if cfg.enforce_rest_window else
                                       "Cycles move to the night off-peak window 00:00-06:00 (EUR 0.18).")),
                         "saving_eur": None})
        if before["peak_tariff_kwh"] > 0:
            recs.append({"type": "insight", "priority": "low", "title": "Evening peak exposure",
                         "detail": (f"{before['peak_tariff_kwh']:.1f} kWh ({before['peak_tariff_kwh'] / before['demand_kwh'] * 100:.0f}%) "
                                    f"of demand falls in the 17:00-22:00 EUR 0.40 band; after optimisation "
                                    f"{after['peak_tariff_kwh']:.1f} kWh. Cooking and TV stay put - comfort is not compromised."),
                         "saving_eur": None})
        return recs

    # --------------------------------------------------------------------- PV
    def pv_simulate(self, capacity: float, compare: list[float], enforce_rest_window: bool) -> dict:
        st = self.get_state()
        key = ("pv", round(capacity, 2), tuple(compare), enforce_rest_window)
        if key not in st.cache:
            selected = simulate_capacity(st.profile, capacity, enforce_rest_window, detail=True)
            comparison = [simulate_capacity(st.profile, c, enforce_rest_window) for c in compare]
            valid = [c for c in comparison if c["scenario_b"]["payback_years"]]
            best = min(valid, key=lambda c: c["scenario_b"]["payback_years"])["capacity_kwp"] if valid else None
            st.cache[key] = {
                "selected": selected, "comparison": comparison, "best_payback_capacity_kwp": best,
                "shifting_only": shifting_only(st.profile, enforce_rest_window),
                "assumptions": {"pv_cost_per_kwp_eur": C.PV_COST_PER_KWP, "export_tariff_eur_kwh": C.EXPORT_TARIFF,
                                "opex_pct_of_capex": C.PV_OPEX_PCT * 100, "tilt_deg": C.PV_TILT,
                                "azimuth_deg": C.PV_AZIMUTH, "system_loss_pct": C.PV_SYSTEM_LOSS_PCT,
                                "tariff": C.TARIFF_BANDS, "rest_window_enforced": enforce_rest_window,
                                "pv_source": st.pv_meta, "demand_basis": "Simulated 365-day hourly household profile"},
            }
        return st.cache[key]

    # -------------------------------------------------------------- history
    def historical(self, days: int) -> dict:
        st = self.get_state()
        h = st.history.iloc[-days * 24:]
        records = [{"time": ts.strftime("%Y-%m-%d %H:%M"), "total_kwh": round(float(r["total"]), 3),
                    "essential_kwh": round(float(r["essential"]), 3), "flexible_kwh": round(float(r["flexible"]), 3),
                    "comfort_kwh": round(float(r["comfort"]), 3), "temperature": round(float(r["temperature"]), 1),
                    "people_home": int(r["people_home"]), "dog_home": bool(r["dog_home"]), "day_type": r["day_type"]}
                   for ts, r in h.iterrows()]
        daily = h.groupby(h.index.date).agg(total=("total", "sum"), essential=("essential", "sum"),
                                            flexible=("flexible", "sum"), comfort=("comfort", "sum"),
                                            temp=("temperature", "mean"), day_type=("day_type", "first"),
                                            dog_home=("dog_home", "first"))
        absent = h[h["people_home"] == 0]
        return {
            "days": days, "hours": len(h), "start": records[0]["time"], "end": records[-1]["time"],
            "total_history_days": round(len(st.history) / 24, 1),
            "summary": {"total_kwh": round(float(h["total"].sum()), 1),
                        "avg_kwh_per_day": round(float(h["total"].sum()) / len(h) * 24, 2),
                        "min_hour_kwh": round(float(h["total"].min()), 3),
                        "max_hour_kwh": round(float(h["total"].max()), 3),
                        "absent_hours": int(len(absent)),
                        "absent_avg_kwh": round(float(absent["total"].mean()), 3) if len(absent) else None,
                        "travel_days": int(daily["day_type"].eq("weekend_travel").sum()),
                        "dog_away_days": int((daily["dog_home"] == 0).sum()),
                        "day_type_counts": {DAY_TYPES[k]: int(v) for k, v in daily["day_type"].value_counts().items()},
                        "noise_sigma_kwh": C.NOISE_SIGMA_KWH, "seed": C.SEED},
            "daily": [{"date": d.isoformat(), "total_kwh": round(float(r["total"]), 2),
                       "essential_kwh": round(float(r["essential"]), 2), "flexible_kwh": round(float(r["flexible"]), 2),
                       "comfort_kwh": round(float(r["comfort"]), 2), "temp_mean": round(float(r["temp"]), 1),
                       "day_type": r["day_type"], "dog_home": bool(r["dog_home"])} for d, r in daily.iterrows()],
            "records": records,
            "components": insights.component_totals(h),
        }

    def health(self) -> dict:
        st = self.get_state()
        m = st.forecaster.metrics
        return {"status": "ok", "app": C.APP_NAME, "version": C.VERSION, "tagline": C.TAGLINE,
                "location": {"city": C.CITY, "lat": C.LAT, "lon": C.LON, "timezone": C.TIMEZONE},
                "now": st.now.strftime("%Y-%m-%d %H:%M"), "built_at": st.built_at, "build_seconds": st.build_seconds,
                "offline_mode": C.OFFLINE, "weather": st.weather_meta, "pv": st.pv_meta,
                "history_days": round(len(st.history) / 24, 1),
                "model": {"name": m.get("model"), "trained_at": m.get("trained_at"),
                          "day_ahead_mae": m["evaluation"]["model_day_ahead"]["mae"],
                          "day_ahead_rmse": m["evaluation"]["model_day_ahead"]["rmse"]},
                "weather_scenarios": {k: v["name"] for k, v in WEATHER_SCENARIOS.items()}}


engine = Engine()
