"""Context / occupancy engine for Ola, Tomek and their dog (Scenario 5).

Each calendar day gets a deterministic plan (seeded with 42 + the date), so
the historical profile and the forecast context are reproducible and
consistent with each other. The plan reflects the behaviour described in the
scenario: hybrid work, frequent weekend travel, the dog sometimes travelling
with the residents, variable meal times, dishwasher/washing machine only on
selected days and different entertainment patterns on weekdays/weekends.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

import numpy as np

from .. import config as C

DAY_TYPES = {
    "both_wfh": "Both residents working from home",
    "one_wfh": "One resident working from home",
    "both_away": "Both residents at the office",
    "weekend_home": "Weekend at home",
    "weekend_travel": "Weekend travel (apartment empty)",
}

OCCUPANCY_MODES = {
    "auto": "Auto (typical hybrid routine)",
    "both_wfh": "Both residents WFH",
    "one_wfh": "One resident WFH",
    "both_away": "Both away (office)",
    "weekend_travel": "Travelling (nobody home)",
}

DOG_MODES = {
    "auto": "Auto (dog travels on some trips)",
    "home": "Dog stays at home",
    "away": "Dog travels with residents",
}


@dataclass
class DayPlan:
    day: date
    day_type: str
    dog_home: bool
    wake_hour: int
    return_hour: int
    dinner_hour: int
    oven: bool
    dishwasher_start: int | None
    washing_start: int | None
    gaming_hours: list[int] = field(default_factory=list)
    outing_hours: list[int] = field(default_factory=list)

    @property
    def travel(self) -> bool:
        return self.day_type == "weekend_travel"

    @property
    def wfh_count(self) -> int:
        return {"both_wfh": 2, "one_wfh": 1}.get(self.day_type, 0)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["day"] = self.day.isoformat()
        d["label"] = DAY_TYPES[self.day_type]
        d["travel"] = self.travel
        d["wfh_count"] = self.wfh_count
        return d


def _weekend_trip(day: date) -> tuple[bool, bool]:
    """Is this weekend a trip, and does the dog come along? Shared by Sat+Sun."""
    saturday = day - timedelta(days=day.weekday() - 5)
    rng = np.random.default_rng([C.SEED, saturday.toordinal(), 7])
    travel = bool(rng.random() < 0.45)
    dog_travels = travel and bool(rng.random() < 0.35)
    return travel, dog_travels


def plan_for_day(day: date, occupancy_mode: str = "auto", dog_mode: str = "auto") -> DayPlan:
    rng = np.random.default_rng([C.SEED, day.toordinal()])
    weekend = day.weekday() >= 5

    # --- who is home? -------------------------------------------------------
    travel, dog_travels = _weekend_trip(day) if weekend else (False, False)
    weekday_type = str(rng.choice(["both_wfh", "one_wfh", "both_away"], p=[0.25, 0.40, 0.35]))
    if occupancy_mode == "auto":
        day_type = ("weekend_travel" if travel else "weekend_home") if weekend else weekday_type
    else:
        day_type = occupancy_mode
        dog_travels = False
    if day_type == "weekend_home" and not weekend:
        day_type = weekday_type

    if dog_mode == "home":
        dog_home = True
    elif dog_mode == "away":
        dog_home = False
    else:
        dog_home = not (day_type == "weekend_travel" and dog_travels)

    # --- routine timing -----------------------------------------------------
    wake_hour = int(rng.choice([6, 7])) if not weekend else int(rng.choice([7, 8, 9]))
    return_hour = int(rng.choice([17, 18, 19], p=[0.35, 0.45, 0.20]))
    dinner_hour = int(rng.choice([18, 19, 20, 21], p=[0.15, 0.40, 0.35, 0.10]))
    dinner_hour = max(dinner_hour, return_hour) if day_type == "both_away" else dinner_hour
    oven = bool(rng.random() < 0.40)

    # --- flexible appliances only on selected days --------------------------
    dishwasher_start = min(dinner_hour + 1, 22) if rng.random() < 0.55 else None
    if weekend:
        washing_start = int(rng.choice([10, 11])) if rng.random() < 0.60 else None
    else:
        washing_start = int(rng.choice([19, 20])) if rng.random() < 0.30 else None

    # --- entertainment differs weekday / weekend ----------------------------
    gaming_hours: list[int] = []
    if weekend and rng.random() < 0.70:
        gaming_hours = [16, 17, 21, 22]
    elif not weekend and rng.random() < 0.30:
        gaming_hours = [21, 22]
    outing_hours = list(range(11, 16)) if (day_type == "weekend_home" and rng.random() < 0.5) else []

    if day_type == "weekend_travel":
        dishwasher_start = washing_start = None
        gaming_hours, outing_hours = [], []
    if outing_hours and washing_start in outing_hours:
        washing_start = 10

    return DayPlan(day, day_type, dog_home, wake_hour, return_hour, dinner_hour, oven,
                   dishwasher_start, washing_start, gaming_hours, outing_hours)


def occupancy_profile(plan: DayPlan) -> tuple[np.ndarray, np.ndarray]:
    """Return (people_home[24], awake[24]) for a day plan."""
    people = np.zeros(24)
    awake = np.zeros(24, dtype=bool)
    if plan.travel:
        return people, awake
    sleep = [h for h in range(24) if h < plan.wake_hour or h >= 23]
    people[sleep] = 2
    for h in range(plan.wake_hour, 23):
        awake[h] = True
        if 9 <= h < plan.return_hour and plan.day_type in ("both_wfh", "one_wfh", "both_away"):
            people[h] = {"both_wfh": 2, "one_wfh": 1, "both_away": 0}[plan.day_type]
            awake[h] = people[h] > 0
        elif h in plan.outing_hours:
            people[h] = 0
            awake[h] = False
        else:
            people[h] = 2
    return people, awake
