## ELD Trip Planner

Monorepo for planning and visualizing ELD trips. Backend is a Django REST API with JWT auth; frontend is a React + TypeScript app (Vite) that renders routes and guidance.

### Features

- Authentication with JWT (signup, login, logout, profile)
- Trip planning via Mapbox Directions with polyline decoding to GeoJSON
- Route polyline rendering and step-by-step directions in the UI
- Fuel stop estimation along the route
- API schema and Swagger UI

---

## Repository Layout

```
backend/       # Django, DRF, apps: drivers, trips, logs
frontend/      # React + TypeScript (Vite)
infra/         # docker-compose for local dev
```

---

## Tech Stack

- Backend: Django 5, DRF, drf-spectacular, SimpleJWT, SQLite (dev)
- Frontend: React 19 + TypeScript, Vite
- Infra: Docker, Docker Compose

---

## Quick Start (Docker)

1. Prerequisites: Docker Desktop running.

2. Create `infra/.env` and add a Fernet key used to encrypt driver Mapbox tokens at rest:

```env
MAPBOX_ENC_KEY=<your_fernet_key>
```

Generate a key:

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

3. Start services:

```bash
cd infra
docker compose up -d --build
```

4. Open:

- API: `http://localhost:8000/`
- API Docs (Swagger): `http://localhost:8000/api/docs/`
- Frontend: `http://localhost:5173/`

Troubleshooting rebuild:

```bash
cd infra
docker compose stop frontend && docker compose rm -f frontend
docker volume prune -f
docker compose up -d --build
```

---

## Quick Start (Local Dev, no Docker)

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export MAPBOX_ENC_KEY=<your_fernet_key>
python manage.py migrate
python manage.py runserver
```

Frontend:

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

---

## Environment Variables

- Backend

  - `MAPBOX_ENC_KEY` (required): base64 Fernet key; encrypts stored Mapbox token
  - `DJANGO_SETTINGS_MODULE` (dev default: `core.settings`)
  - `DEBUG` (`1` in dev compose)

- Frontend
  - `VITE_API_URL` (compose default: `http://localhost:8000`)

Secrets policy: do not commit secrets; use `.env` files locally and CI/hosted secrets in pipelines.

---

## API Overview

Auth (JWT):

- POST `/api/drivers/signup/`
- POST `/api/drivers/login/` → `{ access, refresh }`
- POST `/api/drivers/logout/` with `{ refresh }`
- GET `/api/drivers/me/` (requires `Authorization: Bearer <access>`)

Driver Mapbox token (encrypted at rest):

```bash
curl -X PUT \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"mapbox_api_key": "<mapbox_access_token>"}' \
  http://localhost:8000/api/drivers/profile/
```

Trips:

- POST `/api/trips/` → create + compute a trip
- GET `/api/trips/` → list trips
- GET `/api/trips/{id}/` → detail: `route_geometry` (GeoJSON LineString), `route_metadata`

Example create request:

```bash
ACCESS=<your_jwt_access>
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{
    "current_location": "-118.2437,34.0522",
    "pickup_location": "-115.1398,36.1699",
    "dropoff_location": "-104.9903,39.7392"
  }' \
  http://localhost:8000/api/trips/
```

Swagger UI: `http://localhost:8000/api/docs/` (OpenAPI at `/api/schema/`).

---

## Frontend Usage

1. Login from the app (JWT stored in memory).
2. Provide your Mapbox access token in Profile Settings when prompted.
3. Use Trip Planner to create a route; the map will display the polyline and key markers; the sidebar shows turn-by-turn steps.

---

## Linting & Testing

- Backend lint: `flake8 backend`, `black --check backend`, `isort --check-only backend`
- Backend tests: `cd backend && python manage.py test`
- Frontend lint: `cd frontend && npm run lint`

Target quality (repo policy): typed code, lint clean, and ≥70% coverage for non-trivial features.

---

## Development Workflow

- Branch naming: `phase/{n}-{short-description}` (e.g., `phase/2-trip-planning`)
- Commit style: Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`)
- Pull Requests:
  - Required checks: lint, test, build
  - Required approvals: 1; auto-merge disabled
  - Include run instructions and tests list in PR description

CI: GitHub Actions workflows run lint/test/build for backend and frontend. Use repo/organization secrets for environment variables.

---

## Deployment

Images are built for production and can be pushed to GHCR using the `deploy_to_staging` workflow.

- Backend image: `ghcr.io/<owner>/ELD-backend`
- Frontend image: `ghcr.io/<owner>/ELD-frontend`

### Health Check

- `GET /healthz` should return `200 ok` when backend is healthy.

### Build & Push (manual)

From repo root:

```bash
# Backend
docker build -f backend/Dockerfile -t ghcr.io/<owner>/ELD-backend:local .
# Frontend
docker build -f frontend/Dockerfile -t ghcr.io/<owner>/ELD-frontend:local .
```

### Staging Compose

Use `infra/docker-compose.prod.yml` to run images locally in production mode:

```bash
docker compose -f infra/docker-compose.prod.yml up -d
```

### GitHub Actions

- `deploy_to_staging` (`.github/workflows/deploy.yml`): builds and pushes Docker images to GHCR under the repo.
- `security_scans` (`.github/workflows/security.yml`): runs `pip-audit` and `npm audit` on a schedule.

### Rollback Procedure

1. Identify last known good image tag in GHCR (e.g., `sha-<commit>`).
2. Update deployment to use the previous tag.
3. Restart services (Kubernetes: rollout restart; Docker Compose: `docker compose pull && docker compose up -d`).
4. Verify `GET /healthz` and basic flows.

### Environment & Secrets

- Do not commit secrets. Configure:
  - `MAPBOX_ENC_KEY` (backend) as a secret/variable in the environment.
  - Frontend `VITE_API_URL` pointing to the API ingress/URL.

---
## Troubleshooting

- Backend says `MAPBOX_ENC_KEY is not set` → set it in `infra/.env` (Docker) or export in your shell.
- Mapbox call fails with a network error → check VPN/Internet; retry; ensure token is valid.
- Frontend cannot reach API → verify `VITE_API_URL` and CORS allows `http://localhost:5173`.

---

## License

TBD.
