# Oxane AI-Assisted Onboarding and Monitoring Demos

One workbench for two of Oxane's RFP use cases. All documents and data are synthetic. It is not connected to Panorama.

- **Onboarding** (use case 1) takes a fictional asset-based finance facility from a raw document pack to approved, platform-ready data, with the pitch brief's harder cases worked beside each step: nested definitions, the client's own model and the query cycle, the configuration workbook, a backbook load and independent QC before release. Build plan: [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md).
- **Monitoring** (use case 2, at `/monitoring`) runs the May 2026 cycle for two clients and four facilities, along the pitch brief's seven steps: expect and receive, map and ingest, validate, review and resolve, calculate and report (with a lender Excel workbook and an independent QC comparison), monitor and alert (headroom, early warnings, client self-service alerts), and the weekly status call. One client, Thornbury Bank, does not permit AI, so its CLO warehouse runs on code checks only. Build plan: [docs/MONITORING_PLAN.md](docs/MONITORING_PLAN.md).

The two share one facility record, rules engine, event log and workbench; the switch in the top bar moves between them.

## Run it

Requires Docker Desktop.

```bash
docker compose up --build
```

| Service | Address |
|---|---|
| Workbench | http://localhost:5180 |
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

## Run the onboarding casework

The casework sits around the onboarding pack, on screens beside the steps they belong to. `python -m dealkit.build` also generates its inputs into `deal-kit/output/casework/` (Calderwood's own borrowing base model, the domain team's independent QC workbook, four backbook tapes) and their key into `deal-kit/output/casework-key/`, all in `pack.manifest.json`. The run reads the recorded onboarding run and `services/api/app/casework/casework.yaml` (query log and timeline, QC resolutions, backbook batch, the scorecard's stated assumptions), never a key. A recording cost US$0.79; responses go to `fixtures/llm-casework`, output to `fixtures/casework`.

```bash
docker compose exec api python -m app.casework.run --mode replay
```

| Screen | Scenario | Brief step or measure |
|---|---|---|
| Terms › Definitions | Borrowing Base and Delinquency Ratio traced through 23 defined terms, sections and schedules, two amended by Amendment No. 1; every quote found on its page; each term's value worked out by the engine and the borrowing base reconciled to the cent; the Credit and Collection Policy flagged as not in the pack | 2 Interpret: nested definitions |
| Exceptions › Client model | Calderwood's template v3.2 against the agreement: stale advance rate (+US$1.48m borrowing base), concentration limits on total pool (+US$157k), dealer codes not combined (+US$375k), sub-600 band at 600 and below, "30+ days" boundary, no-score obligors (agreement silent) | 1 Receive (client model and reporting requirements), 3 Clarify |
| Exceptions › Query tracker | Nine queries with raised, sent, answered and closed times; answers flow into the configuration | 3 Clarify; elapsed time split from client waiting |
| Rules › Configuration | Field map, rules and thresholds (each checked against the figure in its verified source), report lines in the client's format, client conventions; `.xlsx` export with source notes, provisional until approval, QC and release | 4 Codify, 6 Configure |
| Mapping › Backbook | Four existing deals on Bramble's stored mapping: one clean, a renamed column, an extra column with blank days past due, servicer status codes; each suggestion checked against the tape | 5 Map and load |
| Approve › QC and release | Independent QC workbook: rounding, sign, per cent as decimal, blank against dash, and two genuine variances traced to the loans that explain them; report provisional until each is resolved and a second analyst releases it | 7 QC and release |
| Scorecard | Field-level accuracy against expert-verified records, material errors and omissions, exception rate, hours per onboarding by deal type, elapsed time split from client waiting, cost per onboarding, share of values linked to source, capacity released; measured and assumed in separate columns | Measures (5b) |

Endpoints: `GET /api/casework`, `GET /api/casework/config-workbook.xlsx`, `GET /api/casework/files/{name}`. Session events `send-query`, `record-answer`, `resolve-variance`, `accept-backbook` (preparer) and `release-report` (reviewer, four-eyes) continue after the load file is approved.

The onboarding cases list (`/cases`, `GET /api/cases`) holds case 0412, its four backbook deals and ten other cases across five clients and deal types. The other cases are generated at summary level by `deal-kit/dealkit/casework/pipeline.py` from the `pipeline` section of `deal-kit/casework.yaml` into `output/casework/pipeline/cases.json`; case 0412 and the backbook deals take their stage and counts from the live session. Walkthrough mode (numbered steps, `[` and `]`, next-step buttons) is off by default; turn it on from the header or with `?presenter=1`.

## Run the monitoring cycle

The cycle kit generates the four facilities' May submissions (Bramble, Northmoor and Kestrel for Calderwood Bank; the Larkspur CLO warehouse for Thornbury Bank), three months of Northmoor tapes, Larkspur's April and May collateral reports and bid files, the domain team's independent QC workbooks and the cycle answer key from `deal-kit/cycle.yaml`, building on Bramble's April tape from `deal.yaml`. `deal-kit/cycle.manifest.json` records the hashes, and `docker compose up` builds it if missing. Running the deal-kit tests rebuilds `deal-kit/output`, so build the cycle again afterwards.

```bash
docker compose run --rm deal-kit python -m dealkit.cycle.build
```

The cycle reads `services/api/app/monitoring/portfolio.yaml` (clients and their policies, the facility record, validation rule sets, the inbox log and the scorecard's stated assumptions) and the onboarding run, never the answer key. Code computes every number; the model reads documents, maps new tape columns, explains a prior-period change from the documents, suggests triage outcomes, turns a client's alert request into a rule and drafts the packs' and status brief's words. Every figure it reads must be found, quoted, in its document, and every figure in drafted text is a `{{placeholder}}` filled by code. Every model call goes through its client's guarded gateway, which refuses any call for, or carrying data of, a client that does not permit AI. A full recording costs about US$0.47; responses go to `fixtures/llm-cycle` and the output to `fixtures/cycle`.

```bash
docker compose exec api python -m app.monitoring.cycle --mode record
```

```bash
docker compose exec api python -m app.monitoring.cycle --mode replay
```

A captioned walkthrough video of the cycle is recorded the same way as the onboarding one, against a production build served by `demo-video/serve.mjs`:

```bash
node demo-video/record-monitoring.mjs && node demo-video/assemble.mjs Monitoring_Workbench_Demo.mp4
```

The scorecard (`GET /api/monitoring/scorecard`) is the only code that reads the cycle key. It reports the brief's section 5b measures by name, with measured results apart from stated assumptions: 29 loaded and reconciled values, the twelve planted issues (M1 to M12) and their outcomes, and the five noise items that must stay logged.

Other monitoring endpoints: `GET /api/monitoring/workbook/{facility}.xlsx` (the lender workbook with live formulas, marked provisional until released) and `POST /api/monitoring/alerts/draft` (a client's alert request turned into a checked, back-tested rule; in replay only the three example requests are recorded). With sign-in on, `SENIOR_USERS` names the third approval level.

The walkthrough video scripts in `demo-video/` predate the brief work (new steps, approval levels) and need updating before the next recording.

## Private Credit Ontology

`services/api/app/pipeline/private_credit_ontology.yaml` defines the business concepts of private lending: what each means, the form its value takes, how concepts relate, and which facility terms and tape fields belong to each. It is layered:

| Layer | Builds on | Holds |
| --- | --- | --- |
| Private credit | | What every facility has: lender, agent, borrower, sponsor, commitment, advances, availability, pricing, covenants, triggers, events of default, reporting, alerts |
| Asset-based finance | Private credit | Lending against a pool: receivables, obligors, servicer, eligibility, concentration, advance rate, reserve, borrowing base and its certificate |
| Auto loans | Asset-based finance | The auto loan, its financed vehicle and its dealer |

This facility uses all three. Direct lending, real estate debt and NAV lending are reserved as extension points on the core. Term extraction, tape mapping and rule drafting are grounded in it. The model must cite the concept IDs it relied on, and code checks every answer against it:

- A term citing a concept it was not given, or a value not in its concept's form (an advance rate that is not a percentage, say), drops to low confidence with the reason.
- A tape column whose concept disagrees with the ontology's is held for review.
- A rule draft citing a concept it was not given stops the run.

The workbench shows each value's concept on the Terms, Mapping and Rules screens (with its layer on Terms), and `GET /api/ontology` returns the whole ontology.

## Controls

The session is an append-only log in PostgreSQL. A database trigger refuses updates and deletes, and each event carries the hash of the one before it. The API enforces four-eyes approval, so a preparer cannot approve their own case. The load file exists only after approval, and "Reset the demo" starts a new session without deleting the old one.

Sign-in arrives with Azure in phase 7. Until then the analyst name is whatever the client sends, so the API limits it to the two demo roles.

## Rehearse

The browser suite covers the full path, every screen, failure drills and keyboard control. Run the `npm install` line once.

```bash
docker compose --profile tools run --rm e2e npm install
```

```bash
docker compose --profile tools run --rm e2e npx playwright test --project=stage
```

Record the fallback videos into `tests/e2e/fallback-recordings`:

```bash
docker compose --profile tools run --rm e2e npx playwright test --project=fallback
```

To measure accuracy across fresh model runs, which needs a key and costs about US$1 a run:

```bash
docker compose exec api python -m app.evaluate --runs 3
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
