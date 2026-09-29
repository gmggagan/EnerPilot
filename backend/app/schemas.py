"""Pydantic v2 request/config schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from . import config as C

OccupancyMode = Literal["auto", "both_wfh", "one_wfh", "both_away", "weekend_travel"]
DogMode = Literal["auto", "home", "away"]
WeatherScenario = Literal["live", "sunny_summer", "mild_spring", "cloudy_winter"]
Horizon = Literal["24h", "3d", "7d"]


class HouseholdConfig(BaseModel):
    """What-if context for the forecast horizon (history is always the real routine)."""
    residents: list[str] = Field(default_factory=lambda: ["Ola", "Tomek"])
    pet: str = "Dog"
    location: str = C.CITY
    occupancy_mode: OccupancyMode = "auto"
    dog_mode: DogMode = "auto"
    weather_scenario: WeatherScenario = "live"
    pv_kwp: float = Field(4.0, ge=0.0, le=20.0)
    enforce_rest_window: bool = True


class PVSimulateRequest(BaseModel):
    capacity_kwp: float = Field(4.0, ge=0.5, le=20.0)
    compare_capacities: list[float] = Field(default_factory=lambda: list(map(float, C.PV_CAPACITIES)),
                                            min_length=1, max_length=12)
    enforce_rest_window: bool = True


class ManualRun(BaseModel):
    """One appliance run planned by the user."""
    appliance: Literal["dishwasher", "washing", "charging"]
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start: int = Field(ge=0, le=23)
    flexible: bool = True  # True: EnerPilot may move it; False: keep the chosen time


class PlanRequest(BaseModel):
    horizon: Horizon = "24h"
    occupancy_mode: OccupancyMode | None = None
    dog_mode: DogMode | None = None
    weather_scenario: WeatherScenario | None = None
    pv_kwp: float | None = Field(None, ge=0, le=20)
    enforce_rest_window: bool | None = None
    runs: list[ManualRun] = Field(default_factory=list, max_length=60)
