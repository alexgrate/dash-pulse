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
- "Typical" = the same weekday over the last 8 weeks. With 4+ days, the single busiest and quietest day are dropped before taking the median, so one-off spikes (promos, outages, catch-ups) cannot distort it. The purple band is the middle half (25th–75th percentile) of those days. Needs at least 2 such days.
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

## Clock
- "Now" comes from the database (SELECT UTC_TIMESTAMP() + 1h), not the machine running Django. The dashboard server's Windows clock was found 1 hour ahead on 26 Sep 2026, which made the current hour look empty and flagged false "quiet hour" insights.
- The API returns server_time (DB-corrected); the frontend clock applies the difference, so the on-screen time is right even if the machine clock is wrong.

## Banks & devices (pulse/queries.py: banks, devices)
- Customer location is not captured in production (transaction coordinates are empty or one fixed Lagos point; login LOCATION is blank; bills have none). The Map scene hides itself when fewer than 3 cities show up (MAP_MIN_CITIES).
- Banks: inter-bank transfers today grouped by BENEFICIARY_BANK_NAME (names normalised to upper case for grouping), with count, successful value and failure rate.
- Bank alarms count only bank-side (system) failures: bank unavailable, timeouts, provider/HTTP errors, as classified in reasons.py. Customer-side failures (insufficient funds, limits, PND) never flag a bank; they still show in the Failing column.
- "Failing now": last 30 min, at least 10 settled transfers, 25%+ bank-side failures, 20+ points above other banks and above the bank's own 7-day usual. "Today" fallback: at least 30 settled, 15%+ bank-side, 12+ points above other banks and its usual. Constants: BANK_* in insights.py.
- Devices: distinct users who logged in today by DEVICE_OS (Android / iOS).
- Test locally: `python dev-db/seed.py live --speed 60 --bank-outage GTBank`

## Login (pulse/auth.py)
- Django's built-in accounts (stored in backend/db.sqlite3, passwords hashed with PBKDF2). No self sign-up; manage with `python manage.py pulse_user add|password|disable|enable|list <username>`.
- /api/pulse returns 401 unless signed in. The page shell is public but contains no data.
- 5 failed attempts per username+IP, or 20 per IP, lock logins for 15 minutes. Error messages never reveal whether a username exists.
- Sessions: HttpOnly + SameSite=Strict cookies, 12 hours, or 30 days with "Keep this screen signed in". CSRF token required on login/logout.
- Passwords: minimum 12 characters, common passwords rejected.
- Every login, failure, lockout and logout is logged (logger pulse.auth) with username and IP.
- Set PULSE_HTTPS=1 when served over HTTPS so cookies are marked Secure.
- User admin page at /manage/ (Django admin, Users only). Only accounts marked admin (`pulse_user make-admin <name>`) can open it; its own login form is disabled, so admins sign in through the dashboard login (with lockout and audit log) and are then let in. Admins see a "Manage users" link next to Sign out.
- Deploy step: `python manage.py collectstatic --noinput` so the admin page's styling is served.

## Live feed (pulse/live.py, /api/live)
- Replaces the old Briefing scene. Latest 200 rows of the legacy transactions table, read by primary key (ID DESC) so it stays fast however large the table grows. Cached 5 seconds; the scene polls every 5 seconds while on screen.
- Each row sends only product, destination bank (transfers to other banks), amount, outcome, a classified failure category and time. No names, account numbers or raw messages.
- Heartbeat: time since the last transaction, judged against the typical number of transactions for this hour on this weekday. Amber after 3× the usual gap (min 5 min), red after 6× (min 15 min).

## Trends (pulse/trends.py)
- Last 90 full days (today excluded), one point per day: transactions, successful value, failure rate, sign-ups, accounts opened. Cached for an hour.
- Weekly comparisons use daily averages: last 7 days vs the 7 before, and vs days 29–35 ago.
- Insight rule trend_shifts: flags any metric whose last-7-day average is 20%+ above or below four weeks earlier (only if it averaged 20+ a day). Keeps sustained changes, such as the ~33% drop after rewards stopped on 17 Sep 2026, in the top bar and ticker.
- The chart marks the last reward payout date.
- Weekly comparisons use the typical (median) day of each week, not the average, so one spike day (e.g. 25 Sep 2026: 2,368 transactions, 785 failed) cannot move a week. Failure rate stays total failed ÷ total settled.
