import json
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase

from . import insights
from .reasons import classify

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
    "signups": 50,
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
            {"reason": "Insufficient funds", "kind": "customer", "today": 30, "recent": 2},
            {"reason": "Beneficiary bank not available", "kind": "system", "today": 5, "recent": 1},
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
    "rewards": {"today": {"count": 500, "value": 50000}, "last_paid_at": "2026-09-26T13:00:00"},
    "generated_at": "2026-09-26T14:00:00",
}


def run(**changes):
    p = deepcopy(PAYLOAD)
    for path, value in changes.items():
        if "__" not in path:
            p[path] = value
            continue
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
            {"reason": "Insufficient funds", "kind": "customer", "today": 15, "recent": 1},
            {"reason": "Beneficiary bank not available", "kind": "system", "today": 25, "recent": 10},
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

    def test_account_numbers_never_reach_the_screen(self):
        for raw in ("Insufficient funds (0011058788)", "Account on PND, debit not allowed on this account: 0011230485",
                    "Something new happened for 0011230485"):
            label, _ = classify(raw)
            self.assertNotRegex(label, r"\d{6,}")

    def test_real_messages_are_grouped(self):
        self.assertEqual(classify("Insufficient Balance"), ("Insufficient funds", "customer"))
        self.assertEqual(classify("Your maximum debit limit per transaction is : 50,000.00")[1], "customer")
        self.assertEqual(classify("HTTP error occurred")[1], "system")
        self.assertEqual(classify(None)[1], "unknown")

    def test_pnd_failures_are_called_out(self):
        reasons = [
            {"reason": "Insufficient funds", "kind": "customer", "today": 20, "recent": 1},
            {"reason": "Account restricted (PND)", "kind": "account", "today": 15, "recent": 1},
        ]
        self.assertIn("reasons-pnd", ids(run(health__reasons=reasons)))

    def test_paused_rewards_are_explained(self):
        result = run(rewards__today={"count": 0, "value": 0}, rewards__last_paid_at="2026-09-20T18:00:00")
        item = next(i for i in result["items"] if i["id"] == "rewards-paused")
        self.assertIn("20 Sep", item["detail"])

    def test_signups_compare_with_typical_weekday(self):
        item = next(i for i in run(funnel__signups={"today": 20, "yesterday": 20})["items"] if i["id"] == "signups")
        self.assertIn("typical Friday", item["title"])

    def _banks(self, gt_recent_failed, gt_recent_system=None):
        def part(settled, failed, system):
            return {"count": settled, "settled": settled, "pending": 0, "failed": failed, "system_failed": system,
                    "failure_rate": failed / settled, "system_rate": system / settled}

        def bank(key, count, failed, system, r_settled, r_failed, r_system):
            return {"key": key, "bank": key.title(), "value": 1000.0, **part(count, failed, system),
                    "recent": part(r_settled, r_failed, r_system)}

        system = gt_recent_failed if gt_recent_system is None else gt_recent_system
        items = [bank("OPAY", 100, 15, 1, 20, 3, 0), bank("PALMPAY", 80, 12, 1, 15, 2, 0),
                 bank("GTBANK", 40, 8, 1, 12, gt_recent_failed, system)]
        for b in items:
            others = [x for x in items if x is not b]
            for field, key in (("failed", "others_rate"), ("system_failed", "others_system_rate")):
                b["recent"][key] = sum(x["recent"][field] for x in others) / sum(x["recent"]["settled"] for x in others)
            b["others_system_rate"] = sum(x["system_failed"] for x in others) / sum(x["settled"] for x in others)
        return {"items": items, "all": items, "bank_count": 3, "recent_minutes": 30,
                "total": {"count": 220, "value": 3000.0, "failure_rate": 35 / 220, "system_rate": 3 / 220}}

    def test_bank_outage_is_flagged(self):
        result = run(banks=self._banks(gt_recent_failed=10))
        item = next(i for i in result["items"] if i["id"] == "bank-GTBANK")
        self.assertEqual(item["severity"], "bad")
        self.assertIn("bank-side", item["detail"])

    def test_normal_banks_stay_quiet(self):
        self.assertNotIn("bank-GTBANK", ids(run(banks=self._banks(gt_recent_failed=2))))

    def test_customer_side_failures_never_flag_a_bank(self):
        self.assertNotIn("bank-GTBANK", ids(run(banks=self._banks(gt_recent_failed=6, gt_recent_system=0))))

    def test_bank_near_its_own_normal_is_not_flagged(self):
        base = deepcopy(BASELINES)
        base["banks"] = {"GTBANK": {"settled": 500, "failure_rate": 0.29, "system_rate": 0.3}}
        p = deepcopy(PAYLOAD)
        p["banks"] = self._banks(gt_recent_failed=5)
        self.assertNotIn("bank-GTBANK", {i["id"] for i in insights.build(p, base)["items"]})
        self.assertFalse(next(x for x in p["banks"]["all"] if x["key"] == "GTBANK")["failing_now"])

    def test_bank_far_above_its_own_normal_is_flagged(self):
        base = deepcopy(BASELINES)
        base["banks"] = {"GTBANK": {"settled": 500, "failure_rate": 0.2, "system_rate": 0.02}}
        p = deepcopy(PAYLOAD)
        p["banks"] = self._banks(gt_recent_failed=10)
        self.assertIn("bank-GTBANK", {i["id"] for i in insights.build(p, base)["items"]})

    def test_real_bank_names_are_cleaned(self):
        from .banks import canonical, key
        cases = {
            "OPAY": "OPay",
            "MONIEPOINT MICROFINANCE BANK": "Moniepoint MFB",
            "PALMPAY": "PalmPay",
            "GTBANK PLC": "GTBank",
            "SmartCash Payment Service bank": "SmartCash PSB",
            "MoMo PSB": "MoMo PSB",
            "FIRST BANK OF NIGERIA": "First Bank",
            "KUDA MICROFINANCE BANK": "Kuda MFB",
            "ACCESS BANK PLC": "Access Bank",
            None: "Unknown bank",
        }
        for raw, expected in cases.items():
            self.assertEqual(canonical(raw), expected)
        self.assertEqual(key("GTBANK PLC"), key("Guaranty Trust Bank"))


class LoginTests(TestCase):
    password = "correct-horse-battery-staple"

    def setUp(self):
        cache.clear()
        get_user_model().objects.create_user("ops", password=self.password)

    def post(self, client, url, body):
        return client.post(url, json.dumps(body), content_type="application/json")

    def test_dashboard_data_needs_login(self):
        self.assertEqual(self.client.get("/api/pulse").status_code, 401)

    def test_wrong_password_is_rejected_generically(self):
        r = self.post(self.client, "/api/auth/login", {"username": "ops", "password": "nope"})
        self.assertEqual(r.status_code, 401)
        r2 = self.post(self.client, "/api/auth/login", {"username": "nobody", "password": "nope"})
        self.assertEqual(r.json()["error"], r2.json()["error"])

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.post(self.client, "/api/auth/login", {"username": "ops", "password": "nope"})
        r = self.post(self.client, "/api/auth/login", {"username": "ops", "password": self.password})
        self.assertEqual(r.status_code, 429)

    def test_login_then_data_then_logout(self):
        fake = {"clock_offset_seconds": 0}
        with patch("pulse.views.snapshot.build", return_value=fake):
            r = self.post(self.client, "/api/auth/login", {"username": "ops", "password": self.password})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["authenticated"])
            self.assertEqual(self.client.get("/api/pulse").status_code, 200)
            self.post(self.client, "/api/auth/logout", {})
            self.assertEqual(self.client.get("/api/pulse").status_code, 401)

    def test_remember_keeps_session_longer(self):
        self.post(self.client, "/api/auth/login", {"username": "ops", "password": self.password, "remember": True})
        self.assertGreater(self.client.session.get_expiry_age(), 7 * 24 * 3600)

    def test_login_requires_csrf_token(self):
        strict = Client(enforce_csrf_checks=True)
        r = self.post(strict, "/api/auth/login", {"username": "ops", "password": self.password})
        self.assertEqual(r.status_code, 403)
        strict.get("/api/auth/session")
        token = strict.cookies["csrftoken"].value
        r = strict.post("/api/auth/login", json.dumps({"username": "ops", "password": self.password}),
                        content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 200)

    def test_manage_page_is_admin_only(self):
        r = self.client.get("/manage/auth/user/", follow=True)
        self.assertEqual(r.redirect_chain[-1][0], "/")
        self.post(self.client, "/api/auth/login", {"username": "ops", "password": self.password})
        self.assertNotEqual(self.client.get("/manage/auth/user/").status_code, 200)
        user = get_user_model().objects.get(username="ops")
        user.is_staff = user.is_superuser = True
        user.save()
        self.post(self.client, "/api/auth/login", {"username": "ops", "password": self.password})
        self.assertEqual(self.client.get("/manage/auth/user/").status_code, 200)
        self.assertTrue(self.client.get("/api/auth/session").json()["is_admin"])

    def test_admin_login_form_is_disabled(self):
        r = self.client.post("/manage/login/", {"username": "ops", "password": self.password})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(self.client.get("/api/auth/session").json()["authenticated"])
