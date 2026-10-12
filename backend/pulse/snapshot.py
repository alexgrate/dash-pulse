from django.core.cache import cache

from . import baselines, insights, queries
from .explore import build_signup_history
from .trends import build_trends

TRENDS_SECONDS = 60 * 60


def trends(now):
    key = f"pulse:trends:{now:%Y-%m-%dT%H}"
    value = cache.get(key)
    if value is None:
        value = build_trends(now)
        cache.set(key, value, TRENDS_SECONDS)
    return value


SIGNUPS_SECONDS = 5 * 60


def signup_history(now):
    key = f"pulse:signups:{now:%Y-%m-%dT%H}:{now.minute // 5}"
    value = cache.get(key)
    if value is None:
        value = {by: build_signup_history(now.date(), by) for by in ("day", "week", "month")}
        cache.set(key, value, SIGNUPS_SECONDS)
    return value


def build():
    now = queries.lagos_now()
    data = queries.build_pulse(now)
    data["trends"] = trends(now)
    data["signup_history"] = signup_history(now)
    data["intelligence"] = insights.build(data, baselines.build(now))
    data["clock_offset_seconds"] = (now - queries.machine_lagos_now()).total_seconds()
    return data
