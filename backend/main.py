"""ENERPILOT API - AI-powered context-aware home energy management.

Run:  uvicorn main:app --port 8000
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import config as C
from app.schemas import DogMode, HouseholdConfig, Horizon, OccupancyMode, PlanRequest, PVSimulateRequest, WeatherScenario
from app.services.engine import engine
from app.services.household import DOG_MODES, OCCUPANCY_MODES
from app.services.simulator import P
from app.services.weather import WEATHER_SCENARIOS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

@asynccontextmanager
async def lifespan(_app):
    # train the model in the background so the first request is fast
    threading.Thread(target=engine.get_state, daemon=True).start()
    yield


app = FastAPI(title="ENERPILOT API", version=C.VERSION, lifespan=lifespan,
              description="EnerPilot - Predict · Optimize · Save. HackoWatt 2026 Scenario 5: Home Alone, But Not Really.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


def _cfg(occupancy_mode, dog_mode, weather_scenario, pv_kwp, enforce_rest_window) -> HouseholdConfig:
    return engine.resolve(occupancy_mode=occupancy_mode, dog_mode=dog_mode, weather_scenario=weather_scenario,
                          pv_kwp=pv_kwp, enforce_rest_window=enforce_rest_window)


# Shared optional query parameters for the what-if context
Q_OCC = Query(None, description="auto | both_wfh | one_wfh | both_away | weekend_travel")
Q_DOG = Query(None, description="auto | home | away")
Q_WX = Query(None, description="live | sunny_summer | mild_spring | cloudy_winter")
Q_PV = Query(None, ge=0, le=20, description="PV capacity (kWp) used for dispatch")
Q_REST = Query(None, description="Enforce 22:00-07:00 rest window for noisy appliances")


@app.get("/api/v1/ping")
def ping():
    """Instant liveness check for hosting platforms (does not wait for model training)."""
    return {"status": "ok", "ready": engine.state is not None}


@app.get("/api/v1/health")
def health():
    return engine.health()


@app.get("/api/v1/household/default")
def household_default():
    return {"config": HouseholdConfig().model_dump(), "current": engine.config.model_dump(),
            "options": {"occupancy_mode": OCCUPANCY_MODES, "dog_mode": DOG_MODES,
                        "weather_scenario": {k: v["name"] for k, v in WEATHER_SCENARIOS.items()},
                        "pv_capacities_kwp": C.PV_CAPACITIES},
            "appliance_parameters": P, "tariff": C.TARIFF_BANDS, "max_power_kw": C.MAX_POWER_KW}


@app.post("/api/v1/household/configure")
def household_configure(cfg: HouseholdConfig):
    engine.config = cfg
    return {"status": "updated", "config": cfg.model_dump()}


def _forecast(h, occ, dog, wx, pv, rest):
    return engine.forecast(_cfg(occ, dog, wx, pv, rest), h)


@app.get("/api/v1/forecast/24h")
def forecast_24h(occupancy_mode: OccupancyMode | None = Q_OCC, dog_mode: DogMode | None = Q_DOG,
                 weather_scenario: WeatherScenario | None = Q_WX, pv_kwp: float | None = Q_PV):
    return _forecast("24h", occupancy_mode, dog_mode, weather_scenario, pv_kwp, None)


@app.get("/api/v1/forecast/3d")
def forecast_3d(occupancy_mode: OccupancyMode | None = Q_OCC, dog_mode: DogMode | None = Q_DOG,
                weather_scenario: WeatherScenario | None = Q_WX, pv_kwp: float | None = Q_PV):
    return _forecast("3d", occupancy_mode, dog_mode, weather_scenario, pv_kwp, None)


@app.get("/api/v1/forecast/7d")
def forecast_7d(occupancy_mode: OccupancyMode | None = Q_OCC, dog_mode: DogMode | None = Q_DOG,
                weather_scenario: WeatherScenario | None = Q_WX, pv_kwp: float | None = Q_PV):
    return _forecast("7d", occupancy_mode, dog_mode, weather_scenario, pv_kwp, None)


@app.get("/api/v1/peaks")
def peaks(horizon: Horizon = "24h", occupancy_mode: OccupancyMode | None = Q_OCC, dog_mode: DogMode | None = Q_DOG,
          weather_scenario: WeatherScenario | None = Q_WX):
    return _forecast(horizon, occupancy_mode, dog_mode, weather_scenario, None, None)["peaks"]


@app.get("/api/v1/explanations")
def explanations(horizon: Horizon = "24h", occupancy_mode: OccupancyMode | None = Q_OCC,
                 dog_mode: DogMode | None = Q_DOG, weather_scenario: WeatherScenario | None = Q_WX):
    return engine.explanations(_cfg(occupancy_mode, dog_mode, weather_scenario, None, None), horizon)


@app.get("/api/v1/optimization")
def optimization(horizon: Horizon = "24h", occupancy_mode: OccupancyMode | None = Q_OCC,
                 dog_mode: DogMode | None = Q_DOG, weather_scenario: WeatherScenario | None = Q_WX,
                 pv_kwp: float | None = Q_PV, enforce_rest_window: bool | None = Q_REST):
    return engine.optimization(_cfg(occupancy_mode, dog_mode, weather_scenario, pv_kwp, enforce_rest_window), horizon)


@app.post("/api/v1/optimization/plan")
def optimization_plan(req: PlanRequest):
    """Optimise the user's own (manual) appliance plan instead of the routine."""
    cfg = _cfg(req.occupancy_mode, req.dog_mode, req.weather_scenario, req.pv_kwp, req.enforce_rest_window)
    return engine.optimization(cfg, req.horizon, manual_jobs=[r.model_dump() for r in req.runs])


@app.get("/api/v1/dashboard")
def dashboard(horizon: Horizon = "24h", occupancy_mode: OccupancyMode | None = Q_OCC,
              dog_mode: DogMode | None = Q_DOG, weather_scenario: WeatherScenario | None = Q_WX,
              pv_kwp: float | None = Q_PV, enforce_rest_window: bool | None = Q_REST):
    """Forecast + peaks + explanations + optimisation in one round trip (used by the UI)."""
    cfg = _cfg(occupancy_mode, dog_mode, weather_scenario, pv_kwp, enforce_rest_window)
    return {"forecast": engine.forecast(cfg, horizon), "explanations": engine.explanations(cfg, horizon),
            "optimization": engine.optimization(cfg, horizon), "health": engine.health()}


@app.post("/api/v1/pv/simulate")
def pv_simulate(req: PVSimulateRequest):
    return engine.pv_simulate(req.capacity_kwp, sorted(set(req.compare_capacities)), req.enforce_rest_window)


@app.get("/api/v1/pv/simulate")
def pv_simulate_get(capacity_kwp: float = Query(4.0, ge=0.5, le=20), enforce_rest_window: bool = True):
    return engine.pv_simulate(capacity_kwp, list(map(float, C.PV_CAPACITIES)), enforce_rest_window)


@app.get("/api/v1/model/metrics")
def model_metrics():
    return engine.get_state().forecaster.metrics


@app.get("/api/v1/historical")
def historical(days: int = Query(30, ge=1, le=365)):
    return engine.historical(days)


# ---- serve the built frontend (single-process deployment) -------------------
if C.FRONTEND_DIST.exists():
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        target = (C.FRONTEND_DIST / path).resolve()
        if path and target.is_file() and C.FRONTEND_DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(C.FRONTEND_DIST / "index.html")
