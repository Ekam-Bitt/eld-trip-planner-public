# ELD Trip & HOS Compliance System

A full‑stack web application that helps truck drivers plan trips, stay FMCSA Hours of Service (HOS) compliant, and generate shareable reports. Backend is a Django REST API with JWT auth; frontend is a React + TypeScript (Vite) app that renders routes and guidance.

### Live App
[ekam-bitt.github.io/eld-trip-planner-public/](https://ekam-bitt.github.io/eld-trip-planner-public/)

### Features

- **Authentication (JWT)**: Signup, login, logout, and driver profile management
- **Trip Planning**: Compute routes via Mapbox Directions; render polyline and key markers
- **Search**: Suggest and retrieve places (Mapbox Search)
- **HOS Compliance**: Log events and compute daily summaries/violations
- **Inspections**: Record pre‑trip and post‑trip inspections
- **Reports**: Export trip PDFs and CSVs
- **Docs**: OpenAPI schema and Swagger UI

### Deployment Stack
- Frontend: Hosted on GitHub Pages
- Backend: Deployed via Render.com

---

## Technologies Used

### Frontend

- React 19 + TypeScript
- Vite
- MapLibre GL (OpenStreetMap raster basemap)
- React Router
- TailwindCSS

### Backend

- Django 5 + Django REST Framework
- drf-spectacular (OpenAPI)
- djangorestframework-simplejwt (JWT auth)
- SQLite (dev)
- cryptography (Fernet) for encrypting driver Mapbox tokens at rest
- reportlab + WeasyPrint for PDF generation

### Infra

- Docker & Docker Compose (local dev and staging compose)

---

## Quick Start (Docker)

1. Prerequisite: Docker Desktop running.

2. Create `infra/.env` with a Fernet key used to encrypt driver Mapbox tokens stored by the backend:

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

## Configuration

### Environment Variables

- Backend
  - `MAPBOX_ENC_KEY` (required): base64 Fernet key; used to encrypt stored Mapbox tokens
  - `DJANGO_SETTINGS_MODULE` (default: `core.settings`)
  - `DEBUG` (`1` for local, `0` for prod)
- Frontend
  - `VITE_API_URL` (default in dev compose: `http://localhost:8000`)

Secrets policy: do not commit secrets. Use `.env` files locally and CI/hosted secrets in pipelines.

---

## Repository Layout

```
backend/       # Django (apps: drivers, trips, logs)
frontend/      # React + TypeScript (Vite)
infra/         # docker-compose for local and staging
```

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
  -d '{"mapbox_api_key": "<mapbox_public_token>"}' \
  http://localhost:8000/api/drivers/profile/
```

Trips:

- POST `/api/trips/` → create + compute a trip
- GET `/api/trips/` → list trips
- GET `/api/trips/{id}/` → detail includes `route_geometry` (GeoJSON LineString) and `route_metadata`
- GET `/api/trips/searchbox/suggest/?q=...&session_token=...&limit=5`
- GET `/api/trips/searchbox/retrieve/?id=...&session_token=...`

Logs & HOS:

- POST `/api/logs/` → create a log event
- GET `/api/logs/{trip_id}/` → list trip log events
- GET `/api/logs/{trip_id}/hos/` → HOS summary and violations
- GET `/api/logs/{trip_id}/daily/` → daily log list
- POST `/api/logs/{trip_id}/daily/submit/` → submit daily logs

Inspections:

- GET `/api/logs/{trip_id}/inspections/` → list inspections
- POST `/api/logs/inspections/` → create inspection

Reports:

- GET `/api/reports/trip/{trip_id}/pdf/`
- GET `/api/reports/trip/{trip_id}/csv/`

Health:

- GET `/healthz` → `200 ok`

Swagger UI: `http://localhost:8000/api/docs/` (OpenAPI at `/api/schema/`).

---

## Using the App

1. Sign up or log in from the frontend.
2. Open Profile Settings and paste your Mapbox Default public token (`pk.*`).
3. Plan a trip with pickup and dropoff; the map displays the route and key markers.
4. Add log events during the trip; review HOS summaries and violations.
5. Record pre/post‑trip inspections; export reports (PDF/CSV) as needed.

Note: The map basemap uses OpenStreetMap tiles (no key needed). Your Mapbox token is used by the backend for directions/search and is stored encrypted using your `MAPBOX_ENC_KEY`.

---

## Linting & Testing

- Backend lint: `flake8 backend`, `black --check backend`, `isort --check-only backend`
- Backend tests: `cd backend && python manage.py test`
- Frontend lint: `cd frontend && npm run lint`

Quality target: typed code, lint clean, and ≥70% coverage for non‑trivial features.

---

## Development Workflow

- Branch naming: `phase/{n}-{short-description}` (e.g., `phase/2-trip-planning`)
- Commit style: Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`)
- Pull Requests:
  - Required checks: lint, test, build
  - Required approvals: 1; auto‑merge disabled
  - Include run instructions and tests list in PR description

CI: GitHub Actions workflows can run lint/test/build for backend and frontend. Use organization secrets for environment variables.

---

## Deployment

Images can be built for production and pushed to a registry (e.g., GHCR).

- Backend image: `ghcr.io/<owner>/eld-backend`
- Frontend image: `ghcr.io/<owner>/eld-frontend`

### Deployed Environments

- Production
  - Frontend: `https://<your-prod-frontend-url>`
  - API base: `https://<your-prod-api-url>` or same-origin `/api`
  - Swagger UI: `https://<your-prod-api-url>/api/docs/`
  - Health: `https://<your-prod-api-url>/healthz`
- Staging
  - Frontend: `https://<your-staging-frontend-url>`
  - API base: `https://<your-staging-api-url>` or same-origin `/api`
  - Swagger UI: `https://<your-staging-api-url>/api/docs/`
  - Health: `https://<your-staging-api-url>/healthz`

Frontend config:
- Same-origin deploys (recommended): set `VITE_API_URL=/api` (as in `infra/docker-compose.prod.yml`).
- Split domains: set `VITE_API_URL` to your API base URL (e.g., `https://api.example.com`).

### Health Check

- `GET /healthz` should return `200 ok` when backend is healthy.

### Build & Run (local images)

```bash
# From repo root
# Backend
docker build -f backend/Dockerfile -t ghcr.io/<owner>/eld-backend:local .
# Frontend
docker build -f frontend/Dockerfile -t ghcr.io/<owner>/eld-frontend:local .
```

### Staging Compose

Use `infra/docker-compose.prod.yml` to run prebuilt images locally in production mode:

```bash
docker compose -f infra/docker-compose.prod.yml up -d
```

### Environment & Secrets

- Do not commit secrets. Configure:
  - `MAPBOX_ENC_KEY` (backend) as a secret/variable in the environment
  - Frontend `VITE_API_URL` pointing to the API ingress/URL

---

## Troubleshooting

- Backend says `MAPBOX_ENC_KEY is not set` → ensure it is set in `infra/.env` (Docker) or exported in your shell.
- Mapbox request fails → verify your `pk.*` token is valid; check connectivity.
- Frontend cannot reach API → verify `VITE_API_URL` and CORS allows `http://localhost:5173`.

---

## Contributing

1. Fork the repository
2. Create a feature branch:
   ```bash
   git checkout -b feature/short-description
   ```
3. Commit changes:
   ```bash
   git commit -m "feat: add <thing>"
   ```
4. Push branch and open a pull request

---

## License

Released under the MIT License. See [`LICENSE`](./LICENSE) for details.
