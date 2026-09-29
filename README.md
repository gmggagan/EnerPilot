---
title: EnerPilot
emoji: ⚡
colorFrom: purple
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: AI home energy forecasting & PV simulator (HackoWatt 2026)
---

# ENERPILOT — Predict · Optimize · Save

**EnerPilot — AI-Powered Context-Aware Home Energy Management System**
HackoWatt 2026 · AI for Green Energy · **Scenario 5: "Home Alone — But Not Really"** (Lisbon, Portugal)

EnerPilot forecasts Ola & Tomek's household electricity demand (24 h / 3 days / 7 days), finds the
highest-demand hours, explains *why* demand changes, separates essential (dog-safety) loads from
flexible ones, recommends safe load shifting, and simulates the impact of a PV investment on grid
purchases, savings and payback. It is software-only: it gives predictions and decision support, it
never switches appliances.

## Quick start (local)

Requirements: Python 3.11+ (3.12 tested) and Node 18+.

```powershell
# Windows — one command (installs deps, builds the UI once, serves UI + API)
.\run_enerpilot.ps1
```
```bash
# macOS / Linux / Git Bash
./run_enerpilot.sh
```
Open **http://127.0.0.1:8000**. The first start downloads a year of Lisbon weather (Open-Meteo) and the
PVGIS profile, then trains the model (~10–30 s). Every what-if option is then pre-computed in the
background (~45 s), after which every control responds instantly.

### Manual / development mode
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
uvicorn main:app --port 8000                         # API docs: http://127.0.0.1:8000/docs

cd ../frontend
npm install
npm run dev                                          # http://localhost:5173 (proxies /api -> :8000)
```
> The `.venv` folder shipped next to this project was created on a different PC and points to that
> machine's Python — create a fresh one as shown above.

### Tests & build
```bash
cd backend && python -m pytest -q      # 34 tests, offline & deterministic
cd frontend && npm run build           # production bundle in frontend/dist
```

### Docker / cloud
```bash
docker compose up --build                            # dev: backend :8000 + Vite :5173
docker compose --profile prod up --build enerpilot   # single container, UI + API on :8080
docker build -t enerpilot . && docker run -p 8000:8000 enerpilot   # any container host (honours $PORT)
```

### Offline / demo mode
If Open-Meteo or PVGIS cannot be reached, EnerPilot falls back to cached responses and then to a
deterministic Lisbon climatology (seed 42). Force it with `ENERPILOT_OFFLINE=1`. The active source is
always shown in the sidebar footer and on the Compliance tab.

| Env var | Default | Meaning |
|---|---|---|
| `ENERPILOT_OFFLINE` | `0` | `1` = never call external APIs |
| `ENERPILOT_HISTORY_DAYS` | `365` | historical window (min. 30 required) |
| `ENERPILOT_WARM_CACHE` | `1` | pre-compute all what-if combinations |
| `ENERPILOT_DATA_DIR` | `backend/data` | cache + saved model |
| `VITE_API_BASE` | *(empty)* | backend origin when the UI is hosted separately (e.g. Vercel) |

## Using the application

| Control | Where | Effect |
|---|---|---|
| Household Profile | sidebar | Auto (hybrid week with weekend trips), both WFH, one WFH, both away, travel mode |
| Climate Condition | sidebar | Live Open-Meteo forecast, or what-if presets (sunny summer, cloudy/rainy winter → zero-PV fallback, mild spring) |
| Pet Logic — Dog Location | sidebar | Auto / dog stays home / dog travels (pet loads switched off) |
| Rooftop PV (kWp) | sidebar & PV tab | 2–12 kWp; drives the dispatch and the PV simulator |
| 24H / 3D / 7D | header | Forecast horizon |
| Rest Window 22h–07h | Dispatch & PV tabs | Stops noisy appliances at night; off → night off-peak fallback allowed |
| Hour scrubber / chart click | Metrics | Gauges + subsystem panel show the selected hour |
| Refresh | header | Re-fetches everything |

**Tabs:** **Metrics** (Q1/Q2: forecast, 80 % interval, temperature, top-3 peaks, explanations) ·
**Dispatch** (Q3: optimised schedule, essential vs flexible, recommendations) · **PV Sizing** (Q4:
Scenario A vs B, 2–12 kWp comparison, monthly & typical-day balance) · **Compliance** (required
outcomes checklist, model validation, 30/90/365-day history, data sources, assumptions).

## API (FastAPI — OpenAPI at `/docs`)
`GET /api/v1/health` · `GET /api/v1/household/default` · `POST /api/v1/household/configure` ·
`GET /api/v1/forecast/24h|3d|7d` · `GET /api/v1/peaks` · `GET /api/v1/explanations` ·
`GET /api/v1/optimization` · `POST /api/v1/pv/simulate` (also `GET`) · `GET /api/v1/model/metrics` ·
`GET /api/v1/historical` · `GET /api/v1/dashboard` (forecast + explanations + optimisation in one call).
What-if query parameters: `occupancy_mode`, `dog_mode`, `weather_scenario`, `pv_kwp`, `enforce_rest_window`.

## Project layout
```
enerpilot/
├── backend/
│   ├── main.py                      FastAPI routes (thin) + static UI hosting
│   ├── app/config.py                official tariff / PV economics / constants
│   ├── app/schemas.py               Pydantic v2 models
│   ├── app/services/weather.py      Open-Meteo + PVGIS + data-quality layer + offline fallback
│   ├── app/services/household.py    context / occupancy engine (day plans)
│   ├── app/services/simulator.py    appliance-level load model, essential/flexible/comfort
│   ├── app/services/forecaster.py   HistGradientBoosting ML engine + evaluation
│   ├── app/services/insights.py     peak intelligence + explanation engine
│   ├── app/services/optimizer.py    load-shifting optimiser
│   ├── app/services/pv_economics.py Scenario A/B + economics
│   ├── app/services/engine.py       orchestration + caching
│   └── tests/                       pytest suite
├── frontend/src/                    React 18 + Vite + Tailwind + Recharts (views/, components/, api.js)
├── docs/                            ARCHITECTURE, ML, ASSUMPTIONS, REQUIREMENTS_TRACEABILITY
└── Dockerfile · docker-compose.yml · run_enerpilot.ps1 · run_enerpilot.sh
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/ML.md](docs/ML.md),
[docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) and
[docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md).
