# Contributing

## Local Development

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and add a Transport for NSW API key if you need live GTFS imports.
4. Run tests with `pytest`.

## Code Quality

- Keep API responses JSON-first and documented in Swagger.
- Add or update tests when changing endpoint behaviour.
- Keep generated data, caches, local databases, and secrets out of Git.
