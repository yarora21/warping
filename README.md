# Northstar — Policy Assignment System

A single-company take-home implementation with a fictional team. The MVP will connect employee information and assignment rules to dated, explainable policy assignments.



## Run locally

Requires Docker with Compose. Ports default to 5180 (web) and 8010 (API); this project uses its own `warping-mvp` Compose name and database volume.

```sh
make up
make seed
```

Open [the workspace](http://localhost:5180) or [API documentation](http://localhost:8010/docs). The first build downloads dependencies. Migrations run before API startup; seeds are explicit and never run automatically. Before seeding, the app displays an empty directory/catalog.

The demo date defaults to **September 12, 2026**. Optional settings are listed in [.env.example](.env.example); create a local `.env` to override them. Set `APP_TODAY=` to use the current date in `COMPANY_TIMEZONE`. Effective dates remain date-only strings; changing the clock does not rewrite existing fixtures. Seed rows are inserted by stable IDs and never overwrite existing logical records.

```sh
make test     # Focused PostgreSQL checks, rolled back after each test
make logs     # Recent API/web logs
make down     # Stop containers; preserve database volume
```

Do not use `docker compose down -v` unless you intend to erase this demo database. Normal rebuilds and restarts retain it. No authentication is implemented; the app binds to localhost and uses a clearly identified fictional HR actor. This is a local demo, not a production deployment.

## Frontend development

With Node 22 and the API running:

```sh
cd frontend
npm ci
npm run types
npm run dev
```

The Vite server proxies `/api` to localhost:8010. The production Compose web container serves built assets and proxies to the API internally. If changing the API port for development, update the type-generation URL and Vite proxy accordingly.

`make types` regenerates the checked-in TypeScript contract from FastAPI OpenAPI. `make check` runs TypeScript checking and a production frontend build. Python dependencies are fully frozen in `backend/requirements.lock`, with direct requirements in `requirements.in`; JavaScript dependencies use `package-lock.json`.

## Structure

```text
backend/
  app/clock.py          Shared date source
  app/database.py       SQLAlchemy engine
  app/queries.py        Explicit, batched read queries
  app/schemas.py        Typed API responses / generated frontend contract
  app/seed.py           Additive fictional fixtures
  app/main.py           HTTP routes
  migrations/          Versioned SQL, including temporal constraints
  tests/               Small database-focused suite
frontend/src/          React screens, styles, API client and generated types
docs/                  Architecture and human walkthrough
```

The initial data layer uses SQLAlchemy connections with explicit parameterized SQL. This avoids maintaining duplicate ORM models just for a small read surface. The migration is the source of truth for database constraints. New resolver modules will consume typed snapshots rather than HTTP requests or database state directly.


