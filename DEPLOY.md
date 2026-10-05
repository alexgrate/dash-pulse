# Deploying Dash Pulse

Production runs on the Windows server at `C:\sites\dash-pulse`, as one NSSM service (`DashPulse`) behind IIS at **https://pulse.dash-mfb.com**.

```
Browser ──https──> IIS (pulse.dash-mfb.com, SSL) ──> 127.0.0.1:8765 Waitress (serve.py)
                                                        ├─ /            built React app (frontend/dist)
                                                        ├─ /api/*       data + login
                                                        └─ /manage/     user admin (admins only)
                                                     └──> MySQL 172.22.0.93 (read-only `robot` account)
```

## Updating (every release)

On the Mac:

```bash
git add . && git commit -m "describe the change" && git push
```

On the server (PowerShell):

```powershell
cd C:\sites\dash-pulse; git pull
cd backend
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py collectstatic --noinput
cd ..\frontend; npm ci; npm run build
nssm restart DashPulse
```

## First-time setup

1. Install Git, Python 3.12+ (python.org, "Add to PATH", disable the Microsoft Store `python` alias), Node 22+, NSSM.
2. Clone and install:
   ```powershell
   cd C:\sites
   git clone https://github.com/alexgrate/dash-pulse.git
   cd dash-pulse\backend
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
3. Create `backend\.env` (never commit it):
   ```env
   DJANGO_SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(50))">
   DJANGO_DEBUG=0
   DJANGO_ALLOWED_HOSTS=pulse.dash-mfb.com,localhost,127.0.0.1
   DJANGO_CSRF_TRUSTED_ORIGINS=https://pulse.dash-mfb.com
   PULSE_HTTPS=1
   BANK_DB_HOST=172.22.0.93
   BANK_DB_PORT=3306
   BANK_DB_USER=robot
   BANK_DB_PASSWORD=<password>
   PULSE_PUBLIC_URL=https://pulse.dash-mfb.com
   MS_GRAPH_TENANT_ID=<Directory (tenant) ID from Azure>
   MS_GRAPH_CLIENT_ID=<Application (client) ID from Azure>
   MS_GRAPH_CLIENT_SECRET=<client secret value>
   MS_GRAPH_SENDER=robot@dash-mfb.com
   ```
   The `MS_GRAPH_*` values send the "set your password" emails. The Azure app needs the **Mail.Send** application permission with admin consent, and the server needs outbound HTTPS to `login.microsoftonline.com` and `graph.microsoft.com`.
4. Check the bank connection. It must print `'+00:00', 1, 5000` (UTC, read-only, 5-second query limit):
   ```powershell
   .venv\Scripts\python.exe manage.py shell -c "from django.db import connections; c=connections['bank'].cursor(); c.execute('SELECT NOW(), @@session.time_zone, @@session.transaction_read_only, @@session.max_execution_time'); print(c.fetchone())"
   ```
5. Prepare the app:
   ```powershell
   .venv\Scripts\python.exe manage.py migrate
   .venv\Scripts\python.exe manage.py collectstatic --noinput
   cd ..\frontend; npm ci; npm run build
   mkdir C:\sites\dash-pulse\logs
   ```
6. Accounts:
   ```powershell
   cd C:\sites\dash-pulse\backend
   .venv\Scripts\python.exe manage.py pulse_user add <your.name>
   .venv\Scripts\python.exe manage.py pulse_user make-admin <your.name>
   .venv\Scripts\python.exe manage.py pulse_user add tv-wall
   ```
7. Service (admin PowerShell):
   ```powershell
   nssm install DashPulse "C:\sites\dash-pulse\backend\.venv\Scripts\python.exe"
   nssm set DashPulse AppParameters "serve.py"
   nssm set DashPulse AppDirectory "C:\sites\dash-pulse\backend"
   nssm set DashPulse AppStdout "C:\sites\dash-pulse\logs\dashpulse.log"
   nssm set DashPulse AppStderr "C:\sites\dash-pulse\logs\dashpulse.log"
   nssm set DashPulse AppRotateFiles 1
   nssm set DashPulse AppRotateBytes 10485760
   nssm set DashPulse Start SERVICE_AUTO_START
   nssm start DashPulse
   ```
   `netstat -ano | findstr :8765` must show `127.0.0.1:8765 LISTENING`.
8. DNS (cPanel → Zone Editor → dash-mfb.com → Manage): A record `pulse.dash-mfb.com.` → `132.145.47.17`.
9. IIS Manager:
   - Add Website `dash-pulse`, physical path `C:\sites\dash-pulse\deploy\iis`, binding http :80 host `pulse.dash-mfb.com`.
   - Bindings → Add https :443, host `pulse.dash-mfb.com`, Require SNI, the dash-mfb.com certificate.
   - Server node → URL Rewrite → View Server Variables → Add `HTTP_X_FORWARDED_PROTO` (once per server).
10. TV: Startup shortcut (`shell:startup`) to
    `"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk https://pulse.dash-mfb.com`,
    then sign in once as `tv-wall` with "Keep this screen signed in" ticked.

## Managing users

In the browser: sign in as an admin → **Manage users** (next to Sign out) → `/manage/`.

From the server:

```powershell
cd C:\sites\dash-pulse\backend
.venv\Scripts\python.exe manage.py pulse_user list
.venv\Scripts\python.exe manage.py pulse_user add <name>
.venv\Scripts\python.exe manage.py pulse_user password <name>
.venv\Scripts\python.exe manage.py pulse_user disable <name>
.venv\Scripts\python.exe manage.py pulse_user make-admin <name>
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| Page loads forever | A firewall (Windows or cloud) is blocking the port |
| 400 Bad Request | The address is missing from `DJANGO_ALLOWED_HOSTS` |
| 403 on sign-in | `DJANGO_CSRF_TRUSTED_ORIGINS` does not exactly match the URL |
| 500.52 | `HTTP_X_FORWARDED_PROTO` is not an allowed IIS server variable |
| 502 | Service down: `nssm status DashPulse`, read `logs\dashpulse.log` |
| Old screen after an update | `npm run build` was skipped, or hard-refresh with Ctrl+Shift+R |
| Admin page has no styling | `collectstatic` was skipped |
