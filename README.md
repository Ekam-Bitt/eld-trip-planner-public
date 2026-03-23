# ELD Trip Planner Platform

[![CI Build](https://img.shields.io/github/actions/workflow/status/Ekam-Bitt/eld-trip-planner-public/ci.yml?branch=main&style=for-the-badge)](https://github.com/Ekam-Bitt/eld-trip-planner-public/actions/workflows/ci.yml)
![Status: Production](https://img.shields.io/badge/Status-Production--Ready-success?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.1-092E20?style=for-the-badge&logo=django)
![React](https://img.shields.io/badge/React-18.3-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-5.0-646CFF?style=for-the-badge&logo=vite&logoColor=white)
![Vercel](https://img.shields.io/badge/Vercel-Deployed-000000?style=for-the-badge&logo=vercel)
![Render](https://img.shields.io/badge/Render-Deployed-46E3B7?style=for-the-badge&logo=render&logoColor=white)

🚀 **Live Demo:** [https://eld-trip-planner-kohl.vercel.app/](https://eld-trip-planner-kohl.vercel.app/)

A production-ready, industry-standard monorepo for generating FMCSA-compliant driver daily logs, enforcing Hours of Service (HOS) recap compliance, and planning trips. This platform combines a deeply optimized Django backend with a blazingly fast React + Vite frontend.

## 🌟 Key Features

- **HOS Compliance Engine**: Robust backend calculation of daily limits, cycle caps (70-hour / 8-day), and restart streaks.
- **Automated Log Generation**: Dynamically rendering complex, multi-day FMCSA-compliant logbooks to SVG and PDF using CairoSVG.
- **Intelligent Trip Planning**: Calculates distance, routes, and rest stops seamlessly utilizing OpenStreetMap routing parameters.
- **Driver-First UX**: Locked onboarding profiles ensure consistent carrier, terminal, and equipment details across logs without redundant data entry.
- **Secure Architecture**: RESTful endpoints protected by robust cross-origin authenticated session management.

## 🏗️ Architecture

The repository uses a clear separation of concerns under a standard monorepo design:

```text
eld-adv/
├── apps/
│   ├── api/                  # Django backend + core compliance & trip planning modules
│   └── web/                  # React + Tailwind frontend built with Vite
├── assets/
│   └── templates/            # Frozen FMCSA SVG log templates
└── artifacts/
    ├── reports/              # Per-record generated SVG/PDF artifacts
    └── latest/               # Latest generated compatibility outputs
```

## 🚀 Quick Start (Local Development)

The repository provides a streamlined `Makefile` interface for rapid local provisioning.

```bash
git clone <repository_url> && cd eld-trip-planner-public
make setup
make dev
```
Navigate to [http://127.0.0.1:5173](http://127.0.0.1:5173) to view the application in strict-port UI mode. The backend runs concurrently on HTTP port `8000` with requests automatically proxied by Vite.

### Manual Setup (Without Make)

**Backend (Django)**
```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

**Frontend (React)**
```bash
cd apps/web
npm install
npm run dev
```

## 🌍 Production Deployment

The project is natively architected for split-tier serverless and instance execution.

- **Frontend (Vercel)**: Ensure Vercel build configuration executes `npm run build` within the `/apps/web` root directory. Provide the `VITE_API_BASE_URL` pointing strictly to your live API instance.
- **Backend (Render)**: Utilizes a native Python environment (`env: python`). A declarative `render.yaml` infrastructure-as-code file automates zero-downtime backend deployments alongside automated database migrations.

## 📡 API Reference

A highly decoupled REST architecture orchestrates the workflows:
- `POST /api/auth/signup` / `POST /api/auth/login` / `POST /api/auth/logout`
- `PUT /api/profile` - Locks in permanent carrier/onboarding details
- `POST /api/trips/plan` - Computes and returns structured route definitions
- `POST /api/trips/generate` - Produces and persists the SVG/PDF assets to the internal file system
- `GET /api/logs/{id}/svg` / `GET /api/logs/{id}/pdf` - Emits `FileResponse` binaries for reporting endpoints

## 🛠️ Verification & Quality Assurance

Ensure codebase strictness and continuous integration checks before committing:

```bash
make test        # Ensure comprehensive unit test passthrough
make api-check   # Validate Django integrity and code linters
make build       # Build optimized React production bundles 
```
