# Oxane AI-Assisted Onboarding Demo

A demo workbench that takes a fictional asset-based finance facility from a raw document pack to approved, platform-ready data. All documents and data are synthetic. It is not connected to Panorama.

The build plan is in [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md).

## Run it

Requires Docker Desktop.

```bash
docker compose up --build
```

| Service | Address |
|---|---|
| Workbench | http://localhost:5180 |
| Design system | http://localhost:5180/design |
| API docs | http://localhost:8010/docs |
| PostgreSQL | localhost:5546 |

To use different ports, copy `.env.example` to `.env` and change them.

## Check it

```bash
docker compose exec web npm run lint
```

```bash
docker compose exec web npm run typecheck
```

```bash
docker compose exec web npm test
```

```bash
docker compose exec api ruff check .
```

```bash
docker compose exec api pytest
```

## Layout

| Path | Contents |
|---|---|
| `apps/web` | React workbench |
| `services/api` | FastAPI service and database migrations |
| `deal-kit` | `deal.yaml`, the single source of truth for the demo deal |
| `docs` | Development plan |
