from . import baselines, insights, queries


def build():
    now = queries.lagos_now()
    data = queries.build_pulse(now)
    data["intelligence"] = insights.build(data, baselines.build(now))
    data["clock_offset_seconds"] = (now - queries.machine_lagos_now()).total_seconds()
    return data
