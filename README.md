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

## Build the deal pack

The 8-file document pack and the answer key are generated from `deal-kit/deal.yaml` into `deal-kit/output/`. The same seed always gives byte-identical files, and `deal-kit/pack.manifest.json` records their hashes.

```bash
docker compose run --rm deal-kit python -m dealkit.build
```

Check the pack with a script that shares no code with the generators:

```bash
docker compose run --rm deal-kit python -m dealkit.verify
```

```bash
docker compose run --rm deal-kit pytest
```

The answer key is for scoring only. The pipeline must never read `deal-kit/output/answer-key/`.

## Record a pipeline run

The workbench shows labelled seed data until a run exists. Recording needs a model key once. After that, replay works with no key and no network.

1. Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. For Claude on Microsoft Foundry, set `LLM_PROVIDER=foundry` and the two Foundry values instead. Git ignores `.env`.
2. Recreate the API container so it picks up the key.

```bash
docker compose up -d --force-recreate --no-deps api
```

3. Record the run. Responses are saved to `fixtures/llm` and the output to `fixtures/run`.

```bash
docker compose exec api python -m app.pipeline.run --mode record
```

4. Check that replay reproduces it without calling the model.

```bash
docker compose exec api python -m app.pipeline.run --mode replay
```

## Test the engine

Build the deal pack first, because the tests compare the engine with the answer key.

```bash
docker compose run --rm engine pytest
```

## Layout

| Path | Contents |
|---|---|
| `apps/web` | React workbench |
| `services/api` | FastAPI service, AI pipeline and database migrations |
| `fixtures` | Recorded model responses and pipeline output |
| `deal-kit` | `deal.yaml`, the document generators, the answer key and the independent checker |
| `packages/engine` | Deterministic rules engine, borrowing base, reconciliation and covenants |
| `docs` | Development plan |
