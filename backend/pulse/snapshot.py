from . import baselines, insights, queries


def build():
    now = queries.lagos_now()
    data = queries.build_pulse(now)
    data["intelligence"] = insights.build(data, baselines.build(now))
    return data
