# Oxane AI-Assisted Onboarding Demo: Development Plan

Source: `Oxane_AI_Assisted_Onboarding_Demo_Specification.docx` (31 Oct 2026), read with the Oxane RFP and the L100 to L300 domain guides.

## 1. Summary

We will build one web app, the analyst workbench, plus the pipeline behind it. It takes the fictional Calderwood / Bramble facility from an 8-file pack to an approved load file in nine scenes.

Three decisions shape the build:

1. **One deal file generates everything.** A single `deal.yaml` plus a fixed random seed produces the documents, the tape, the borrower's certificate and the answer key, so the numbers always agree. The pipeline never reads the answer key.
2. **The deterministic core comes first, and the UI comes before the AI.** The rules engine is built and proven first. All nine screens are then built against seeded data, so UX quality gets the most iteration and the AI work plugs into a finished surface.
3. **Every external service sits behind an adapter.** Local and Azure run the same code and differ only in configuration. The LLM adapter has `live`, `record` and `replay` modes, so the stage demo works without a network call.

Section 3 lists problems in the spec that need fixing before the data is generated. X4 is the most serious, because a credit expert would spot it.

## 2. What the product must do

| Scene | Screen | Hero interaction | Must be true |
|---|---|---|---|
| 0 | Deal card | None | States that all data is synthetic |
| 1 | Intake | Drop 8 files | Files classified, Amendment No. 1 linked, Schedule 4 flagged missing |
| 2 | Terms | Click a value, clause opens highlighted | 26 fields with source, confidence, tier and status; 85% struck through, 82.5% from 1 Mar 2026 |
| 3 | Rules | Edit a threshold | 17 rules, each shown as clause, plain English and test logic; edit logged with name and reason |
| 4 | Mapping | Accept a mapping | 38 columns mapped; weighted average APR labelled as derived; date formats resolved |
| 5 | Validation | Run, then drill from gap to loans | System figure beside borrower's; 3 shared VINs across 6 loans flagged |
| 6 | Exceptions | Accept, query, escalate | Each item has type, evidence, suggested action and owner |
| 7 | Approve | Second analyst approves | Self-approval is blocked; load file and audit log produced |
| 8 | Scorecard | None | Figures are computed from the run, with formulas shown |

Pass bar: 10 of 10 planted exceptions found and 3 or fewer false items. Every Tier 1 value needs a person. The same tape always gives the same result.

## 3. Spec issues to resolve first

The "Proposed fix" column was accepted on 31 Oct 2026, including the US$1.1m gap for X4, and the build follows it. The source spec still has the old values. Totals, hours, the 26 fields and the 17 rules all check out.

### Would be noticed by the audience

| # | Issue | Proposed fix |
|---|---|---|
| 1 | **X4 is arithmetically impossible.** US$3.3m across 41 loans averages US$80,487, but rule E5 caps a loan at US$75,000, so 41 eligible-sized loans top out at US$3.075m. It is also far above a typical auto loan. | Keep 41 loans and change the gap to about US$1.1m (about US$27k a loan). Alternative: keep US$3.3m with about 122 loans. |
| 2 | **The gap cannot be explained by the 41 loans alone.** The 6 duplicate-VIN loans fail E12, so they also leave the system's eligible pool. The borrower would have counted them. | Replace the single gap with a bridge: borrower's figure, less 41 past-due loans, less 6 duplicate-VIN loans, equals system figure. Excess concentration and advance rate get their own bridge lines. |
| 3 | **The delinquency trigger needs three months of data**, but the servicer report covers April only. X7 says the trigger can still run. | Add a trailing three-month delinquency table to the servicer report. |
| 4 | **Processing cost is missing from the scorecard.** The spec says it uses the RFP's success measures, but the RFP lists six and processing cost is left out. | Add it, taken from logged LLM and OCR usage. |

### Would break the demo flow

| # | Issue | Proposed fix |
|---|---|---|
| 5 | **Approval has no defined state for open items.** X2 (Schedule 4), X4, X5 and X7 wait on outside parties and cannot close during the demo. Restricted Jurisdictions is a Tier 1 field with no value. | Add the status "Approved with open items". Blocking items need an explicit carry-forward by the approver, and the load file lists them. |
| 6 | **Rule E7 cannot run**, and the spec does not say how it affects the result. | Give E7 the status "Not evaluated" and label the borrowing base "Provisional: E7 not run". |
| 7 | **The scene 3 edit would change scene 5 and break the answer key.** | The edit shows a live impact preview and saves as a pending rule version. Runs use the last approved version. In scene 7 the second analyst declines it with a reason, which also shows that four-eyes is a real control. |
| 8 | **The Sunrise Motors match changes the numbers after scene 5.** | Make X6 the item accepted live in scene 6. The bridge recalculates in front of the audience. X4 is the query and X5 the escalation. |
| 9 | **Four minutes cannot cover 11 Tier 1 approvals and 10 exceptions.** Only 3 terms and 3 exceptions are worked live. | Seed the rest as worked earlier by the same analyst, and label them so in the audit log. |
| 10 | **Measured time on stage would mislead.** Cached results make the run look faster than it is. | Show a visible "Live" or "Replay" label, and show the recorded pipeline duration separately. Replay is never presented as live. |

### Would block the build

| # | Issue | Proposed fix |
|---|---|---|
| 11 | Rules use tape columns not listed in the spec: `model_year`, `payments_made` and new or used status. X9 needs another date column. | Include these plus `first_payment_date` in the 38 columns. |
| 12 | The borrowing base calculation leaves three things open: which pool the 1% reserve uses, which pool concentration percentages use, and how a loan in two excess buckets is treated. | Reserve and limits use the eligible pool before excess. Excess is applied in order C1 to C5, without double counting. Written into the agreement text so the demo cites it. |
| 13 | Queue types do not match. Scene 6 names 3 types, while the exception table uses 7. | Keep the RFP's 3 as the main types, with the other 4 as sub-labels. |
| 14 | Covenants are extracted and X10 builds the leverage formula, but no scene shows a result. | Add a small covenant panel to Validation, using Q1 figures. |
| 15 | The target go-live date is unspecified, and the commitment schedule has no number. | Use a demo date of your choice. Call the schedule Annex A. |

**Staffing.** If the six-person plan stands, AI2 has 72 hours in week 2 (tasks 9 and 10), and AI1 has at least 64 (tasks 8 and 12, plus part of 7). Move task 9 or 12 to week 3, or add capacity.

## 4. UX plan

**The goal:** a credit expert should feel the tool was built by someone who has done the job, and should be able to check any number without being asked to trust it.

### Principles

| Principle | What it means on screen |
|---|---|
| Evidence is always one click away | Evidence panel on every screen; hovering a value previews its clause |
| Show who produced each value | Chips for AI drafted, Calculated, Derived, Analyst edited and Approved |
| Numbers read like finance | Tabular numerals, right aligned, consistent units, full precision on hover |
| Show position at all times | Deal bar plus a stepper with live counts, such as "Terms 18/26" and "Exceptions 7 open" |
| Motion explains change | Used only for cause and effect, such as a bridge step updating. Respects reduced-motion settings |
| Readable from the back of a room | Tested at 1080p on a projector; presenter mode enlarges the type |
| Fast for repeat use | Keyboard control: `J`/`K` to move, `A` approve, `E` edit, `Q` query, `Ctrl+K` command palette |
| Every state is designed | Skeletons, empty states, errors with a next step, undo on reversible actions |

### Signature moments

1. **Intake:** files settle into a checklist as they are classified, and Schedule 4 appears as a dashed "expected but not received" card.
2. **Click to clause:** the PDF glides to the exact page and the clause highlights in place, using real text coordinates.
3. **As-of date control (added):** drag an effective date across 1 Mar 2026 and the advance rate flips from 85% to 82.5%, with the cited clause changing beside it.
4. **Rule impact preview (added):** while editing a threshold, the app shows how many loans and dollars would change.
5. **Reconciliation bridge:** a waterfall from the borrower's figure to the system's. Clicking a bar opens exactly those loans.
6. **VIN cluster view:** the 3 VINs with their 6 loans side by side, so double pledging is visible at a glance. This is the slowest moment in the script.
7. **Live recalculation:** accepting the Sunrise match re-runs the engine and the bridge updates.
8. **Scorecard:** every figure opens its formula and its underlying items.

### Visual system

- **Palette:** Artizent's deck theme: near-black `#141414`, warm neutrals and grey `#7B716D`. Yellow `#FFDD00` appears only as a focus or selection accent, never as text on white.
- **Status colours:** a separate semantic set. Every status also has a label or icon, so colour is never the only signal.
- **Type:** Inter with tabular numerals, plus a monospace face for rule logic. Light theme by default, because it projects better. Dark theme is not in scope.
- **Branding:** presented as an Artizent workbench, with no Oxane branding or Panorama look-alike. The app states "Not connected to Panorama".
- **Accessibility:** WCAG 2.2 AA, checked with axe plus a full keyboard pass.

### How quality is checked

Each screen goes through a design review against a screenshot before it counts as done. Playwright visual snapshots catch regressions at 1920×1080 and 1440×900. Target timings: screen change under 150 ms, clause jump under 300 ms, engine re-run under 1 second. The workbench is desktop only, as it is a stage and analyst tool.

## 5. Architecture

### Local

| Layer | Choice | Why |
|---|---|---|
| Workbench | React, TypeScript, Vite, Tailwind, Radix primitives | Accessible parts with full control of the design |
| Data grids | TanStack Table and Virtual | Smooth with 2,400 loans |
| Motion and charts | Motion, custom SVG waterfall | The bridge is the hero, so it is custom built |
| PDF | PDF.js with our own highlight overlay | Exact control of highlights from stored coordinates |
| API | Python 3.13, FastAPI, Pydantic, server-sent events for progress | Same language as the engine; no job queue needed at this size |
| Data store | PostgreSQL 16 in Docker, SQLAlchemy, Alembic | As the spec requires; audit table is append only |
| Rules engine | Pure Python, rules as versioned JSON | No `eval`. Rule logic is a small validated expression format, and the result is keyed by a hash of tape and rule set |
| PDF parsing | pdfplumber and pypdfium2 | Keeps page and character positions. PyMuPDF is avoided because of its AGPL licence |
| OCR | Adapter: Azure Document Intelligence, with results recorded for local replay | One real scanned page is enough, so no local OCR engine is needed |
| LLM | Anthropic Python SDK behind our gateway, `claude-opus-5-5` by default, set in config | Matches the spec's model-agnostic gateway |

### How AI output is kept honest

- The model returns each value with an exact quote, using structured outputs. Claude's built-in Citations feature cannot be combined with structured outputs and only gives page-level locations for PDFs, so we do not depend on it.
- **Code then finds that quote in the parsed text.** If the quote is not found, the value goes to the queue as unverified. This check is what makes highlights exact and stops invented citations.
- Confidence comes from verifiable signals (quote match, OCR quality, agreement across passes), not from the model's own opinion.
- Tier 1 values get two independent extraction passes, and any disagreement goes to the queue.
- Document text is treated as data in prompts. No LLM output reaches a calculation without passing rule validation.

### Azure mapping

| Local | Azure |
|---|---|
| Docker Compose | Azure Container Apps, one image serving the SPA and API, minimum one replica so there is no cold start on stage |
| Postgres container | Azure Database for PostgreSQL Flexible Server |
| Local file store | Azure Blob Storage |
| `.env` | Azure Key Vault, with managed identity |
| Anthropic API key | Claude on Microsoft Foundry through `AnthropicFoundry`. The features we use (PDF input, structured outputs, prompt caching) are listed as available there |
| Logs | Application Insights |
| None | Entra ID sign-in through Container Apps authentication, private by default |

Infrastructure is written in Bicep and deployed with `azd`, with images in Azure Container Registry. Before Azure work starts, check that `claude-opus-5-5` is offered in the chosen Foundry region and subscription type.

### Repository

```text
apps/web/            React workbench
services/api/        FastAPI, pipeline, adapters
packages/engine/     Rules engine and borrowing base (no I/O)
deal-kit/            deal.yaml, generators, answer key
fixtures/            Recorded LLM and OCR responses
infra/               Bicep, azd config
tests/e2e/           Playwright scene tests
docs/
```

## 6. Delivery phases

Each phase ends with something that can be seen and checked. "Spec tasks" refers to the build table in the spec.

| Phase | Output | Spec tasks | Done when |
|---|---|---|---|
| **0. Foundations** | Git repo, Docker Compose, CI, design tokens, core components, app shell | 5 | `docker compose up` shows the deal bar and stepper |
| **1. Deal kit** | `deal.yaml`, generators for all 8 documents, answer key | 1–4 | Pack regenerates identically from the seed; all 10 exceptions present; a separate script confirms the numbers reconcile |
| **2. Deterministic core** | Rule format, engine, borrowing base, bridge, covenants | 11 | Tests match the answer key on all 17 rules; same input gives the same output |
| **3. Workbench on seeded data** | All 9 screens, signature moments, full flow | 14, 15 | Scenes 0 to 8 can be clicked through in under 20 minutes, and you sign off the UX |
| **4. AI pipeline** | Gateway, intake, parsing and anchors, extraction, amendment and cross-reference resolver, rule drafting, mapping | 6–10, 12 | Workbench runs on pipeline output; replay mode works with no network |
| **5. Controls** | Exception service, four-eyes, audit log, load file, computed scorecard | 13, 16, 17 | Self-approval blocked; scorecard reads only run data and the key |
| **6. Tuning and stage readiness** | Accuracy tuning, presenter mode, one-key reset, fallback recordings | 18–20 | 10 of 10 found, 3 or fewer false items; three clean rehearsals |
| **7. Azure** | Bicep, deployment, sign-in, monitoring | Added | Full demo passes on the Azure URL, in both replay and live modes |

The seeded data in phase 3 comes from the answer key, so it would flatter the results. The scorecard stays labelled "Seed data" until phase 5 replaces it with real output.

**Sequence:** phases 1 and 2 feed everything else. Phases 3 and 4 can overlap once phase 2 is done. The six-person estimate of three weeks does not include phase 7, so allow two to three more days for it.

## 7. Quality and testing

| Level | What it covers |
|---|---|
| Unit | Each rule at its boundaries, such as E1 at 30 and 31 days; bridge totals always reconcile |
| Reproducibility | Identical results across runs; generated pack matches its stored hash |
| Accuracy evaluation | Runs in CI on replay and on demand against live; reports by tier; a test confirms the pipeline cannot read the key |
| End to end | One Playwright test per scene, plus the full 20-minute path |
| Stage drill | LLM down, network down and page reload mid-scene; each must recover or fall back |

## 8. Risks

| Risk | Mitigation |
|---|---|
| Synthetic documents look too clean | Real messiness in the generators: scans, inconsistent tables, cross-references |
| Credit detail is wrong | **A credit BA must review the pack. This cannot be automated.** External ABF reviewer if available |
| Exact clause matching fails on some text | Normalise whitespace and hyphenation; unmatched values go to the queue |
| Demo seen as competing with Accelerate | Presenter states early that a pilot would extend Accelerate; nothing on screen suggests replacement |
| Live model is slow or wrong on stage | Replay by default, with recorded fallbacks for every scene |
| Foundry availability differs by region or subscription | Checked before phase 7. The direct API remains a fallback for the demo only |

## 9. Needed from you

| Item | Needed by | Note |
|---|---|---|
| Decisions on section 3, above all X4 | Phase 1 | Everything downstream depends on these numbers |
| LLM access for local work | Phase 4 | No `ANTHROPIC_API_KEY` is set on this machine. Either an Anthropic key or a Foundry deployment works |
| Azure subscription, resource group and allowed region | Phase 4 for OCR, phase 7 for the rest | `az` and `azd` are not installed yet; Docker, Node 22 and Python 3.13 are ready |
| Credit BA reviewer | Phase 1 | Must review the pack before it is used |
| Demo date | Phase 6 | Sets the rehearsal schedule and the deal card date |
