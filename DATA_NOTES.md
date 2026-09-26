# Data Notes

## Timezones
- UTC: `dashmfb-cba-mcs`, `dashmfb-billspayment`, `dashmfb-notification`
- Lagos (WAT, UTC+1): `dashmfb-mcs`, `dashmfb-authservice`
- The dashboard displays everything in Lagos time.

## Transactions
- `mcs.DashMFB_Transactions` (legacy) = every customer attempt, including failures. Use it for counts, value, mix and failure rate.
- `cba-mcs.payment_transactions` (new) = what executed on core banking + reward payouts.
- Joined on `payment_reference`. NEVER add the two tables together.
- Outcome:
  - new.status = REVERSED    → REVERSED
  - new.status = SUCCESSFUL  → SUCCESS
  - legacy.CBA_RESPONSE_CODE = 'false' → FAILED
  - otherwise                → PENDING
- Reversals only occur on bill-type purchases (airtime, data, betting, utilities, cable).
- new `DEPOSIT` rows = `QUEST_REWARD` payouts, not customer inflows.

## Gotchas
- Cross-schema UNION/JOIN needs `CONVERT(col USING utf8mb4)` or `COLLATE` (collations differ).
- `DEVICE_OS` has `ios` in lowercase; normalize it.
- Useless columns (a single value): notifications.status, accounts.status/type, account_kyc_tier_code, account_closure_status.
- Failed liveness checks have PURPOSE = NULL (upstream logging bug).
- `TABLE_ROWS` in information_schema is an estimate.

## Never select
password, salt, BVN, NIN, *_IMAGE_PATH, names, phone, email, balances (without approval)

## Alert rule (pulse/queries.py)
- Compares the failure rate of the last 15 minutes against the previous 7 days.
- Fires only when all hold: at least 15 settled transactions in the window, the rate is 1.5x normal or more, and at least 10 percentage points above normal.
- Tune with RECENT_MINUTES, BASELINE_DAYS, ALERT_MIN_SETTLED, ALERT_RATIO, ALERT_MIN_GAP.
- Test locally: `python dev-db/seed.py live --speed 60 --chaos`

## Onboarding funnel (pulse/queries.py)
- Cohort: onboarding processes created in the last 30 days, grouped by their current ONBOARDING_PHASE.
- PHASE_ORDER is an ASSUMPTION. Confirm the real order with the backend team; stage counts depend on it.
- Stages: Signed up, Email confirmed, Phone verified, Profile created, Face check passed, Account opened.

## Map (pulse/geo.py)
- Uses LOCATION_LAT / LOCATION_LON on the legacy transactions table (today only), snapped to a 0.1° grid.
- Rows with non-numeric or out-of-Nigeria coordinates are ignored.
- Each grid cell is assigned to the nearest city in CITIES within 60 km; everything else counts as "Elsewhere".
- Outline: Natural Earth 1:50m (world-atlas), stored in frontend/src/lib/nigeria.js.

## Intelligence (pulse/baselines.py, pulse/insights.py)
- Runs entirely inside Django. No external AI service; no data leaves the bank network.
- "Typical" = the same weekday over the last 4 weeks (e.g. today vs the last 4 Fridays). Needs at least 2 such days.
- Forecast = transactions so far ÷ the share of a typical day that is usually done by this time.
- Other baselines (failure reasons, product failure/reversal rates, face-check failures, rewards per transaction) use the previous 7 days.
- Baselines are cached for 15 minutes; the live numbers still refresh every 60 seconds.
- Each rule returns an insight with severity (bad, warn, good, info), a plain-English title and detail, and a score. The top 10 by score are sent.
- Scenes with a warn/bad insight stay on screen 8 seconds longer (ATTENTION_BONUS_SECONDS in frontend/src/scenes/index.js).
- Tests: `python manage.py test pulse`

## Failure reasons (pulse/reasons.py)
- Real reasons live in PROVIDER_RESPONSE_MESSAGE; CBA_MESSAGE is empty ~87% of the time. We read provider first, then CBA.
- Raw messages embed customer account numbers (e.g. "Insufficient funds (0011058788)"). classify() maps them to fixed labels and strips any 6+ digit run, so account numbers never reach the API or the screen. A test enforces this.
- Categories: customer, account (PND holds), system, unknown (no message saved), other (unmatched text). Add new patterns to RULES when new messages appear.
- Real mix over 7 days (26 Sep 2026): 57% customer, 22% PND, 13% not recorded, 8% system.

## Rewards
- Real data had no quest_reward_transactions in the 3 days to 26 Sep 2026; the programme looks paused. The dashboard shows the last payout time instead of a bare zero.
