"""Weather + PV data layer.

Sources (Common Challenge Assumptions, section 04):
  * Open-Meteo Historical Weather API (archive-api.open-meteo.com)
  * Open-Meteo Forecast API (api.open-meteo.com)
  * JRC PVGIS hourly series (re.jrc.ec.europa.eu)

Every fetch is cached on disk. If the network is unavailable (or
ENERPILOT_OFFLINE=1) a deterministic Lisbon climatology is used instead, so
the application always works in demo mode. The active source is reported by
/api/v1/health and shown in the UI.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pandas as pd

from .. import config as C

log = logging.getLogger("enerpilot.weather")

WEATHER_VARS = ["temperature", "humidity", "cloud_cover", "radiation"]
_OM_VARS = "temperature_2m,relative_humidity_2m,cloud_cover,shortwave_radiation"
_OM_MAP = {
    "temperature_2m": "temperature",
    "relative_humidity_2m": "humidity",
    "cloud_cover": "cloud_cover",
    "shortwave_radiation": "radiation",
}

# Lisbon climatology used for the offline fallback (monthly means).
_MONTH_TEMP = [11.6, 12.6, 14.9, 16.2, 18.6, 22.0, 23.9, 24.4, 22.9, 19.6, 15.1, 12.4]
_MONTH_CLOUD = [0.55, 0.50, 0.45, 0.45, 0.35, 0.20, 0.10, 0.10, 0.25, 0.45, 0.55, 0.55]

# PV performance: 14 % system loss (spec) and an average plane-of-array gain
# for a 35 deg south-facing array relative to horizontal irradiance.
PV_PERFORMANCE_RATIO = 1 - C.PV_SYSTEM_LOSS_PCT / 100
PV_TILT_GAIN = 1.10

WEATHER_SCENARIOS = {
    "live": {"name": "Live Lisbon forecast (Open-Meteo)"},
    "sunny_summer": {"name": "Sunny Summer heatwave", "temp_mean": 29.0, "amp": 7.0,
                     "cloud": 5.0, "sky_doy": 196, "sky_factor": 1.0, "humidity": 45.0},
    "mild_spring": {"name": "Mild Spring", "temp_mean": 18.5, "amp": 5.0,
                    "cloud": 35.0, "sky_doy": 110, "sky_factor": 0.8, "humidity": 65.0},
    "cloudy_winter": {"name": "Cloudy / rainy Winter (zero-PV)", "temp_mean": 10.0, "amp": 2.5,
                      "cloud": 100.0, "sky_doy": 15, "sky_factor": 0.02, "humidity": 92.0},
}


def now_local() -> datetime:
    """Current Lisbon wall-clock time, floored to the hour (naive)."""
    return datetime.now(ZoneInfo(C.TIMEZONE)).replace(minute=0, second=0, microsecond=0, tzinfo=None)


# ---------------------------------------------------------------- solar geometry
def clear_sky_ghi(times: pd.DatetimeIndex, doy_override: int | None = None) -> np.ndarray:
    """Haurwitz clear-sky global horizontal irradiance (W/m2) for Lisbon.

    Times are local wall-clock; the solar hour angle accounts for the
    longitude and the Portuguese summer time offset.
    """
    doy = np.full(len(times), doy_override) if doy_override else times.dayofyear.values
    hour = times.hour.values + 0.5  # centre of the hourly interval
    dst = np.array([(ZoneInfo(C.TIMEZONE).utcoffset(t.to_pydatetime()) or timedelta()).total_seconds() / 3600
                    for t in times]) if doy_override is None else np.where((doy > 88) & (doy < 300), 1.0, 0.0)
    solar_time = hour - dst + C.LON / 15.0
    decl = np.radians(23.45) * np.sin(np.radians(360 / 365 * (284 + doy)))
    ha = np.radians(15 * (solar_time - 12))
    lat = np.radians(C.LAT)
    cos_z = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(ha)
    cos_z = np.clip(cos_z, 0, 1)
    ghi = np.where(cos_z > 0.01, 1098 * cos_z * np.exp(-0.057 / np.maximum(cos_z, 0.01)), 0.0)
    return ghi


def pv_kw_per_kwp(radiation_w_m2) -> np.ndarray:
    """Convert horizontal irradiance to AC output per installed kWp."""
    return np.clip(np.asarray(radiation_w_m2, dtype=float) / 1000.0 * PV_TILT_GAIN * PV_PERFORMANCE_RATIO, 0, 1.0)


# ---------------------------------------------------------------- synthetic fallback
def synthetic_weather(times: pd.DatetimeIndex) -> pd.DataFrame:
    """Deterministic Lisbon climatology (seed 42) for offline demo mode."""
    days = times.normalize()
    uniq = days.unique()
    rng = np.random.default_rng(C.SEED)
    day_anom = pd.Series(rng.normal(0, 1.8, len(uniq)), index=uniq)
    day_cloud = pd.Series(rng.beta(1.2, 1.6, len(uniq)), index=uniq)
    month = times.month.values - 1
    base = np.array(_MONTH_TEMP)[month]
    amp = 4.0 + 2.5 * np.sin(np.pi * (times.month.values - 1) / 11)
    temp = base + amp * np.cos(2 * np.pi * (times.hour.values - 15) / 24) + day_anom.loc[days].values
    cloud = np.clip(np.array(_MONTH_CLOUD)[month] * 0.6 + day_cloud.loc[days].values * 0.6, 0, 1)
    ghi = clear_sky_ghi(times) * (1 - 0.75 * cloud ** 3.4)
    humidity = np.clip(70 + 20 * cloud - 1.2 * (temp - 18), 25, 100)
    return pd.DataFrame({"temperature": temp.round(1), "humidity": humidity.round(0),
                         "cloud_cover": (cloud * 100).round(0), "radiation": ghi.round(1)}, index=times)


def apply_scenario(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
    """Replace forecast weather with a what-if preset (keeps the timestamps)."""
    if scenario in (None, "", "live") or scenario not in WEATHER_SCENARIOS:
        return df
    s = WEATHER_SCENARIOS[scenario]
    times = df.index
    rng = np.random.default_rng(C.SEED)
    temp = s["temp_mean"] + s["amp"] * np.cos(2 * np.pi * (times.hour.values - 15) / 24) + rng.normal(0, 0.6, len(times))
    ghi = clear_sky_ghi(times, doy_override=s["sky_doy"]) * s["sky_factor"]
    out = df.copy()
    out["temperature"] = temp.round(1)
    out["cloud_cover"] = s["cloud"]
    out["humidity"] = s["humidity"]
    out["radiation"] = ghi.round(1)
    return out


# ---------------------------------------------------------------- data quality layer
def clean_weather(df: pd.DataFrame, start: datetime, end: datetime) -> tuple[pd.DataFrame, dict]:
    """Deduplicate, re-index to a strict hourly grid, interpolate gaps, clip ranges."""
    report = {"rows_in": int(len(df)), "duplicates_removed": 0, "gaps_filled": 0, "values_clipped": 0}
    df = df[~df.index.duplicated(keep="first")].sort_index()
    report["duplicates_removed"] = report["rows_in"] - int(len(df))
    idx = pd.date_range(start, end, freq="h", inclusive="left")
    df = df.reindex(idx)
    missing = int(df[WEATHER_VARS].isna().any(axis=1).sum())
    df = df.interpolate(limit_direction="both")
    fallback = synthetic_weather(idx)
    df = df.fillna(fallback)
    report["gaps_filled"] = missing
    bounds = {"temperature": (-10, 48), "humidity": (0, 100), "cloud_cover": (0, 100), "radiation": (0, 1200)}
    for col, (lo, hi) in bounds.items():
        bad = int(((df[col] < lo) | (df[col] > hi)).sum())
        report["values_clipped"] += bad
        df[col] = df[col].clip(lo, hi)
    report["rows_out"] = int(len(df))
    return df, report


# ---------------------------------------------------------------- disk cache helpers
def _cache_read(name: str):
    p = C.CACHE_DIR / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # corrupt cache -> ignore
            return None
    return None


def _cache_write(name: str, payload) -> None:
    try:
        (C.CACHE_DIR / name).write_text(json.dumps(payload))
    except Exception as exc:  # cache is best-effort
        log.warning("cache write failed: %s", exc)


def _om_frame(payload: dict) -> pd.DataFrame:
    h = payload["hourly"]
    df = pd.DataFrame({_OM_MAP[k]: h[k] for k in _OM_MAP}, index=pd.to_datetime(h["time"]))
    return df.astype(float)


def _get_json(url: str, params: dict) -> dict:
    with httpx.Client(timeout=C.HTTP_TIMEOUT_S) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------- public API
def load_weather(now: datetime | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (history, forecast, meta).

    history: HISTORY_DAYS of hourly weather ending at `now` (exclusive)
    forecast: 7 days (168 h) of hourly weather starting at `now`
    """
    now = now or now_local()
    hist_start = (now - timedelta(days=C.HISTORY_DAYS)).replace(hour=0)
    fc_end = now + timedelta(hours=7 * 24)
    meta = {"source": "synthetic-fallback", "provider": "Lisbon climatology (deterministic, seed 42)",
            "fetched_at": now.isoformat(), "errors": []}

    frames = []
    if not C.OFFLINE:
        # 1) historical archive
        a_key = f"om_archive_{hist_start:%Y%m%d}_{now:%Y%m%d}.json"
        archive = _cache_read(a_key)
        if archive is None:
            try:
                archive = _get_json("https://archive-api.open-meteo.com/v1/archive", {
                    "latitude": C.LAT, "longitude": C.LON, "timezone": C.TIMEZONE,
                    "start_date": f"{hist_start:%Y-%m-%d}", "end_date": f"{(now - timedelta(days=1)):%Y-%m-%d}",
                    "hourly": _OM_VARS})
                _cache_write(a_key, archive)
            except Exception as exc:
                meta["errors"].append(f"archive: {exc}")
        # 2) recent past + forecast
        f_key = f"om_forecast_{now:%Y%m%d%H}.json"
        forecast = _cache_read(f_key)
        if forecast is None:
            try:
                forecast = _get_json("https://api.open-meteo.com/v1/forecast", {
                    "latitude": C.LAT, "longitude": C.LON, "timezone": C.TIMEZONE,
                    "past_days": 7, "forecast_days": 9, "hourly": _OM_VARS})
                _cache_write(f_key, forecast)
            except Exception as exc:
                meta["errors"].append(f"forecast: {exc}")
                # fall back to the most recent cached forecast, if any
                cached = sorted(C.CACHE_DIR.glob("om_forecast_*.json"))
                if cached:
                    forecast = json.loads(cached[-1].read_text())
                    meta["errors"].append(f"using cached forecast {cached[-1].name}")
        if archive is not None:
            frames.append(_om_frame(archive))
        if forecast is not None:
            frames.append(_om_frame(forecast))
        if archive is not None and forecast is not None:
            meta["source"] = "open-meteo"
            meta["provider"] = "Open-Meteo Historical Weather API + Forecast API"
        elif frames:
            meta["source"] = "open-meteo-partial"
            meta["provider"] = "Open-Meteo (partial) + climatology gap-fill"

    if frames:
        # archive first so its (reanalysis) values win over forecast-model values
        raw = pd.concat(frames)
        raw = raw[~raw.index.duplicated(keep="first")]
    else:
        raw = pd.DataFrame(columns=WEATHER_VARS, dtype=float)

    full, dq = clean_weather(raw, hist_start, fc_end)
    meta["data_quality"] = dq
    history = full.loc[full.index < now]
    fcast = full.loc[full.index >= now]
    meta["history_start"] = str(history.index[0])
    meta["history_end"] = str(history.index[-1])
    meta["forecast_start"] = str(fcast.index[0])
    meta["forecast_end"] = str(fcast.index[-1])
    return history, fcast, meta


def load_pv_profile() -> tuple[pd.Series, dict]:
    """Hourly AC output (kW) of a 1 kWp array for a full year, keyed by local
    (month, day, hour). Uses PVGIS seriescalc (35 deg tilt, south, 14 % loss)."""
    meta = {"source": "synthetic-fallback", "provider": "Clear-sky model x Lisbon cloud climatology",
            "tilt": C.PV_TILT, "azimuth": C.PV_AZIMUTH, "loss_pct": C.PV_SYSTEM_LOSS_PCT, "errors": []}
    key = f"pvgis_{C.PVGIS_YEAR}_{C.PV_TILT}_{C.PV_AZIMUTH}_{C.PV_SYSTEM_LOSS_PCT}.json"
    payload = None if C.OFFLINE else _cache_read(key)
    if payload is None and not C.OFFLINE:
        try:
            payload = _get_json("https://re.jrc.ec.europa.eu/api/v5_3/seriescalc", {
                "lat": C.LAT, "lon": C.LON, "peakpower": 1, "loss": C.PV_SYSTEM_LOSS_PCT,
                "angle": C.PV_TILT, "aspect": C.PV_AZIMUTH, "pvcalculation": 1,
                "startyear": C.PVGIS_YEAR, "endyear": C.PVGIS_YEAR, "outputformat": "json"})
            _cache_write(key, payload)
        except Exception as exc:
            meta["errors"].append(f"pvgis: {exc}")
    if payload is not None:
        rows = payload["outputs"]["hourly"]
        utc = pd.to_datetime([r["time"] for r in rows], format="%Y%m%d:%H%M", utc=True)
        local = utc.tz_convert(C.TIMEZONE).tz_localize(None).floor("h")
        s = pd.Series([r["P"] / 1000.0 for r in rows], index=local)
        s = s[~s.index.duplicated(keep="first")]
        meta.update(source="pvgis", provider=f"JRC PVGIS v5.3 ({payload['inputs']['meteo_data']['radiation_db']}), year {C.PVGIS_YEAR}")
    else:
        idx = pd.date_range(f"{C.PVGIS_YEAR}-01-01", f"{C.PVGIS_YEAR + 1}-01-01", freq="h", inclusive="left")
        s = pd.Series(pv_kw_per_kwp(synthetic_weather(idx)["radiation"].values), index=idx)
    s = s[~((s.index.month == 2) & (s.index.day == 29))]
    keyed = pd.Series(s.values, index=pd.MultiIndex.from_arrays([s.index.month, s.index.day, s.index.hour]))
    keyed = keyed[~keyed.index.duplicated(keep="first")]
    meta["annual_kwh_per_kwp"] = round(float(keyed.sum()), 1)
    return keyed, meta
