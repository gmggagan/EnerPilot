# Architecture

```mermaid
flowchart TD
    HC[Household configuration<br/>occupancy · dog · weather scenario · PV kWp · rest window] --> CTX
    OM[(Open-Meteo<br/>archive + forecast)] --> DQ[Data quality layer<br/>dedupe · reindex · interpolate · clip]
    PVG[(JRC PVGIS<br/>hourly 1 kWp)] --> PVS
    DQ --> CTX[Context / occupancy engine<br/>deterministic day plans]
    CTX --> SIM[Appliance simulator<br/>essential · flexible · comfort]
    SIM --> HIST[(365-day historical profile)]
    HIST --> FE[Feature engineering<br/>time · weather · context · lags]
    FE --> ML[HistGradientBoosting<br/>chronological eval vs naive]
    ML --> FC[24h / 3d / 7d recursive forecast]
    FC --> PK[Peak intelligence]
    FC --> EX[Explanation engine]
    SIM --> CL[Load classification]
    FC --> OPT[Load optimiser<br/>solar 10-16 · off-peak 00-06 · rest window · 6.9 kW]
    CL --> OPT
    HIST --> PVS[PV simulation<br/>annual hourly balance]
    OPT --> PVS
    PVS --> ECO[Economics<br/>Scenario A vs B · payback]
    PK & EX & OPT & ECO --> API[FastAPI /api/v1]
    API --> UI[React dashboard<br/>Metrics · Dispatch · PV Sizing · Compliance]
```

## Request flow

```mermaid
sequenceDiagram
    participant UI as React UI
    participant API as FastAPI
    participant EN as Engine (cache)
    UI->>API: GET /api/v1/dashboard?horizon&occupancy_mode&dog_mode&weather_scenario&pv_kwp&enforce_rest_window
    API->>EN: forecast(cfg) (cached per what-if combination)
    EN-->>API: forecast + peaks, explanations, optimisation
    API-->>UI: JSON
    UI->>API: POST /api/v1/pv/simulate {capacity_kwp, enforce_rest_window}
    API->>EN: annual Scenario A/B (cached per capacity)
    EN-->>UI: selected + 2-12 kWp comparison
```

## Lifecycle
1. **Startup:** a background thread builds the engine.
   - Weather is fetched (disk-cached) and the history is simulated.
   - The model is trained and evaluated, and PVGIS is loaded (about 10–30 s).
   - All 60 what-if forecasts and all PV capacities are then pre-computed (about 45 s).
2. **Hourly rebuild:** when the Lisbon hour changes, the engine rebuilds in the background. The previous state keeps serving in the meantime, so the forecast always starts at the current hour.
3. **Failure handling:** each external call falls back to the last cached response, then to the deterministic climatology. The UI shows the active source.

## Deployment
- **Single container:** the root `Dockerfile` builds the UI with Node and serves `frontend/dist` from FastAPI on `$PORT`.
- **Dev:** `docker-compose.yml` runs the backend on :8000 plus the Vite dev server on :5173 (the `/api` proxy uses `VITE_API_TARGET`).
- **Static frontend (e.g. Vercel):** build with `VITE_API_BASE=https://<backend-host>`. CORS is open.
