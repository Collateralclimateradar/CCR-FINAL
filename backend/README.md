# CCR Backend

Backend services for Climate Guard AI.

**Status: Phase 1 (foundation).** The backend starts, connects to a PostgreSQL/PostGIS
database, and reports its health. No climate-risk features exist yet.

## What exists

- `GET /api/v1/health` - reports app status and checks the database for real.
  Returns HTTP 200 when healthy and HTTP 503 when the database is unreachable.
- Settings read from environment variables (no passwords in code).
- Database connection (SQLAlchemy) and migration setup (Alembic, no tables yet).
- Docker and Docker Compose files (API + PostGIS database).
- Automated tests that do not need a real database.

## Run with Docker

1. Copy `.env.example` to `.env` and set a strong `POSTGRES_PASSWORD`
   (use the same password inside `DATABASE_URL`).
2. From this folder: `docker compose up --build`
3. Open http://localhost:8000/api/v1/health
4. Interactive API docs (development only): http://localhost:8000/docs

## Run the tests

```
pip install -r requirements-dev.txt
pytest
```

## Folder layout

```
backend/
  ccr/
    main.py          application entry point
    core/            settings and logging
    db/              database connection and base class for tables
    api/v1/          version 1 of the API (health check so far)
  migrations/        database migrations (Alembic)
  tests/             automated tests
```

## Rules for this project

- Synthetic data must always be labeled as synthetic.
- Exposed collateral value is not the same as financial loss.
- No regulatory compliance claim is made until the official requirements are verified.

## Roadmap

Phase 2 banking data, Phase 3 geospatial, Phase 4 climate risk engine,
Phase 5 financial exposure, Phase 6 security, Phase 7 frontend integration,
Phase 8 testing and deployment.
Tests run automatically on GitHub Actions.

