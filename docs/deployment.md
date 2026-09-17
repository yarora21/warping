# Deploy Northstar on Render and Neon

The root `Dockerfile` builds React and serves its static files from FastAPI. Render runs one free web service; Neon stores PostgreSQL data independently of the web container. The existing three-service local Compose setup remains available.

## Create the database

Create a project on Neon's **Free** plan with PostgreSQL 17. Choose a US East region near Render's Virginia region. Copy the **direct** database connection string, retaining its SSL parameters. The application accepts either `postgresql://` or `postgresql+psycopg://` and uses psycopg 3. Its migrations enable `btree_gist` for temporal exclusion constraints.

Keep the connection string in Render's environment settings. Do not commit it or include it in screenshots.

## Deploy the service

Push the application and deployment files to the GitHub branch you intend to deploy. In Render, create a **Blueprint** from that repository and branch. The root [render.yaml](../render.yaml) configures:

| Setting | Value |
| --- | --- |
| Runtime | Docker, root `Dockerfile` |
| Instance | Free |
| Region | Virginia |
| Health check | `/api/health` |
| `DATABASE_URL` | Enter the Neon connection string when prompted |
| `APP_TODAY` | `2026-09-12` for repeatable demo behavior |
| `COMPANY_TIMEZONE` | `America/New_York` |
| `SEED_DEMO_ON_EMPTY_DB` | `true` |

The startup script runs migrations, initializes fictional fixtures only when there are no employees, policies, or rules, then starts Uvicorn on Render's supplied `PORT`. Initialization uses the normal company transaction lock. Future restarts skip seeding once application data exists. Set the seed flag to `false` if you want an empty application instead. The local Compose setup still requires explicit `make seed`.

There is no separate frontend URL or CORS configuration: browser `/api` requests go to the same origin. The frontend mount comes after API routes, and unknown API paths or missing assets return errors rather than the app shell.

## Verify and operate

After Render reports a successful deployment:

1. Open `/api/health` and confirm `{"status":"ok"}`.
2. Manually open the root URL, review People/Policies/Assignments, preview a change, and save it.
3. Restart the service and confirm the saved change persists. Inspect startup logs for the message that automatic seeding was skipped.

Render's free service sleeps after 15 minutes without traffic; the next request can take about a minute to wake it. Open the demo ahead of a presentation. Free usage has limits; retain the free plans when creating resources. Render's free PostgreSQL expires after 30 days, which is why this setup uses Neon. See [Render free-service limits](https://render.com/docs/free) and [Neon plans](https://neon.com/pricing).

All users share one fictional company and can edit it: the app has no authentication. Do not load real employee information into this public demo. The database is external, so deploying an earlier application commit does not roll back its schema or data. Avoid resets and destructive migrations when recovering a failed deployment.

The single-service image keeps deployment small, but the UI and API share the same cold start. This is appropriate for a low-traffic reviewer demo.

## Reproduce the build locally

```sh
docker build -t northstar-deploy .
```

The image requires a reachable PostgreSQL database. Pass `DATABASE_URL` through a private environment file when running it. Browser testing remains manual; server routing and seed behavior are covered by the focused backend suite.
