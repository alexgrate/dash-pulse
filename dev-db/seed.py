"""
Fake-data generator for the local MySQL mirror (docker-compose, port 3307).

    python dev-db/seed.py history --reset [--scale 1.0]      # backfill launch -> now
    python dev-db/seed.py live [--interval 3] [--speed 10]   # keep adding "now" events
    python dev-db/seed.py live --chaos                       # spike transfer failures
    python dev-db/seed.py live --bank-outage GTBank          # one destination bank failing

Volumes, mixes and failure rates copy what discovery found in production
(see DATA_NOTES.md). Production quirks are mirrored on purpose:
  - dashmfb-mcs and dashmfb-authservice store Lagos time (UTC+1)
  - dashmfb-cba-mcs and dashmfb-billspayment store UTC
  - notifications.created_at is a TIMESTAMP (session is forced to UTC)
  - failed liveness checks have PURPOSE = NULL, iOS is stored as "ios"

Refuses to connect anywhere except localhost, so it can never write to a real server.
"""
import argparse
import math
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from itertools import accumulate

import pymysql

HOST = os.environ.get("SEED_DB_HOST", "127.0.0.1")
PORT = int(os.environ.get("SEED_DB_PORT", "3307"))
PASSWORD = os.environ.get("SEED_DB_PASSWORD", "localroot")

LAUNCH = datetime(2026, 3, 14)        # first production rows (UTC)
QUEST_LAUNCH = datetime(2026, 5, 20)  # first reward payouts
SEPT_MIX_FROM = datetime(2026, 9, 1)  # INTRA jumped, airtime/betting fell
WAT = timedelta(hours=1)
TENANT = "69aecff363b533804b31d090"
BATCH = 5000


# ─── Shapes taken from production discovery ─────────────────────────

# Legacy transactions per day, at mid-month points (Lagos dates).
RATE_POINTS = [
    (datetime(2026, 3, 23), 6),
    (datetime(2026, 4, 15), 72),
    (datetime(2026, 5, 16), 124),
    (datetime(2026, 6, 15), 314),
    (datetime(2026, 7, 16), 745),
    (datetime(2026, 8, 16), 967),
    (datetime(2026, 9, 12), 1107),
    (datetime(2026, 12, 31), 1300),
]

# Activity by Lagos hour (0-23), normalised below to average 1.0.
HOURLY = [0.25, 0.15, 0.10, 0.08, 0.10, 0.25, 0.55, 0.90, 1.20, 1.40, 1.50, 1.55,
          1.60, 1.50, 1.45, 1.40, 1.40, 1.45, 1.50, 1.45, 1.30, 1.05, 0.75, 0.45]
HOURLY = [h * 24 / sum(HOURLY) for h in HOURLY]

MIX_BEFORE_SEPT = {"INTER": 74.5, "Airtime": 15.8, "Data Bundle": 4.25, "Betting & Lottery": 3.7,
                   "INTRA": 0.8, "Utilities": 0.8, "Cable TV": 0.08, "Transport and Toll Payment": 0.01}
MIX_SEPT = {"INTER": 77.5, "Airtime": 11.3, "Data Bundle": 2.9, "Betting & Lottery": 2.0,
            "INTRA": 5.5, "Utilities": 0.73, "Cable TV": 0.02, "Transport and Toll Payment": 0.01}

# (failed, reversed, success-but-flag-NULL, pending) probabilities; the rest succeed.
OUTCOMES = {
    "INTER": (0.174, 0.0, 0.05, 0.016),
    "INTRA": (0.011, 0.0, 0.0, 0.0),
    "Airtime": (0.09, 0.046, 0.0, 0.0002),
    "Data Bundle": (0.073, 0.083, 0.0, 0.0),
    "Betting & Lottery": (0.056, 0.083, 0.0, 0.0003),
    "Utilities": (0.074, 0.20, 0.0, 0.002),
    "Cable TV": (0.22, 0.055, 0.0, 0.01),
    "Transport and Toll Payment": (0.0, 1.0, 0.0, 0.0),
}
CHAOS_INTER_FAIL = 0.45
BANK_OUTAGE_FAIL = 0.6

FAIL_REASONS = {
    "Insufficient funds ({acct})": 935,
    "Account on PND, debit not allowed on this account: {acct}": 415,
    None: 245,
    "Daily CBA debit limit exceeded": 91,
    "HTTP error occurred": 68,
    "Request in progress": 59,
    "INVALID VIRTUAL ACCOUNT": 10,
    "Your maximum debit limit per transaction is : 50,000.00": 10,
    "Beneficiary Transfer Limit Exceeded": 7,
    "Invalid amount": 4,
    "Beneficiary Institution not available": 2,
    "Transaction Timed Out From Destination Institution": 1,
}
CHAOS_REASONS = {
    "HTTP error occurred": 50,
    "Transaction Timed Out From Destination Institution": 25,
    "Beneficiary Institution not available": 25,
}

BANKS = {"OPay": 22, "Moniepoint MFB": 16, "PalmPay": 14, "GTBank": 9, "Access Bank": 8,
         "Kuda MFB": 6, "Zenith Bank": 6, "First Bank": 6, "UBA": 5, "Wema Bank": 3,
         "Sterling Bank": 2, "Fidelity Bank": 2, "Stanbic IBTC": 1}

# (city, state, lat, lon, weight). The real LOCATION string format is unverified.
CITIES = [
    ("Ikeja", "Lagos", 6.6018, 3.3515, 20), ("Lekki", "Lagos", 6.4698, 3.5852, 12),
    ("Surulere", "Lagos", 6.5000, 3.3500, 8), ("Yaba", "Lagos", 6.5095, 3.3711, 5),
    ("Abuja", "FCT", 9.0765, 7.3986, 12), ("Port Harcourt", "Rivers", 4.8156, 7.0498, 8),
    ("Ibadan", "Oyo", 7.3775, 3.9470, 7), ("Kano", "Kano", 12.0022, 8.5920, 6),
    ("Benin City", "Edo", 6.3350, 5.6037, 4), ("Enugu", "Enugu", 6.5244, 7.5170, 4),
    ("Kaduna", "Kaduna", 10.5105, 7.4165, 3), ("Owerri", "Imo", 5.4840, 7.0351, 3),
    ("Jos", "Plateau", 9.8965, 8.8583, 2), ("Ilorin", "Kwara", 8.4966, 4.5426, 2),
    ("Abeokuta", "Ogun", 7.1475, 3.3619, 2), ("Warri", "Delta", 5.5160, 5.7502, 2),
    ("Uyo", "Akwa Ibom", 5.0377, 7.9128, 2),
]

CATEGORIES = ["Airtime", "Data Bundle", "Betting & Lottery", "Utilities", "Cable TV",
              "Transport and Toll Payment"]
BILLERS = {
    "Airtime": {"MTN": 50, "Airtel": 25, "Glo": 20, "9mobile": 5},
    "Data Bundle": {"MTN": 50, "Airtel": 25, "Glo": 20, "9mobile": 5},
    "Betting & Lottery": {"SportyBet": 40, "Bet9ja": 30, "BetKing": 15, "1xBet": 15},
    "Utilities": {"Ikeja Electric": 35, "Eko Electric": 25, "Abuja Electric": 20,
                  "PH Electric": 10, "Ibadan Electric": 10},
    "Cable TV": {"DStv": 50, "GOtv": 40, "StarTimes": 10},
    "Transport and Toll Payment": {"LCC Toll": 100},
}
BILL_FAILURES = [("91", "Biller unavailable"), ("06", "Transaction failed at biller"),
                 ("96", "System malfunction")]

# Current-phase snapshot counts from production.
PHASES = {"ACCOUNT_CREATED": 21624, "USER_PROFILE_CREATED": 18214,
          "RESEND_EMAIL_VERIFICATION_LINK": 10455, "EMAIL_VERIFICATION": 7058,
          "PHONE_OTP_VALIDATED": 2054, "RESEND_PHONE_OTP": 2017, "BVN_VALIDATION": 1879,
          "PHONE_VERIFICATION": 1776, "EMAIL_CONFIRMATION": 1030, "LIVENESS_CHECK_DONE": 447,
          "BVN_PHONE_MATCHED": 4}
# ASSUMED order. Confirm with the backend team and update here.
PHASE_ORDER = ["EMAIL_VERIFICATION", "RESEND_EMAIL_VERIFICATION_LINK", "EMAIL_CONFIRMATION",
               "PHONE_VERIFICATION", "RESEND_PHONE_OTP", "PHONE_OTP_VALIDATED", "BVN_VALIDATION",
               "BVN_PHONE_MATCHED", "USER_PROFILE_CREATED", "LIVENESS_CHECK_DONE",
               "ACCOUNT_CREATED"]
NEXT_PHASE = dict(zip(PHASE_ORDER, PHASE_ORDER[1:]))
NEXT_PHASE["RESEND_EMAIL_VERIFICATION_LINK"] = "EMAIL_CONFIRMATION"
NEXT_PHASE["RESEND_PHONE_OTP"] = "PHONE_OTP_VALIDATED"
USER_FROM = PHASE_ORDER.index("PHONE_OTP_VALIDATED")
LIVENESS_FROM = PHASE_ORDER.index("LIVENESS_CHECK_DONE")

REWARDS = {"DAILY_TRANSFER": 40719, "ONBOARDING_BONUS": 19417, "DAILY_AIRTIME_DATA": 10330,
           "REFERRAL": 4042, "DAILY_BILLS": 1783}
# Placeholder amounts; the real ones are unknown.
REWARD_AMOUNT = {"DAILY_TRANSFER": 50, "ONBOARDING_BONUS": 500, "DAILY_AIRTIME_DATA": 50,
                 "REFERRAL": 1000, "DAILY_BILLS": 50}

LIVENESS_PURPOSE = {"PASSWORD_RESET": 16620, "DEVICE_CHANGE": 1681, "PIN_RESET": 163}
NOTIF_CHANNELS = {"EMAIL": 129662, "SMS": 66458, "PUSH": 1733}

# Events per legacy transaction, from production row counts.
PER_TX = {"login": 4.35, "reset": 3.2, "notif": 2.1, "liveness": 0.19, "reward": 0.95}


# ─── Tables ─────────────────────────────────────────────────────────

TABLES = {
    "legacy": ("`dashmfb-mcs`.DashMFB_Transactions",
               "PAYMENT_REFERENCE, TRANSACTION_TYPE, AMOUNT, CREATED, UPDATED, CBA_RESPONSE_CODE, "
               "CBA_MESSAGE, PROVIDER_RESPONSE_MESSAGE, PROVIDER, ACCOUNT_NUMBER, BENEFICIARY_BANK_NAME, LOCATION_LAT, "
               "LOCATION_LON, TENANT_ID, NARRATION, BENEFICIARY_NAME, BENEFICIARY_ACCOUNT, CBA_REFERENCE, "
               "PROVIDER_REFERENCE"),
    "pt": ("`dashmfb-cba-mcs`.payment_transactions",
           "id, transfer_amount, beneficiary_bank_name, source_account, payment_reference, provider, "
           "status, transfer_type, transaction_direction, transaction_category, requery_count, "
           "created_at, updated_at, source_account_name, beneficiary_name, narration, session_id"),
    "bills": ("`dashmfb-billspayment`.bills_payment_transactions",
              "amount, biller_id, request_reference, status, response_code, response_message, "
              "latitude, longitude, created_at, completed_at"),
    "login": ("`dashmfb-mcs`.UM_LOGIN_TRAIL",
              "DEVICE_ID, USERNAME, LOCATION, DEVICE_OS, LOGIN_TIME, TENANT_ID"),
    "onboarding": ("`dashmfb-mcs`.DashMFB_UM_ONBOARDING_PROCESS",
                   "ONBOARDING_PHASE, NEXT_ONBOARDING_PHASE, DATE_CREATED, DATE_UPDATED, "
                   "ACCOUNT_OPENED_DATE, TENANT_ID, FIRSTNAME, LASTNAME, EMAIL, PHONE_NUMBER"),
    "accounts": ("`dashmfb-cba-mcs`.accounts",
                 "id, account_number, account_name, customer_email_address, customer_phone_number, "
                 "account_kyc_tier_code, status, created_at"),
    "liveness": ("`dashmfb-mcs`.LIVENESS_CHECK_LOG",
                 "DATE_CREATED, SCORE, CHANNEL, STATUS, PURPOSE, USERNAME, TENANT_ID"),
    "user": ("`dashmfb-authservice`.UM_FLAMINGO_USER",
             "id, username, registration_date, account_closure_status, created_at"),
    "reset": ("`dashmfb-authservice`.ResetToken", "tokenType, generatedOn, usedOn, created_at"),
    "notif": ("`dashmfb-notification`.notifications",
              "id, notification_channel, status, created_at"),
    "enroll": ("`dashmfb-cba-mcs`.quest_enrollments",
               "id, customer_id, status, total_earned, enrolled_at, created_at"),
    "reward": ("`dashmfb-cba-mcs`.quest_reward_transactions",
               "id, enrollment_id, reward_type, amount, status, created_at"),
}
BILLER_TABLES = ["`dashmfb-billspayment`.billers", "`dashmfb-billspayment`.biller_categories"]


# ─── Helpers ────────────────────────────────────────────────────────

class Pick:
    """Weighted random choice with precomputed cumulative weights."""

    def __init__(self, weights):
        self.items = list(weights)
        self.cum = list(accumulate(weights.values()))

    def __call__(self):
        return random.choices(self.items, cum_weights=self.cum)[0]


pick_mix_before, pick_mix_sept = Pick(MIX_BEFORE_SEPT), Pick(MIX_SEPT)
pick_reason, pick_chaos_reason, pick_bank = Pick(FAIL_REASONS), Pick(CHAOS_REASONS), Pick(BANKS)
pick_city = Pick({i: c[4] for i, c in enumerate(CITIES)})
pick_phase, pick_reward = Pick(PHASES), Pick(REWARDS)
pick_purpose, pick_channel = Pick(LIVENESS_PURPOSE), Pick(NOTIF_CHANNELS)
pick_biller = {cat: Pick(names) for cat, names in BILLERS.items()}


def poisson(lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, round(random.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= random.random()
        if p <= limit:
            return k
        k += 1


def daily_rate(local):
    if local <= RATE_POINTS[0][0]:
        return RATE_POINTS[0][1]
    for (d0, r0), (d1, r1) in zip(RATE_POINTS, RATE_POINTS[1:]):
        if local <= d1:
            return r0 + (r1 - r0) * (local - d0) / (d1 - d0)
    return RATE_POINTS[-1][1]


def day_factor(local):
    f = {5: 0.9, 6: 0.8}.get(local.weekday(), 1.0)
    if local.day >= 25 or local.day <= 2:  # payday
        f *= 1.2
    return f


def tx_per_hour(ts_utc):
    local = ts_utc + WAT
    return daily_rate(local) * day_factor(local) * HOURLY[local.hour] / 24


def nice(x, step, lo):
    return max(lo, int(round(x / step)) * step)


def amount_for(kind):
    if kind == "INTER":
        return min(nice(random.lognormvariate(math.log(15000), 1.1), 50, 100), 5_000_000)
    if kind == "INTRA":
        return nice(random.lognormvariate(math.log(8000), 1.0), 50, 100)
    if kind == "Airtime":
        return random.choices([100, 200, 300, 500, 1000, 1500, 2000, 5000],
                              [20, 22, 8, 25, 15, 3, 5, 2])[0]
    if kind == "Data Bundle":
        return random.choices([350, 500, 1000, 1500, 2000, 3000, 5000, 10000],
                              [10, 20, 25, 15, 12, 8, 7, 3])[0]
    if kind == "Betting & Lottery":
        return nice(random.lognormvariate(math.log(1500), 1.0), 100, 100)
    if kind == "Utilities":
        return nice(random.lognormvariate(math.log(8000), 0.7), 100, 1000)
    if kind == "Cable TV":
        return random.choice([2800, 5000, 8400, 11000, 15700, 24500, 37000])
    return random.choice([200, 300, 500])


def place():
    city, state, lat, lon, _ = CITIES[pick_city()]
    return (f"{city}, {state}, Nigeria",
            f"{lat + random.uniform(-0.04, 0.04):.6f}", f"{lon + random.uniform(-0.04, 0.04):.6f}")


def slug(text):
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def biller_id(category, name):
    return slug(f"{name} {category}")


def username(uid):
    return f"user{uid}@example.com"


def account_number(uid):
    return f"20{uid:08d}"


FIRST_NAMES = ["Ada", "Chinedu", "Tunde", "Ngozi", "Emeka", "Funmi", "Ibrahim", "Aisha", "Segun", "Kemi",
               "Obinna", "Zainab", "Yusuf", "Bisi", "Uche", "Amaka", "Femi", "Halima", "Chika", "Seyi"]
LAST_NAMES = ["Okafor", "Adeyemi", "Bello", "Eze", "Ogunleye", "Abubakar", "Nwosu", "Balogun", "Okeke",
              "Ibrahim", "Adebayo", "Musa", "Onyeka", "Akande", "Danjuma", "Obi", "Lawal", "Chukwu"]


def person(uid):
    r = random.Random(uid)
    first, last = r.choice(FIRST_NAMES), r.choice(LAST_NAMES)
    return {
        "first": first,
        "last": last,
        "name": f"{first} {last}",
        "email": f"{first}.{last}{uid % 10000}@example.com".lower(),
        "phone": f"080{uid % 100000000:08d}",
    }


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─── Writer ─────────────────────────────────────────────────────────

class Writer:
    def __init__(self, conn):
        self.conn = conn
        self.rows = {key: [] for key in TABLES}
        self.sql = {key: f"INSERT INTO {t} ({cols}) VALUES ({', '.join(['%s'] * len(cols.split(',')))})"
                    for key, (t, cols) in TABLES.items()}

    def add(self, key, row):
        self.rows[key].append(row)
        if len(self.rows[key]) >= BATCH:
            self.flush(key)

    def flush(self, key=None):
        with self.conn.cursor() as cur:
            for k in [key] if key else self.rows:
                if self.rows[k]:
                    cur.executemany(self.sql[k], self.rows[k])
                    self.rows[k].clear()


# ─── Event generation ───────────────────────────────────────────────

class Seeder:
    def __init__(self, writer, chaos=False, bank_outage=None):
        self.w = writer
        self.chaos = chaos
        self.bank_outage = bank_outage
        self.next_uid = 1
        self.holders = []       # user ids with an opened account
        self.enrollments = []   # quest enrollment ids

    def transaction(self, ts):
        if not self.holders:
            return
        kind = (pick_mix_sept if ts >= SEPT_MIX_FROM else pick_mix_before)()
        fail, rev, null_ok, pending = OUTCOMES[kind]
        if self.chaos and kind == "INTER":
            fail = CHAOS_INTER_FAIL
        r = random.random()
        if r < fail:
            outcome = "FAILED"
        elif r < fail + rev:
            outcome = "REVERSED"
        elif r < fail + rev + null_ok:
            outcome = "NULL_SUCCESS"
        elif r < fail + rev + null_ok + pending:
            outcome = "PENDING"
        else:
            outcome = "SUCCESS"

        uid = random.choice(self.holders)
        amount = amount_for(kind)
        ref = f"DMFB{uuid.uuid4().hex[:20].upper()}"
        _, lat, lon = place()
        local = ts + WAT
        is_bill = kind not in ("INTER", "INTRA")
        bank = pick_bank() if kind == "INTER" else ("Dash MFB" if kind == "INTRA" else None)
        outage = bool(self.bank_outage) and bank == self.bank_outage and random.random() < BANK_OUTAGE_FAIL
        if outage:
            outcome = "FAILED"
        cba_code = None if outcome in ("NULL_SUCCESS", "PENDING") else ("false" if outcome == "FAILED" else "true")
        message, provider_message = None, None
        if outcome == "FAILED":
            template = ("Beneficiary Institution not available" if outage
                        else pick_chaos_reason() if self.chaos and kind == "INTER" else pick_reason())
            provider_message = template.format(acct=account_number(uid)) if template else None
            if template and template.startswith("Account on PND") and random.random() < 0.33:
                message = "Account on PND, debit not allowed on this account"
            elif template and template.startswith("Insufficient") and random.random() < 0.11:
                message = "Insufficient Balance"
        elif cba_code is not None:
            message = "Successful"
        updated = local if outcome == "PENDING" else local + timedelta(seconds=random.randint(2, 30))

        sender = person(uid)
        if is_bill:
            receiver, receiver_account = None, f"0{random.randint(7000000000, 9099999999)}"
            narration = f"{kind} purchase"
        else:
            receiver = person(random.randint(10**7, 10**8)) if kind == "INTER" else person(random.choice(self.holders))
            receiver_account = f"{random.randint(10**9, 10**10 - 1)}"
            narration = f"Transfer to {receiver['name']}"
        cba_ref = f"CBA{uuid.uuid4().hex[:16].upper()}" if cba_code == "true" else None
        provider_ref = f"NCB{uuid.uuid4().hex[:16].upper()}" if outcome != "FAILED" else None
        self.w.add("legacy", (ref, kind, amount, local, updated, cba_code, message, provider_message,
                              "BAXI" if is_bill else "NCUBE", account_number(uid), bank,
                              lat, lon, TENANT, narration, receiver["name"] if receiver else None,
                              receiver_account, cba_ref, provider_ref))

        if outcome in ("SUCCESS", "NULL_SUCCESS", "REVERSED"):
            created = ts + timedelta(seconds=random.randint(1, 4))
            finished = created + (timedelta(minutes=random.randint(2, 40)) if outcome == "REVERSED"
                                  else timedelta(seconds=random.randint(1, 20)))
            self.w.add("pt", (str(uuid.uuid4()), amount, bank or "Dash MFB", account_number(uid), ref,
                              "NCUBE", "REVERSED" if outcome == "REVERSED" else "SUCCESSFUL",
                              "INTER" if kind == "INTER" else "INTRA", "WITHDRAWAL", "TRANSFERS",
                              random.randint(1, 3) if random.random() < 0.04 else 0,
                              created, finished, sender["name"], receiver["name"] if receiver else None,
                              narration, f"{random.randint(10**29, 10**30 - 1)}"))

        if is_bill and outcome in ("SUCCESS", "REVERSED"):
            failed = outcome == "REVERSED" and random.random() < 0.33
            code, msg = random.choice(BILL_FAILURES) if failed else ("00", "Successful")
            created = ts + timedelta(milliseconds=random.randint(300, 1500))
            done = created + timedelta(seconds=random.uniform(15, 60) if failed else random.uniform(1, 8))
            self.w.add("bills", (amount, biller_id(kind, pick_biller[kind]()), f"BP{uuid.uuid4().hex[:24]}",
                                 "FAILED" if failed else "SUCCESS", code, msg, lat, lon, created, done))

    def signup(self, ts):
        phase = pick_phase()
        idx = PHASE_ORDER.index(phase)
        local = ts + WAT
        opened = local + timedelta(minutes=random.randint(3, 90)) if phase == "ACCOUNT_CREATED" else None
        who = person(self.next_uid if idx >= USER_FROM else random.randint(9 * 10**8, 10**9))
        self.w.add("onboarding", (phase, NEXT_PHASE.get(phase), local,
                                  local + timedelta(minutes=random.randint(1, 120)), opened, TENANT,
                                  who["first"], who["last"], who["email"], who["phone"]))
        if idx < USER_FROM:
            return

        uid = self.next_uid
        self.next_uid += 1
        self.w.add("user", (uid, username(uid), local + timedelta(minutes=2),
                            "NONE" if random.random() < 0.968 else None, local))

        reached_liveness = idx >= LIVENESS_FROM
        if random.random() < (0.45 if reached_liveness else 0.30 if phase == "USER_PROFILE_CREATED" else 0):
            self.liveness_row(ts, uid, passed=False, purpose=None)
        if reached_liveness:
            self.liveness_row(ts + timedelta(minutes=1), uid, passed=True, purpose="ONBOARDING")
        if phase == "ACCOUNT_CREATED":
            self.holders.append(uid)
            self.w.add("accounts", (str(uuid.uuid4()), account_number(uid), who["name"].upper(), who["email"],
                                    who["phone"], random.choice([None, None, None, "TIER_1", "TIER_3"]), "ACTIVE",
                                    opened - WAT))
            if ts >= QUEST_LAUNCH and random.random() < 0.93:
                self.enroll(uid, ts)

    def liveness_row(self, ts, uid, passed, purpose):
        score = random.uniform(0.75, 0.99) if passed else random.uniform(0.10, 0.60)
        # Production bug mirrored: failed checks lose their PURPOSE.
        self.w.add("liveness", (ts + WAT, round(score, 4), "MOBILE", "PASSED" if passed else "LOW_SCORE",
                                purpose if passed else None, username(uid), TENANT))

    def liveness(self, ts):
        if self.holders:
            self.liveness_row(ts, random.choice(self.holders), passed=random.random() > 0.05,
                              purpose=pick_purpose())

    def login(self, ts):
        if not self.holders:
            return
        uid = random.choice(self.holders)
        location, _, _ = place()
        os_name = "ios" if uid % 100 < 10 or random.random() < 0.005 else "ANDROID"
        device = f"dev-{uid:07d}" if random.random() < 0.95 else f"dev-{uuid.uuid4().hex[:12]}"
        self.w.add("login", (device, username(uid), location, os_name, ts + WAT, TENANT))

    def reset_token(self, ts):
        local = ts + WAT
        used = local + timedelta(seconds=random.randint(20, 600)) if random.random() < 0.35 else None
        self.w.add("reset", (2, local, used, local))

    def notification(self, ts):
        self.w.add("notif", (str(uuid.uuid4()), pick_channel(), "DELIVERED", ts))

    def enroll(self, uid, ts):
        eid = str(uuid.uuid4())
        self.enrollments.append(eid)
        self.w.add("enroll", (eid, str(uid), "ACTIVE", 0, ts, ts))

    def reward(self, ts):
        if not self.enrollments:
            return
        kind = pick_reward()
        amount = REWARD_AMOUNT[kind]
        self.w.add("reward", (str(uuid.uuid4()), random.choice(self.enrollments), kind, amount, "CREDITED", ts))
        self.w.add("pt", (str(uuid.uuid4()), amount, "Dash MFB", "1000000001", f"QR{uuid.uuid4().hex[:24]}",
                          "NCUBE", "SUCCESSFUL", "INTRA", "DEPOSIT", "QUEST_REWARD", 0, ts, ts,
                          "Dash Rewards", None, f"Quest reward: {kind}", None))

    def window(self, start, seconds, mult=1.0):
        """Generate every kind of event for [start, start + seconds)."""
        base = tx_per_hour(start) * seconds / 3600 * mult
        signup_rate = base * (0.62 + 25 / daily_rate(start + WAT))
        ramp = min(1.0, max(0.0, (start - QUEST_LAUNCH).days / 14)) if start >= QUEST_LAUNCH else 0.0
        plan = [
            ("signups", self.signup, signup_rate),
            ("transactions", self.transaction, base),
            ("logins", self.login, base * PER_TX["login"]),
            ("reset_tokens", self.reset_token, base * PER_TX["reset"]),
            ("notifications", self.notification, base * PER_TX["notif"]),
            ("liveness", self.liveness, base * PER_TX["liveness"]),
            ("rewards", self.reward, base * PER_TX["reward"] * ramp),
        ]
        counts = {}
        for name, fn, lam in plan:
            n = poisson(lam)
            for _ in range(n):
                fn(start + timedelta(seconds=random.uniform(0, seconds)))
            counts[name] = n
        return counts


# ─── Commands ───────────────────────────────────────────────────────

def connect():
    if HOST not in ("127.0.0.1", "localhost"):
        sys.exit(f"Refusing to seed {HOST}: this script only writes to a local database.")
    return pymysql.connect(host=HOST, port=PORT, user="root", password=PASSWORD, autocommit=True,
                           charset="utf8mb4", init_command="SET time_zone = '+00:00'")


def seed_billers(cur):
    now = utcnow()
    cur.executemany("INSERT INTO `dashmfb-billspayment`.biller_categories (id, name, created_at) "
                    "VALUES (%s, %s, %s)", [(i, name, now) for i, name in enumerate(CATEGORIES, 1)])
    rows = [(biller_id(cat, name), slug(f"{name} {cat}").upper(), name, CATEGORIES.index(cat) + 1, now)
            for cat, names in BILLERS.items() for name in names]
    cur.executemany("INSERT INTO `dashmfb-billspayment`.billers (id, code, name, category_id, created_at) "
                    "VALUES (%s, %s, %s, %s, %s)", rows)


def history(args):
    conn = connect()
    with conn.cursor() as cur:
        if args.reset:
            for table, _ in TABLES.values():
                cur.execute(f"TRUNCATE TABLE {table}")
            for table in BILLER_TABLES:
                cur.execute(f"TRUNCATE TABLE {table}")
        else:
            cur.execute("SELECT COUNT(*) FROM `dashmfb-mcs`.DashMFB_Transactions")
            if cur.fetchone()[0]:
                sys.exit("Tables already have data. Re-run with --reset to wipe and regenerate.")
        seed_billers(cur)

    writer = Writer(conn)
    seeder = Seeder(writer)
    totals, now, cur_ts, quest_backfilled = {}, utcnow(), LAUNCH, False
    started = time.time()

    while cur_ts < now:
        if not quest_backfilled and cur_ts >= QUEST_LAUNCH:
            for uid in random.sample(seeder.holders, int(len(seeder.holders) * 0.6)):
                seeder.enroll(uid, cur_ts + timedelta(hours=random.uniform(0, 72)))
            quest_backfilled = True
        seconds = min(3600.0, (now - cur_ts).total_seconds())
        for k, v in seeder.window(cur_ts, seconds, args.scale).items():
            totals[k] = totals.get(k, 0) + v
        cur_ts += timedelta(hours=1)
        if cur_ts.hour == 0:
            print(f"\r  {cur_ts:%Y-%m-%d}  transactions so far: {totals.get('transactions', 0):,}",
                  end="", flush=True)

    writer.flush()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE `dashmfb-cba-mcs`.quest_enrollments e
            JOIN (SELECT enrollment_id, SUM(amount) s
                  FROM `dashmfb-cba-mcs`.quest_reward_transactions GROUP BY enrollment_id) r
              ON r.enrollment_id = e.id
            SET e.total_earned = r.s""")
    print(f"\n\nDone in {time.time() - started:.0f}s")
    for k, v in totals.items():
        print(f"  {k:<14} {v:>9,}")


def load_state(conn, seeder):
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM `dashmfb-authservice`.UM_FLAMINGO_USER")
        seeder.next_uid = cur.fetchone()[0] + 1
        cur.execute("SELECT DISTINCT ACCOUNT_NUMBER FROM `dashmfb-mcs`.DashMFB_Transactions")
        seeder.holders = [int(r[0][2:]) for r in cur.fetchall() if r[0]]
        cur.execute("SELECT id FROM `dashmfb-cba-mcs`.quest_enrollments")
        seeder.enrollments = [r[0] for r in cur.fetchall()]
    if not seeder.holders:
        sys.exit("No history found. Run `seed.py history --reset` first.")


def live(args):
    conn = connect()
    writer = Writer(conn)
    seeder = Seeder(writer, chaos=args.chaos, bank_outage=args.bank_outage)
    load_state(conn, seeder)
    print(f"Live: every {args.interval}s at {args.speed}x real volume"
          f"{'  [CHAOS: transfer failures spiking]' if args.chaos else ''}. Ctrl+C to stop.")
    try:
        while True:
            end = utcnow()
            counts = seeder.window(end - timedelta(seconds=args.interval), args.interval, args.speed)
            writer.flush()
            print(f"  {end + WAT:%H:%M:%S}  " + "  ".join(f"{k}={v}" for k, v in counts.items() if v))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        writer.flush()
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    h = sub.add_parser("history", help="backfill from launch until now")
    h.add_argument("--reset", action="store_true", help="wipe all seeded tables first")
    h.add_argument("--scale", type=float, default=1.0, help="volume multiplier (0.2 = quicker, smaller)")
    lv = sub.add_parser("live", help="keep inserting events for 'now'")
    lv.add_argument("--interval", type=float, default=3.0, help="seconds between batches")
    lv.add_argument("--speed", type=float, default=10.0, help="volume multiplier so the screen visibly moves")
    lv.add_argument("--chaos", action="store_true", help=f"force {CHAOS_INTER_FAIL * 100:.0f}%% INTER failures")
    lv.add_argument("--bank-outage", metavar="BANK", help="make transfers to one bank fail, e.g. \"GTBank\"")
    args = parser.parse_args()
    history(args) if args.command == "history" else live(args)


if __name__ == "__main__":
    main()
