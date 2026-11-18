# CCR Backend

Backend services for Climate Guard AI (banking climate-risk platform).

**Status:** development. Banking data (organizations, collaterals, valuations, CSV import)
exists. There is **no login yet**, and no climate-risk calculations.

## What exists

- `GET /api/v1/health`: app status plus a real database check (200 healthy, 503 if the database is down).
- Organizations, collaterals (create, read, partial update, archive, restore) and valuations.
- CSV import for collaterals: preview (no writes) and execution (one transaction).
- Alembic migrations, Docker Compose (API + PostgreSQL/PostGIS), automated tests.

## Development routes (no login)

The routes under `/api/v1/organizations` have **no authentication**. They are OFF by default.
They only run when `ENABLE_DEV_ROUTES=true`, and never when `ENVIRONMENT=production`.
Do not expose a server with these routes enabled to the internet.

## Run with Docker

1. Copy `.env.example` to `.env` and set a strong `POSTGRES_PASSWORD`
   (use the same password inside `DATABASE_URL`).
2. From this folder: `docker compose up --build`
3. Open http://localhost:8000/api/v1/health
4. Interactive API docs (not available in production): http://localhost:8000/docs

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
    models/          database tables
    schemas/         request and response shapes
    services/        business logic (CSV import)
    api/v1/          API routes
  migrations/        database migrations (Alembic)
  tests/             automated tests
```

## Rules for this project

- Synthetic data must always be labeled as synthetic.
- Exposed collateral value is not the same as financial loss.
- No regulatory compliance claim is made until the official requirements are verified.

## Roadmap

Authentication and roles, climate hazard data, risk engine, financial exposure,
frontend integration, deployment.
