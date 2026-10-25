# RescueEye :D

RescueEye is a web platform for drone-based search-and-rescue. Drone footage is
analysed by AI to flag possible casualties and damage; Command Staff verify what
the AI found, dispatch the nearest available Field Responders, and track each
incident to resolution.

The repo has two parts:

- **Web app** (`src/`) — React + TypeScript, backed by Supabase PostgreSQL for
  accounts, organizations and drones, with in-memory stores for the rest.
- **Detection API** (`api/`) — Python FastAPI service that runs the AI models
  over live and uploaded drone feeds (casualty detection, damage classification,
  fire/smoke detection).

## Roles

| Role | What they do |
|---|---|
| **System Admin** | Reviews and approves organization registrations; manages organization account status. |
| **Agency Admin** | Manages the organization's personnel (Add Staff, activate/deactivate) and monitors response teams and incident history. |
| **Command Staff** | Watches live drone feeds, reviews AI detections, verifies casualties, dispatches responders, registers drones, uses the Damage Map. |
| **Field Responder** | Receives missions, views mission details and the map, updates status. |

Each role has its own route group in [src/app/router.tsx](src/app/router.tsx), gated by
[ProtectedRoute](src/features/auth/ProtectedRoute.tsx).

## Project structure

```
src/                         Web app
  app/                       router, root layout, query client, role layouts
  pages/                     one component per screen
  components/                UI, grouped by feature area
    ui/                      shared building blocks (Button, Panel, Table, …)
    landing/registration/    organization sign-up steps
    agency-admin/ command-staff/ detections/ map/ media/ …
  features/                  role data providers, auth, theming, media feeds
  db/                        Supabase data-access hooks (agencies, staff, drones, profiles)
  state/                     shared in-memory stores (detections, incidents, missions, …)
  hooks/                     general-purpose React hooks
  lib/                       utilities (Supabase client, labels, phone/address helpers, …)
  data/                      mock seed data for demo accounts
  types/                     shared domain types
  routes/                    route path definitions

api/                         Detection API (FastAPI)
  main.py                    app entry point
  routers/                   HTTP endpoints (/detect, /classify, /stream, /detections, …)
  services/                  model loading, casualty verdict, tracking, feeds, georeferencing
  models/                    weights the server loads (victim, damage, fire)
    base/                    stock Ultralytics weights (COCO, pose, classifier)
    archive/                 retired weights kept for reference
  scripts/training/          dataset preparation, training and evaluation scripts
  runs/                      training runs and candidate models (not in git)
  data/                      datasets, uploads and media (not in git)
  tests/                     pytest suite

supabase/migrations/         SQL to run in the Supabase SQL editor, in order
docs/                        data dictionary, database and Supabase guides
```

Model weights, datasets and training runs are **not in git** (see `.gitignore`) —
share them separately.

## Getting started

### Web app

Prerequisites: Node.js 18+, a Supabase project.

```bash
npm install
```

Create `.env` in the repo root:

```env
VITE_SUPABASE_URL=https://[YOUR-PROJECT].supabase.co
VITE_SUPABASE_ANON_KEY=[YOUR-ANON-KEY]
```

```bash
npm run dev      # http://localhost:5173
npm run build    # type-check and build for production
npm run lint     # oxlint
```

### Detection API

Prerequisites: Python 3.11, FFmpeg (bundled via `imageio-ffmpeg`).

```bash
cd api
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

- On Windows with any GPU, install `onnxruntime-directml` so models run on the GPU.
- `torch` must stay below 2.6 (pinned in `requirements.txt`).
- Put the trained weights in `api/models/` and the stock ones in `api/models/base/`.
  (Older checkouts with the stock weights loose in `api/` still work.)
- Tests: `.venv\Scripts\python.exe -m pytest -q`

#### Alerts (SMS, push, in-app)

When Command Staff dispatch a verified incident, the API sends each responder an
SMS, a push notification and an in-app alert, and records them in the `alert` and
`audit_history` tables ([api/services/alert_service.py](api/services/alert_service.py)).
Add these to `api/.env`:

```env
SUPABASE_URL=https://[YOUR-PROJECT].supabase.co
SUPABASE_SERVICE_ROLE_KEY=[service-role key — server only, never in the web app]
SEMAPHORE_API_KEY=[Semaphore API key]
# SEMAPHORE_SENDER_NAME=RescueEye   # a sender name registered with Semaphore
# EXPO_ACCESS_TOKEN=                # only if push security is on in the Expo project
```

For testing without paid credits, SMS can go through **textbee** instead: an
Android phone running the [textbee](https://textbee.dev) app sends each alert
from its own SIM. Set `SMS_PROVIDER=textbee`, `TEXTBEE_API_KEY` and
`TEXTBEE_DEVICE_ID` (both from the textbee dashboard). textbee alerts stay SENT —
it reports when the phone has queued the text, not a carrier delivery receipt.

Without credentials for the selected provider every SMS alert is recorded as FAILED; without a
registered Expo push token on the responder's `user` row every PUSH alert is.
The in-app alert is sent either way. Alerts go only to accounts in the database —
the built-in demo logins have no `user` row.

### Connecting drones

The API runs an always-on video receiver, [MediaMTX](https://github.com/bluenviron/mediamtx)
([api/services/drone_ingest.py](api/services/drone_ingest.py)). Install it once:

```bash
cd api && .venv/Scripts/python.exe -m scripts.get_mediamtx
```

Then, per drone, **once**: Drones → Connect Drone → type the drone's name →
scan the QR code (or copy the address) into **DJI Fly → Transmission → Live
Streaming Platforms → RTMP**. The address is `rtmp://<this computer>:1935/live/<name>`.
After that the pilot only presses **Go Live**: the feed opens on Live Monitoring
by itself, with detection running (about 3 seconds from Go Live to video), and
closes 10 seconds after the drone stops. Several drones share port 1935.

- The phone must reach this computer (same Wi-Fi or hotspot). Video is
  accepted from the network but only readable on this computer.
- Without MediaMTX, Connect Drone falls back to arming one listener per connection.

### Sign-in and security

Sign-in runs on the API, not in the browser ([api/services/auth.py](api/services/auth.py)).
The API checks the password (bcrypt; old SHA-256 hashes are upgraded on the
next sign-in) and returns a signed session token. The web app sends it with
every API call, on media URLs and the live WebSocket, and to Supabase, where
row-level security uses it ([07_security_rls.sql](supabase/migrations/07_security_rls.sql)).

- Every API endpoint except `/auth/login`, `/auth/register`, `/auth/demo` and
  `/health` requires a token. Only Command Staff dispatch; a responder reports
  only their own location and sees only their own alerts; live updates stay
  within the agency.
- `api/.env` needs `SUPABASE_SERVICE_ROLE_KEY` (the real service_role key) and
  `SUPABASE_JWT_SECRET` (Project Settings > JWT Keys > Legacy JWT secret) **before**
  migration 07 is run. Without the JWT secret, everyone must sign in again
  after each API restart.
- Reset any account's password from the server:
  `cd api && .venv/Scripts/python.exe -m scripts.admin.set_password someone@agency.org`
- `POST /drone/telemetry` also accepts `X-Device-Key: <DRONE_INGEST_KEY>` for drone bridges.

### Demo mode

`VITE_DEMO_MODE=true` (web, `.env`) and `DEMO_MODE=true` (API, `api/.env`) turn
on the built-in demo accounts and the mock incidents, detections and drones,
for presentations. **Leave both off for a real deployment** such as an LDRRMO
pilot: demo passwords are published in this README, and mock incidents would
sit beside real ones. The Android app is always built without demo mode.

### Database migrations

Run each file in [supabase/migrations/](supabase/migrations/) **in order** in the
Supabase SQL editor. They are plain SQL — there is no migration tool. The live
schema is whatever Supabase has; [docs/data-dictionary.md](docs/data-dictionary.md)
describes it.

## Android app (Field Responders)

The Field Responder side also ships as an installable Android app (Capacitor),
so responders don't need Expo Go or a browser. It contains only sign-in and
the Field Responder screens; other roles are signed out and sent to the website.

```bash
npm run android:apk   # builds dist/ with .env.mobile, syncs, runs Gradle
# -> android/app/build/outputs/apk/debug/app-debug.apk
```

- Needs Android Studio's bundled JDK 17: `JAVA_HOME="C:/Program Files/Android/Android Studio/jbr"`,
  plus `android/local.properties` with `sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk`.
- `.env.mobile` sets the API address the phone uses. `127.0.0.1` means the phone
  itself, so use the laptop's Wi-Fi IP (or a hosted/tunnelled URL) and rebuild when it changes.
- Run the API with `--host 0.0.0.0` so the phone can reach it, on the same Wi-Fi.

## AI models

| Model | File | Trained on | Used for |
|---|---|---|---|
| Person detector | `models/victim_best.pt` (+ `victim_fast.onnx`) | VisDrone | finding people; a separate casualty check (posture + stillness) decides who is a casualty |
| Damage classifier | `models/damage_best.pt/.onnx` | AIDER + demo clips | labelling a frame as fire / flood / structural / no damage |
| Fire/smoke detector | `models/fire_best.pt/.onnx` | D-Fire | boxes around fire and smoke |

Training and evaluation scripts are in [api/scripts/training/](api/scripts/training/)
and run in a separate GPU venv (`api/.venv-train`, CUDA PyTorch). Each script's
header explains its data sources and usage. Outputs go to `api/runs/`; a model
only replaces one in `api/models/` after it beats it on the evaluation script.

## Demo accounts

Only with demo mode on (see above). All use password `password123`. Demo
accounts are local mock logins — they cannot register drones or add personnel,
and nothing they create is saved.

| Role | Email |
|---|---|
| System Admin | admin@rescueeye.io (demo mode; the real System Admin account of the same email needs its password set with `set_password`) |
| Agency Admin | agencyadmin@rescueeye.io |
| Command Staff | commandstaff@rescueeye.io |
| Field Responder | responder@rescueeye.io |

More guides: [docs/SUPABASE_INTEGRATION.md](docs/SUPABASE_INTEGRATION.md),
[docs/DATABASE_MIGRATION_GUIDE.md](docs/DATABASE_MIGRATION_GUIDE.md).
