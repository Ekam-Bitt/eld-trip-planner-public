# HOS Driver Log Platform

Production-oriented monorepo for generating FMCSA-style driver daily logs, enforcing HOS recap compliance, and planning assessment-ready trips with a Django + React stack.

## Stack

- Backend: Django
- Frontend: React + Vite + Tailwind
- Storage: SQLite
- Rendering: SVG template fill + PDF export via CairoSVG
- Routing: OpenStreetMap geocoding/routing services with local fallbacks

## Repository Layout

```text
eld-adv/
  apps/
    api/                  # Django backend + shared planning/rendering modules
    web/                  # React + Tailwind frontend
  assets/
    templates/            # Frozen SVG templates
  artifacts/
    latest/               # Latest generated SVG/PDF (compatibility outputs)
    reports/              # Per-record generated SVG/PDF artifacts
  docs/
    assessment.md
```

## Core Features

- Driver-first authentication with sign up, login, and locked onboarding
- Backend-owned HOS recap and compliance calculation
- Timeline rendering into `<g id="timeline-events">` in the SVG dynamic layer
- Assessment-aligned trip planner:
  - Inputs: current location, pickup, dropoff, current cycle used hours
  - Outputs: route instructions, stop/rest plan, and multi-day generated log sheets
- Locked onboarding fields mapped from the PDF template: carrier name, office address, terminal address, and equipment numbers
- Secure per-record artifact access (`/api/logs/{id}/svg|pdf`)
- Focused frontend UX for sign up, onboarding, and trip generation

## Quick Start

```bash
cd /Users/ekambitt/Projects/eld-adv
make setup
make api
make web
```

Then open [http://127.0.0.1:5173](http://127.0.0.1:5173).

## Local Setup

### API

```bash
cd /Users/ekambitt/Projects/eld-adv/apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py check
python manage.py runserver 0.0.0.0:8000
```

### Web

```bash
cd /Users/ekambitt/Projects/eld-adv/apps/web
npm install
npm run dev
```

Optional API override:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

By default, the web dev server proxies `/api` to `http://127.0.0.1:8000`, so no CORS config is needed for local development.

## Makefile Shortcuts

```bash
cd /Users/ekambitt/Projects/eld-adv
make help
make setup
make api-setup
make api-check
make api-shell
make web-install
make api
make web
make test
make build
```

Open the frontend at `http://127.0.0.1:5173` (fixed host/port, strict port mode).

## Driver Flow

1. Create a driver account or sign in.
2. Complete the one-time onboarding fields:
   - Name of carrier
   - Main office address
   - Home terminal address
   - Truck / trailer numbers
3. Enter:
   - Current Location
   - Pickup Location
   - Dropoff Location
   - Current Cycle Used (hours)
4. Click **Plan Route + Stops** for route + stop instructions.
5. Click **Generate Multi-Day Logs** to create one SVG/PDF daily log per trip day.

The onboarding fields are locked after submission for the assessment flow. HOS recap history is derived by the backend rather than being entered manually.

## Project Practices

- Treat the backend as Django-only. There is no FastAPI runtime in the repo anymore.
- Keep one-time carrier fields in onboarding and do not ask for them again in the trip planner.
- Keep the assessment input surface narrow: current location, pickup, dropoff, and current cycle used hours.
- Prefer `make setup`, `make api`, `make web`, `make test`, and `make build` for routine local work.

## Trip APIs

- `POST /api/auth/signup`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/profile`
- `PUT /api/profile`
- `POST /api/trips/plan`
- `POST /api/trips/generate`
- `GET /api/logs/{id}/svg`
- `GET /api/logs/{id}/pdf`

## Environment Variables

- `DRIVER_LOG_TEMPLATE` (default: `assets/templates/driver-log-template.svg`)
- `DRIVER_LOG_DB_PATH` (default: `apps/api/data/driver_log.db`)
- `HOS_STRICT_COMPLIANCE`
- `AUTH_PBKDF2_ITERATIONS`
- `AUTH_SESSION_TTL_HOURS`
- `LOG_LEVEL`

## Verification

Backend checks:

```bash
cd /Users/ekambitt/Projects/eld-adv
make api-check
make test
```

Production build:

```bash
cd /Users/ekambitt/Projects/eld-adv
make build
```
