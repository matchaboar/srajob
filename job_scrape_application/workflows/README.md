Setup and Run

Prereqs
- Temporal server available (e.g., dev server at `localhost:7233`)
- Convex HTTP router running/deployed and reachable via `CONVEX_HTTP_URL`
- `uv` installed (Python 3.11+)

Environment
- `TEMPORAL_ADDRESS` (default `localhost:7233`)
- `TEMPORAL_NAMESPACE` (default `default`)
- `TEMPORAL_TASK_QUEUE` (default `scraper-task-queue`)
- `CONVEX_HTTP_URL` (required; on Convex Cloud use the `.convex.site` domain, e.g., `https://<deployment>.convex.site`)
- `FETCHFOX_API_KEY` (required)

Install deps
- uv sync

Run worker
- uv run python -m job_scrape_application.workflows.worker

Create/Update 12h schedule
- uv run python -m job_scrape_application.workflows.create_schedule

Health check (sites + jobs)
- Ensure `CONVEX_HTTP_URL` is set to your HTTP base (Convex Cloud uses the `.convex.site` domain)
- Run: `uv run python -m job_scrape_application.workflows.health_check`

Temporal: local DEV (Docker/Podman)
- Dev image build + run (Docker Compose): `docker compose -f docker/temporal/docker-compose.yml up -d`
- Podman helper (Windows-friendly):
  - Start + health check with timeouts: `pwsh docker/temporal/start-podman.ps1 -RunCheck -HealthCheckTimeoutSeconds 180 -BuildTimeoutSeconds 600`
  - Stop: `pwsh docker/temporal/stop-podman.ps1`
- UI: http://localhost:8233 (server on `localhost:7233`)
- Real-server Temporal check: `uv run python -m job_scrape_application.workflows.temporal_real_server_check`
  - Respects `TEMPORAL_ADDRESS` (default `localhost:7233`) and `TEMPORAL_NAMESPACE` (default `default`)
  - Requires `CONVEX_HTTP_URL`

One-liner test runner (PowerShell)
- Use `scripts/run-tests.ps1` for easy commands with built-in timeouts:
  - Start Temporal dev + check: `pwsh scripts/run-tests.ps1 temporal:start -RunCheck`
  - Stop Temporal dev: `pwsh scripts/run-tests.ps1 temporal:stop`
  - Ephemeral test env check: `pwsh scripts/run-tests.ps1 hc:ephemeral`
  - Real server check (requires Temporal dev or remote): `pwsh scripts/run-tests.ps1 hc:real`
  - Manual test: `pwsh scripts/run-tests.ps1 hc:manual`
  - Override timeouts: `-TimeoutSeconds 300`
  - Verbose podman build logs: `-VerboseBuild`

Seed sites (example)
- POST to `${CONVEX_HTTP_URL}/api/sites` with body:
  {"name":"Datadog SWE US","url":"https://careers.datadoghq.com/all-jobs/?s=software%20developer&region_Americas%5B0%5D=Americas","pattern":"https://careers.datadoghq.com/detail/**","enabled":true}
