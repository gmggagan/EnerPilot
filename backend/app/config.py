"""Central configuration for ENERPILOT.

Official HackoWatt 2026 values (Common Challenge Assumptions + Scenario 5) are
marked OFFICIAL. Everything else is a documented modelling assumption
(see docs/ASSUMPTIONS.md).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

import warnings

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))
warnings.filterwarnings("ignore", message="Could not find the number of physical cores")

APP_NAME = "ENERPILOT"
TAGLINE = "Predict · Optimize · Save"
VERSION = "2.0.0"

# --- Location (OFFICIAL: example household location = Lisbon, Portugal) ---
LAT = 38.7223
LON = -9.1393
TIMEZONE = "Europe/Lisbon"
CITY = "Lisbon, Portugal"

# --- Reproducibility (spec: seed 42, noise N(0, 0.05^2)) ---
SEED = 42
NOISE_SIGMA_KWH = 0.05

# --- Grid connection: single-phase residential limit in Portugal ---
MAX_POWER_KW = 6.9

# --- Data window ---
# OFFICIAL minimum is 30 consecutive days. We use a full year so the model
# has seen every season (heating AND cooling) and the PV simulator can use a
# full annual demand profile.
HISTORY_DAYS = int(os.getenv("ENERPILOT_HISTORY_DAYS", "365"))
TEST_DAYS = 14  # chronological hold-out for evaluation

# --- OFFICIAL tariff (Common Challenge Assumptions, section 02) ---
TARIFF_BANDS = [
    {"start": 0, "end": 6, "rate": 0.18, "label": "Night Off-Peak"},
    {"start": 6, "end": 17, "rate": 0.28, "label": "Day Standard"},
    {"start": 17, "end": 22, "rate": 0.40, "label": "Evening Peak"},
    {"start": 22, "end": 24, "rate": 0.28, "label": "Late-Night Standard"},
]
_TARIFF_BY_HOUR = np.array(
    [next(b["rate"] for b in TARIFF_BANDS if b["start"] <= h < b["end"]) for h in range(24)]
)


def tariff_for_hour(hour):
    """EUR/kWh for an hour of day (int or numpy array)."""
    return _TARIFF_BY_HOUR[np.asarray(hour) % 24]


def tariff_label(hour: int) -> str:
    return next(b["label"] for b in TARIFF_BANDS if b["start"] <= hour % 24 < b["end"])


# --- OFFICIAL renewable simulator economics (section 03) ---
PV_COST_PER_KWP = 1300.0
EXPORT_TARIFF = 0.08
PV_OPEX_PCT = 0.01

# --- PV geometry (spec defaults for PVGIS) ---
PV_TILT = 35
PV_AZIMUTH = 0  # PVGIS convention: 0 = south
PV_SYSTEM_LOSS_PCT = 14
PV_CAPACITIES = [2, 4, 6, 8, 10, 12]
PVGIS_YEAR = 2023

# --- Load-shifting windows ---
SOLAR_WINDOW = (10, 16)       # primary target: 10:00-16:00
OFFPEAK_WINDOW = (0, 6)       # zero-PV fallback: 00:00-06:00 @ 0.18
REST_WINDOW = (22, 7)         # no noisy appliances 22:00-07:00
BAD_WEATHER_PV_KWH = 0.1      # daytime PV below this -> fallback

# --- Runtime ---
OFFLINE = os.getenv("ENERPILOT_OFFLINE", "0") == "1"
WARM_CACHE = os.getenv("ENERPILOT_WARM_CACHE", "1") == "1"  # pre-compute all what-if combinations
HTTP_TIMEOUT_S = float(os.getenv("ENERPILOT_HTTP_TIMEOUT", "20"))
DATA_DIR = Path(os.getenv("ENERPILOT_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIST = Path(os.getenv(
    "ENERPILOT_FRONTEND_DIST",
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist",
))
