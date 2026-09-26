from copy import deepcopy

from django.test import SimpleTestCase

from . import insights

TYPICAL = {
    "weekday": "Friday",
    "days": 4,
    "hourly_median": [10] * 6 + [60] * 18,
    "hourly_low": [8] * 6 + [50] * 18,
    "hourly_high": [12] * 6 + [70] * 18,
    "so_far_median": 500,
    "total_median": 1000,
    "fraction_median": 0.5,
    "fraction_low": 0.45,
    "fraction_high": 0.55,
}

BASELINES = {
    "typical": TYPICAL,
    "reasons": {"Insufficient funds": 0.6, "Beneficiary bank not available": 0.1},
    "products": {"Utilities": {"count": 200, "failure_rate": 0.05, "reversal_rate": 0.08}},
    "liveness": 0.25,
    "rewards": {"per_tx": 1.0, "value_per_tx": 100},
}

PAYLOAD = {
    "hour_now": 13,
    "transactions": {"today": {"count": 500, "failed": 50, "pending": 0}},
    "hourly": {"today": [10] * 6 + [60] * 18},
    "health": {
        "alert": None,
        "window_minutes": 15,
        "recent": {"count": 40, "failed": 6, "settled": 40, "failure_rate": 0.15},
        "baseline": {"failure_rate": 0.15},
        "reasons": [
            {"reason": "Insufficient funds", "today": 30, "recent": 2},
            {"reason": "Beneficiary bank not available", "today": 5, "recent": 1},
        ],
        "products": [{"kind": "Utilities", "count": 40, "failure_rate": 0.05, "reversal_rate": 0.08}],
        "liveness": {"failure_rate": 0.25},
    },
    "funnel": {
        "days": 30,
        "stages": [
            {"label": "Signed up", "count": 100, "lost": 40},
            {"label": "Account opened", "count": 60, "lost": 0},
        ],
        "signups": {"today": 50, "yesterday": 50},
    },
    "geography": {"located": 0, "cities": [], "recent_minutes": 10},
    "rewards": {"today": {"count": 500, "value": 50000}},
}


def run(**changes):
    p = deepcopy(PAYLOAD)
    for path, value in changes.items():
        target = p
        *keys, last = path.split("__")
        for k in keys:
            target = target[k]
        target[last] = value
    return insights.build(p, BASELINES)


def ids(result):
    return {i["id"] for i in result["items"]}


class InsightTests(SimpleTestCase):
    def test_normal_day_is_calm(self):
        result = run()
        severities = {i["severity"] for i in result["items"]}
        self.assertNotIn("bad", severities)
        self.assertNotIn("warn", severities)
        self.assertIn("volume", ids(result))

    def test_forecast_projects_from_typical_share_of_day(self):
        self.assertEqual(run()["forecast"]["projected"], 1000)

    def test_no_forecast_early_in_the_day(self):
        early = deepcopy(BASELINES)
        early["typical"] = {**TYPICAL, "fraction_median": 0.05}
        self.assertIsNone(insights.build(deepcopy(PAYLOAD), early)["forecast"])

    def test_busy_day_is_flagged(self):
        item = next(i for i in run(transactions__today={"count": 700, "failed": 50, "pending": 0})["items"]
                    if i["id"] == "volume")
        self.assertEqual(item["severity"], "good")
        self.assertIn("Busier", item["title"])

    def test_quiet_last_hour_warns(self):
        hourly = [10] * 6 + [60] * 18
        hourly[12] = 5
        item = next(i for i in run(hourly__today=hourly)["items"] if i["id"] == "hour")
        self.assertEqual(item["severity"], "warn")

    def test_alert_ranks_first(self):
        alert = {"title": "Transaction failures are spiking", "failure_rate": 0.4, "normal_rate": 0.15,
                 "failed": 20, "window_minutes": 15}
        first = run(health__alert=alert)["items"][0]
        self.assertEqual((first["id"], first["severity"]), ("alert", "bad"))

    def test_reason_shift_is_explained(self):
        reasons = [
            {"reason": "Insufficient funds", "today": 15, "recent": 1},
            {"reason": "Beneficiary bank not available", "today": 25, "recent": 10},
        ]
        items = run(health__reasons=reasons)["items"]
        shift = next(i for i in items if i["id"] == "reason-Beneficiary bank not available")
        self.assertIn("NIP outage", shift["detail"])

    def test_reversal_jump_is_flagged(self):
        products = [{"kind": "Utilities", "count": 40, "failure_rate": 0.05, "reversal_rate": 0.25}]
        self.assertIn("reversal-Utilities", ids(run(health__products=products)))

    def test_rewards_cost_growth_warns(self):
        item = next(i for i in run(rewards__today={"count": 700, "value": 70000})["items"] if i["id"] == "rewards")
        self.assertEqual(item["severity"], "warn")

    def test_without_history_it_still_answers(self):
        bare = {**BASELINES, "typical": None}
        result = insights.build(deepcopy(PAYLOAD), bare)
        self.assertIsNone(result["forecast"])
        self.assertIsNone(result["typical"])
