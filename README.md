# Sydney Transit GTFS API

A production-style Flask-RESTX API for importing, querying, and visualising Sydney public transport schedule data from the Transport for NSW GTFS feed.

This portfolio project demonstrates backend API design, role-based access control, external data ingestion, SQLite persistence, automated testing, Swagger documentation, CSV export, and server-side route visualisation.

## Features

- REST API documented with Swagger UI at `/docs/`.
- Role-based workflows for Admin, Planner, and Commuter users.
- GTFS import pipeline for Transport for NSW bus schedules.
- SQLite-backed route, trip, stop, agency, and favourite-route data.
- Fuzzy stop search powered by RapidFuzz.
- Favourite route map rendering as PNG.
- Favourite route export as downloadable CSV.
- Automated pytest suite and GitHub Actions CI.

## Tech Stack

- Python
- Flask and Flask-RESTX
- SQLite
- Pandas
- Matplotlib
- RapidFuzz
- Pytest
- GitHub Actions

## Getting Started

### 1. Clone and Enter the Project

```bash
git clone https://github.com/Hrithik028/sydney-transit-gtfs-api.git
cd sydney-transit-gtfs-api
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Set `TRANSPORT_API_KEY` in `.env` if you want to import live GTFS data from Transport for NSW.

### 5. Run the API

```bash
python z5509844_api.py
```

Open the interactive API docs at:

```text
http://127.0.0.1:5000/docs/
```

## Demo Users

The application seeds three users on startup:

| Username | Role |
| --- | --- |
| `admin` | Admin |
| `planner` | Planner |
| `commuter` | Commuter |

Pass one of these values in the `X-User` header when using protected endpoints.

## Example Workflow

1. Check the service: `GET /health`
2. Authorize in Swagger with `X-User: admin`
3. Import data: `POST /gtfs/import/GSBC001`
4. Search stops: `GET /data/search/stops?name=Circular+Quay`
5. Add a favourite route: `POST /favourites/{route_id}`
6. Export favourites: `GET /visualisation/favourites/export`
7. Render map: `GET /visualisation/favourites/map`

## Testing

```bash
pytest
```

The test suite covers health checks, role-based access, user management, GTFS import validation, data lookup edge cases, favourites, exports, and Swagger availability.

## Repository Hygiene

The repository intentionally excludes:

- API keys and `.env` files.
- Local SQLite databases.
- Downloaded GTFS data.
- Generated CSV and PNG exports.
- Virtual environments and Python caches.

This keeps the GitHub repo lightweight, reproducible, and safe to share.

## Project Structure

```text
.
├── z5509844_api.py          # Flask-RESTX application
├── z5509844_tests.py        # Pytest coverage for API behaviour
├── requirements.txt         # Runtime and test dependencies
├── pytest.ini               # Test discovery configuration
├── docs/
│   └── API_OVERVIEW.md      # Endpoint and capability overview
├── .github/workflows/
│   └── ci.yml               # GitHub Actions test workflow
├── .env.example             # Public environment template
└── .gitignore               # Git ignore rules for generated/local files
```

## Resume Summary

Built a role-based Flask REST API for Sydney transit GTFS data with Transport for NSW integration, SQLite persistence, Swagger documentation, fuzzy search, CSV export, server-side route visualisation, pytest coverage, and CI automation.
