# API Overview

The Sydney Bus GTFS API exposes a role-aware REST interface for importing and exploring Transport for NSW bus schedule data.

## Core Capabilities

- Health and service discovery endpoints.
- Admin user management with enabled/disabled accounts.
- Role-based access for Admin, Planner, and Commuter users.
- GTFS schedule import from the Transport for NSW API.
- Route, trip, stop, agency, and stop-search endpoints backed by SQLite.
- Per-user favourite routes.
- PNG route visualisation and CSV export for favourite routes.
- Swagger documentation at `/docs/`.

## Demo Users

Use the `X-User` request header with one of these seeded users:

| User | Role |
| --- | --- |
| `admin` | Admin |
| `planner` | Planner |
| `commuter` | Commuter |

## Important Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check service status |
| `GET` | `/admin/users` | List users |
| `POST` | `/admin/users` | Create Planner or Commuter users |
| `POST` | `/gtfs/import/{agency_id}` | Import GTFS schedule data |
| `GET` | `/data/route/{route_id}` | Fetch route metadata |
| `GET` | `/data/trip/{trip_id}` | Fetch trip metadata |
| `GET` | `/data/stop/{stop_id}` | Fetch stop metadata |
| `GET` | `/data/search/stops?name={query}` | Fuzzy stop search |
| `GET` | `/favourites/` | List favourite routes |
| `POST` | `/favourites/{route_id}` | Add a favourite route |
| `GET` | `/visualisation/favourites/map` | Render favourite routes as PNG |
| `GET` | `/visualisation/favourites/export` | Export favourite routes as CSV |
