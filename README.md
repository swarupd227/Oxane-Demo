# Oxane AI-Assisted Onboarding and Monitoring Demos

One workbench for two of Oxane's RFP use cases. All documents and data are synthetic. It is not connected to Panorama.

- **Onboarding** (use case 1) takes a fictional asset-based finance facility from a raw document pack to approved, platform-ready data, with the pitch brief's harder cases worked beside each step: nested definitions, the client's own model and the query cycle, the configuration workbook, a backbook load and independent QC before release. Build plan: [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md).
- **Monitoring** (use case 2, at `/monitoring`) runs the May 2026 cycle for two clients and four facilities, along the pitch brief's seven steps: expect and receive, map and ingest, validate, review and resolve, calculate and report (with a lender Excel workbook and an independent QC comparison), monitor and alert (headroom, early warnings, client self-service alerts), and the weekly status call. One client, Thornbury Bank, does not permit AI, so its CLO warehouse runs on code checks only. Build plan: [docs/MONITORING_PLAN.md](docs/MONITORING_PLAN.md).

The two share one facility record, rules engine, event log and workbench; the switch in the top bar moves between them.

## Run it

Requires Docker Desktop.

```bash
cp .env.example .env   # once: the API mounts this file (Settings › AI provider writes the key to it)
docker compose up --build
```

| Service | Address |
|---|---|
| Workbench | http://localhost:5180 |
| API docs | http://localhost:8010/docs |
| PostgreSQL | localhost:5546 |

To use different ports, change them in `.env`.

The Administrator (Alex Morgan) sets the model key at **Settings › AI provider**, with the access code. A key saved there is encrypted with `SETTINGS_ENCRYPTION_KEY` (a Fernet key; see `.env.example`) and is used from the next model call, ahead of `ANTHROPIC_API_KEY`. Locally, saving also writes the key to `.env`.

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

The cycle also carries the RFP review's three additions (`docs/PITCH_BRIEF_GAPS.md`): Ravenglass Direct Lending Fund I, a Calderwood back-leverage facility on 40 middle-market obligors (`app/monitoring/middle_market.py`); Wharfedale Infrastructure Partners III, a Thornbury subscription line run on code only (`subline.py`); and each facility's document schedule, Larkspur's daily feeds and the mapping library (`schedules.py`). The engine adds `directlending.py`, `fundfinance.py` and `feeds.py`. The scorecard scores M13 to M20 and N6 to N8 beside the original twelve and five. The review's model steps (obligor financials, the waiver notice, Ravenglass triage, pack and brief section) run their code fallback until recorded, are listed under `pending_recording` in the cycle and the agents' run log, and are recorded, capped at US$4, with:

```bash
docker compose exec api python -m app.monitoring.cycle --mode record --budget-usd 4
```

A captioned walkthrough video of the cycle is recorded the same way as the onboarding one, against a production build served by `demo-video/serve.mjs`:

```bash
node demo-video/record-monitoring.mjs && node demo-video/assemble.mjs Monitoring_Workbench_Demo.mp4
```

The scorecard (`GET /api/monitoring/scorecard`) is the only code that reads the cycle key. It reports the brief's section 5b measures by name, with measured results apart from stated assumptions: 29 loaded and reconciled values, the twelve planted issues (M1 to M12) and their outcomes, and the five noise items that must stay logged.

Other monitoring endpoints: `GET /api/monitoring/workbook/{facility}.xlsx` (the lender workbook with live formulas, marked provisional until released) and `POST /api/monitoring/alerts/draft` (a client's alert request turned into a checked, back-tested rule; in replay only the three example requests are recorded). With sign-in on, `SENIOR_USERS` names the third approval level.

The walkthrough video scripts in `demo-video/` predate the brief work (new steps, approval levels) and need updating before the next recording.

## New deals: create to monitor

Besides the two scripted scenarios, a user can run a new deal end to end: create a client, open an onboarding case, upload its agreement, amendments, loan tape (CSV or XLSX) and optionally the client's model, and take it through classification, terms, rules, tape mapping, validation, exceptions, independent QC, four-eyes approval and go-live. The live facility then receives monthly submissions: stored mapping reuse (AI only when the layout changes), validation, reconciliation against the prior period, triggers from the facility's own rule set, triage, a lender workbook, the client's approval levels and release. It also appears in the monitoring portfolio. Code: `services/api/app/deals/`, `apps/web/src/pages/deals/`.

The model reads, classifies, maps and drafts; code finds every quote on its page, checks every figure against its quote, validates rules against their clauses and computes every number. A client that does not permit AI gets no model calls: the analyst enters terms with page references and writes rules, and code checks each entry. The scripted scenarios always replay; new deals call the model whenever a key is set, reusing any recorded call with the same request.

| Setting | Default | Meaning |
|---|---|---|
| `DEMO_ACCESS_CODE` | unset | Code entered once in the workbench (user menu, Access code) and sent as `X-Demo-Access-Code`. Uploads and any step that may call the model return 403 without it; unset switches them off |
| `LIVE_DAILY_CAP_USD` | `10` | Daily live model spend for new deals, counted in the database from token usage; at the cap model steps return 429 and the header shows the limit |
| `DEALS_STUB_MODEL` | `false` | Tests and offline end-to-end runs only: a deterministic test double for the generated test deals in place of the model. Never set in a deployment |

Two generated test deals, distinct from the Bramble pack, are built into `deal-kit/output/newdeals/` (`docker compose run --rm deal-kit python -m dealkit.newdeals.build`): Harbourline (consumer instalment, CSV tape, an amendment changing the advance rate and adding a concentration limit, the lender's own model with a stale rate, a later month with a duplicate account and a loan missing from the file) and Fenwick (SME loans, XLSX tape, no reserve in the agreement, a later month with a renamed and an added column). `tests/record_deals.py` records their model calls once a key is set.

## Personas and hand-offs

There is no sign-in on the demo, so the header's acting-user menu chooses who is acting; the workbench sends it as `X-Acting-User` and the API looks up the role and enforces it. Each persona lands on My work (client users on the client portal), sees only the areas their role uses, and every step that waits on someone else becomes a work item for them, shown in their My work, in the bell and in the record's history, all in a hash-chained log.

| Persona | Role | Hands to |
|---|---|---|
| Hannah Cole | Onboarding analyst | Client user (query), credit expert (judgement), QC analyst (submit for QC) |
| Ruth Adeyemi | Credit expert | Back to the analyst who escalated |
| Tom Fairley | QC analyst | Reviewer (QC passed) or analyst (variances) |
| Marcus Hale | Second analyst | Go-live hands the facility to the monitoring analyst; report level 2 to the head or the client |
| Priya Raman | Monitoring analyst | Expert, reviewer (report level 2) |
| Elena Varga | Head of monitoring | Client (release at level 3); sees team workload |
| James Whitcombe, Laura Haskett, new clients' contacts | Client user | Answers go back to the analyst; sees only released reports, the status brief and their own queries |
| Alex Morgan | Administrator | Clients, approval levels, AI permission |

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

Test runs never write into the demo's database. The `e2e` service runs against its own stack, `api-test` and `web-test` (ports 8011 and 5181), on the `oxane_test` database, which is created and migrated when that stack starts; `pytest` does the same for itself in `tests/conftest.py`. A Playwright run from the host goes to `BASE_URL`, so point it at `http://localhost:5181` with that stack up (`docker compose --profile tools up -d web-test`) rather than at the demo on 5180.

If a test run did write into a demo database, remove what it left, then rebuild the scripted hand-offs once. It is a dry run that prints what would go until you add `--apply`; it never touches the scripted fixtures, the session logs, the audit log or the saved AI-provider key:

```bash
docker compose exec api python -m app.admin.purge --test-data
docker compose exec api python -m app.admin.purge --test-data --apply
```

`specs/deals.spec.ts` runs the new-deal flows through the browser, switching persona at each hand-off. It needs `DEMO_ACCESS_CODE` in `.env`. The AI steps run on the test model when the API is started with `DEALS_STUB_MODEL=true` (the offline variant), or on the live model only with `E2E_LIVE=1`; otherwise those two tests skip and the no-AI client's flow still runs:

```bash
DEALS_STUB_MODEL=true docker compose --profile tools run --rm e2e sh -c "npm ci && npx playwright test --project=stage specs/deals.spec.ts"
```

`specs/context.spec.ts` checks that the shell shows only what belongs to the acting persona and the page in view: each persona lands on My work with its role's navigation, list pages carry no case or facility section, the scripted case's sidebar names that case, a new-deal case page shows its own case, client users never reach internal pages (and the API refuses them), and presenter mode starts off. A matching unit test, `apps/web/src/guards/scenarioLiterals.test.ts` (part of `npm test`), fails if the shared UI (shells, navigation, breadcrumbs, headers, persona menu, notifications, My work, list pages and shared components) hard-codes a case number, a facility, client or person name from the scenario data, a fixed date, or "demo" wording.

### Smoke-test the hosted app

The `azure` project runs the suite against the hosted app. It exists only when `BASE_URL` names a hosted (https) address, or under `npm run azure`, which defaults to the demo address. It skips the specs that reset the shared scripted case or need the test model. From `tests/e2e` on the host, after `npm ci` and `npx playwright install chromium`:

```bash
BASE_URL=https://oxaneworkbench.livelypond-56376142.eastus2.azurecontainerapps.io NEWDEALS_DIR=../../deal-kit/output/newdeals DEMO_ACCESS_CODE=<code> npx playwright test --project=azure
```

```powershell
$env:BASE_URL = "https://oxaneworkbench.livelypond-56376142.eastus2.azurecontainerapps.io"; $env:NEWDEALS_DIR = "../../deal-kit/output/newdeals"; $env:DEMO_ACCESS_CODE = "<code>"; npm run azure
```

Without the access code, the tests that need it skip. `infra/deploy.ps1 -SmokeTest` runs the same after a deployment (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).

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
