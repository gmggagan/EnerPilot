"""API contract tests - every endpoint of the specification (offline mode)."""
import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["app"] == "ENERPILOT" and body["weather"]["source"] == "synthetic-fallback"
    assert body["history_days"] >= 30


def test_household(client):
    d = client.get("/api/v1/household/default").json()
    assert d["config"]["residents"] == ["Ola", "Tomek"]
    r = client.post("/api/v1/household/configure", json={**d["config"], "pv_kwp": 6})
    assert r.status_code == 200 and r.json()["config"]["pv_kwp"] == 6
    client.post("/api/v1/household/configure", json=d["config"])
    bad = client.post("/api/v1/household/configure", json={"occupancy_mode": "nonsense"})
    assert bad.status_code == 422


@pytest.mark.parametrize("h,n", [("24h", 24), ("3d", 72), ("7d", 168)])
def test_forecast_horizons(client, h, n):
    body = client.get(f"/api/v1/forecast/{h}").json()
    assert body["hours"] == n and len(body["records"]) == n
    rec = body["records"][0]
    for key in ("predicted_kwh", "temperature", "tariff", "essential_kwh", "lower_kwh", "upper_kwh"):
        assert key in rec
    assert body["summary"]["total_kwh"] == pytest.approx(sum(r["predicted_kwh"] for r in body["records"]), abs=0.1)
    assert all(r["predicted_kwh"] >= r["essential_kwh"] - 1e-6 for r in body["records"])
    assert len(body["peaks"]["top3"]) == 3


def test_forecast_what_if_changes_result(client):
    home = client.get("/api/v1/forecast/24h", params={"occupancy_mode": "both_wfh"}).json()["summary"]["total_kwh"]
    away = client.get("/api/v1/forecast/24h", params={"occupancy_mode": "weekend_travel", "dog_mode": "away"}).json()["summary"]["total_kwh"]
    assert away < home and away > 0


def test_peaks_and_explanations(client):
    p = client.get("/api/v1/peaks", params={"horizon": "3d"}).json()
    assert [x["rank"] for x in p["top3"]] == [1, 2, 3]
    assert p["top3"][0]["kwh"] >= p["top3"][1]["kwh"] >= p["top3"][2]["kwh"]
    e = client.get("/api/v1/explanations", params={"horizon": "3d"}).json()
    assert "Expected consumption" in e["summary"] and "never drops to zero" in e["lowest"]
    assert len(e["day_changes"]) >= 3


def test_optimization(client):
    o = client.get("/api/v1/optimization", params={"horizon": "7d", "pv_kwp": 4}).json()
    assert o["after"]["cost_eur"] <= o["before"]["cost_eur"] + 1e-6
    assert o["after"]["demand_kwh"] == pytest.approx(o["before"]["demand_kwh"], abs=0.05)  # energy conserved
    assert {c["category"] for c in o["load_classes"]} == {"essential", "flexible", "comfort"}
    for s in o["schedule"]:
        if s["noisy"] and o["rules"]["rest_window_enforced"]:
            start = s["recommended_start"]
            if s["shifted"]:
                assert all(not (h >= 22 or h < 7) for h in range(start, start + s["duration_h"]))


def test_pv_simulate(client):
    r = client.post("/api/v1/pv/simulate", json={"capacity_kwp": 4}).json()
    assert [c["capacity_kwp"] for c in r["comparison"]] == [2, 4, 6, 8, 10, 12]
    a, b = r["selected"]["scenario_a"], r["selected"]["scenario_b"]
    assert a["capital_investment_eur"] == 5200 and a["annual_opex_eur"] == 52
    for key in ("annual_production_kwh", "self_sufficiency_pct", "grid_purchased_kwh", "exported_kwh",
                "export_revenue_eur", "gross_annual_savings_eur", "net_annual_savings_eur", "payback_years"):
        assert key in a and key in b
    assert b["net_annual_savings_eur"] >= a["net_annual_savings_eur"]
    assert 1 <= len(r["selected"]["monthly"]) <= 12 and len(r["selected"]["typical_day"]) == 24  # 12 with a full-year history
    assert client.get("/api/v1/pv/simulate", params={"capacity_kwp": 8}).status_code == 200


def test_model_metrics(client):
    m = client.get("/api/v1/model/metrics").json()
    assert m["model"] == "HistGradientBoostingRegressor" and m["split"] == "chronological"
    ev = m["evaluation"]
    assert ev["model_day_ahead"]["mae"] < ev["naive_same_hour_previous_day"]["mae"]
    assert {"lag_1", "lag_2", "lag_24", "lag_168", "roll_mean_24"} <= set(m["features"])


def test_historical(client):
    h = client.get("/api/v1/historical", params={"days": 30}).json()
    assert h["hours"] == 30 * 24 and len(h["daily"]) >= 30
    assert h["summary"]["min_hour_kwh"] > 0


def test_dashboard(client):
    d = client.get("/api/v1/dashboard", params={"horizon": "24h", "weather_scenario": "cloudy_winter"}).json()
    assert {"forecast", "explanations", "optimization", "health"} <= set(d)


def test_manual_plan(client):
    auto = client.get("/api/v1/optimization", params={"horizon": "3d", "pv_kwp": 4}).json()
    planner = auto["planner"]
    assert planner["mode"] == "auto" and set(planner["appliances"]) == {"dishwasher", "washing", "charging"}
    # pick a day with a full evening inside the horizon
    day = next(d for d in planner["days"] if 19 in d["hours"] and 20 in d["hours"])["date"]
    runs = [{"appliance": "dishwasher", "date": day, "start": 19, "flexible": True},
            {"appliance": "washing", "date": day, "start": 19, "flexible": False},
            {"appliance": "charging", "date": "2000-01-01", "start": 12, "flexible": True}]  # outside horizon
    r = client.post("/api/v1/optimization/plan", json={"horizon": "3d", "pv_kwp": 4, "runs": runs})
    assert r.status_code == 200
    o = r.json()
    assert o["planner"]["mode"] == "manual"
    assert any("outside" in w for w in o["planner"]["warnings"])
    sched = {s["appliance"]: s for s in o["schedule"]}
    assert set(sched) == {"dishwasher", "washing"}
    assert sched["washing"]["strategy"] == "fixed" and sched["washing"]["recommended_start"] == 19
    assert sched["dishwasher"]["strategy"] != "fixed"
    assert o["after"]["demand_kwh"] == pytest.approx(o["before"]["demand_kwh"], abs=0.05)
    assert o["after"]["cost_eur"] <= o["before"]["cost_eur"] + 1e-6
    # empty manual plan = no flexible runs at all
    empty = client.post("/api/v1/optimization/plan", json={"horizon": "3d", "runs": []}).json()
    assert empty["schedule"] == [] and empty["before"]["demand_kwh"] < o["before"]["demand_kwh"]
    bad = client.post("/api/v1/optimization/plan", json={"runs": [{"appliance": "oven", "date": day, "start": 1}]})
    assert bad.status_code == 422


def test_ping(client):
    r = client.get("/api/v1/ping")
    assert r.status_code == 200 and r.json()["status"] == "ok"
