# Oxane Ongoing Ingestion and Monitoring Demo: Development Plan

Source: `Oxane_Ongoing_Ingestion_and_Monitoring_Demo_Specification.docx` (31 Oct 2026, use case 2), read against the onboarding demo as built (commit 2ad80e5).

## Status (3 Nov 2026)

Phases 0 to 5 are built and pass their checks: the cycle kit regenerates byte for byte, the engine's monitoring checks match the cycle answer key, and the recorded cycle scores 20 of 20 values, finds M1 to M9 with the right outcome and raises none of N1 to N3. Recording the cycle costs about US$0.35. Phase 6 (rehearsals and the walkthrough video) is next, and the cycle documents still need a credit BA's review.

## 1. Summary

We will extend the onboarding workbench with a portfolio level. An analyst runs Calderwood Bank's May 2026 monitoring cycle across three facilities in nine scenes, from submissions received to an approved lender pack.

As the spec asks, the two demos share one facility record, rules engine, exception queue and workbench. The onboarding demo stays exactly as it is, and Monitoring becomes a second mode of the same app.

The build follows the onboarding demo's pattern:

1. **One cycle file generates everything.** A `cycle.yaml` beside `deal.yaml` produces the three facilities' documents, the March to May tapes and the answer key, so the numbers always agree. The pipeline never reads the key.
2. **Every number comes from code.** The model extracts values, maps changed layouts, spreads financial statements, suggests a triage outcome and drafts pack commentary. Reconciliation, tests and what-if are deterministic Python.
3. **Recorded model calls.** The same live, record and replay gateway is used, so the stage demo needs no network call.
4. **The Private Credit Ontology grows.** Kestrel switches on the NAV lending extension that is already reserved in the ontology.

Section 3 lists conflicts between the spec and the onboarding demo. They must be settled before the data is generated, because a credit expert watching both demos would catch them.

## 2. What the product must do

| Scene | Screen | Hero interaction | Must be true |
|---|---|---|---|
| 0 | Portfolio monitor | Open a facility | Three facilities, documents due, status; states that all data is synthetic |
| 1 | Submission tracker | View the chase | Northmoor servicer report late, chase already sent; two new Bramble columns mapped from memory, no alert |
| 2 | Reconciliation | Open the 27 loans | Roll-forward gap of US$412k traced to 27 missing loans; US$140k charge-off difference on 9 loans |
| 3 | Terms timeline | Switch period | Amendment No. 2 (limit US$300m, dealer limit 7%) effective 1 June; May uses US$250m and 5%, both shown with clauses |
| 4 | Covenants and triggers | Run what-if for June | Delinquency near-breach with June what-if; leverage recomputed against reported; Kestrel loan-to-value 30.3% or 32.2% |
| 5 | Collateral check | Open both tape rows | One VIN in two facilities' May tapes |
| 6 | Triage and expert queue | Confirm, query, send to expert | Four outcomes with reasons; three noise items held back |
| 7 | Lender pack | Approve and send | One pack per facility, every figure linked to its source; approval and audit log |
| 8 | Scorecard | None | M1 to M9 found, none of N1 to N3 raised; effort, turnaround and cost measured |

Pass bar: all nine planted issues found, and none of the three noise items raised as an alert. Each check stores its inputs, the terms version it used and its result.

## 3. Spec issues to resolve first

The proposed fixes below were accepted on 3 Nov 2026, including dropping the payment deferral example (issue 5), and the build follows them.

### Conflicts with the onboarding demo (would be noticed)

| # | Issue | Proposed fix |
|---|---|---|
| 1 | **Bramble's pool is the wrong size.** The spec's May roll-forward expects US$235.60m. The onboarding April tape is US$63.41m across 2,400 loans, with US$48m drawn, so the pool cannot nearly quadruple in a month. | Keep the story and the US$412k gap from 27 loans (about US$15k a loan), at Bramble's real scale: about US$69.7m expected and US$69.3m on the tape. |
| 2 | **Bramble's delinquency history contradicts onboarding.** The onboarding servicer report shows 60+ day delinquency of 0.71%, 0.76% and 0.79% (February to April), which is right for a near-prime lender. The spec has 5.1%, 5.6% and 6.6% for March to May. | Move the near-breach to Northmoor, a new subprime borrower whose 60+ day trigger we write at 6.0%. The spec's numbers, the 5.77% average and the June what-if (above 5.8% breaches) then hold unchanged. Bramble passes at about 0.8%. Northmoor keeps its excess spread trigger as well. |
| 3 | **The leverage story contradicts onboarding.** Onboarding already recomputed Bramble's Q1 leverage as 5.28x, a pass, from the same Q1 statements. The spec has the borrower reporting 5.4x and a recomputed 6.2x. | Keep onboarding's figures, and add one new fact in the Q1 compliance certificate due in May. Its notes disclose a US$53.9m guarantee of the parent's other warehouse line. The borrower reports 5.28x without it. Counted as a liability under clause 1.1, leverage is 6.20x against the 6.0x maximum. Whether a guarantee counts is a reading of the clause, so it stays an expert review item, as M6 intends. |

### Gaps that would break the demo flow

| # | Issue | Proposed fix |
|---|---|---|
| 4 | **M1 is escalated "after one day"**, but the demo runs in one sitting. | Use a fixed demo clock of 24 June 2026. The 15th business day of June is 22 June (Juneteenth falls on the 19th), the chase was sent on 23 June and escalated on 24 June, with both shown in the chase history. (The plan first said 17 June, which is before the due date.) |
| 5 | **The triage table names an expert example that is not planted**: whether a payment deferral counts as a modification. | Drop it, so every on-screen item is in the answer key. The alternative is to plant it as M10. |
| 6 | **Northmoor's excess spread trigger has no numbers.** | Northmoor passes at 4.1% against a 3.0% minimum, so the screen shows a pass beside the near-breach. |

### Worth showing, not a problem

| # | Point | Use in the demo |
|---|---|---|
| 7 | Onboarding found Sunrise Motors at 5.76% of the pool against a 5% dealer limit. Amendment No. 2 raises the limit to 7% from 1 June. | The terms timeline shows the May excess still applying, and that it falls away in June. This links the two demos without adding scope. |

Totals check out: the scenes sum to 20 minutes, the build tasks to 616 hours, and the Kestrel figures (30.3% and 32.2%) and the delinquency average (5.77%) are correct.

## 4. Architecture

Everything new sits beside the onboarding code, not inside it.

| Layer | Added | Reused |
|---|---|---|
| Cycle kit (`deal-kit/`) | `cycle.yaml`; Northmoor and Kestrel terms; Bramble March to May tapes and May documents; Amendment No. 2; Kestrel NAV, valuation and compliance documents; answer key for M1 to M9 and N1 to N3 | Tape generator, PDF and workbook builders, Bramble terms |
| Engine (`packages/engine/`) | Roll-forward, tape against servicer report, effective-dated terms, rolling triggers with what-if, NAV loan-to-value, valuation freshness, cross-facility VINs, tolerances | Rules, borrowing base, covenants |
| API (`services/api/`) | Monitoring cycle pipeline, portfolio and cycle endpoints, triage and pack services | Gateway, audit log, sessions, scoring |
| AI steps | Layout mapping with memory, statement spreading, triage suggestion with reason, pack commentary; recorded for replay | Extraction with verified quotes |
| Ontology | NAV lending layer: NAV, loan-to-value, valuation, position, markdown | Private credit core, asset-based finance, auto loans |
| Workbench (`apps/web/`) | Lender and cycle bar, portfolio monitor, submission tracker, reconciliation, terms timeline, covenants and triggers, collateral, triage and expert queue, lender pack, cycle scorecard | Shell, evidence panel, loan drill, badges, keyboard control |

## 5. Delivery phases

| Phase | Output | Spec tasks | Done when |
|---|---|---|---|
| **0. Foundations** | Monitoring mode, lender and cycle bar, portfolio data model, routes | 16 (part) | The mode switch shows the portfolio shell with three facilities |
| **1. Cycle kit** | `cycle.yaml`, every document for three facilities, three months of tapes, answer key | 1–5 | Kit regenerates identically from the seed; every M and N item present; a verify script confirms the numbers |
| **2. Deterministic core** | All code checks in section 6 of the spec, with tolerances and what-if | 8, 9, 11, 12, 14 | Tests match the answer key for every check; same input, same output |
| **3. Workbench on seeded data** | All nine screens and the full flow | 6, 16, 17, 18 | Scenes 0 to 8 click through in about 20 minutes, and you sign off the UX |
| **4. AI steps** | Layout memory, statement spreading, triage suggestion, pack drafting; record and replay | 7, 10, 13, 15 | Workbench runs on pipeline output; replay works offline |
| **5. Controls and scorecard** | Triage decisions, chase log, pack approval, audit, computed scorecard | 13, 18 | Scorecard reads only run data and the key |
| **6. Stage readiness** | Tuning, rehearsal, fallback recordings, walkthrough video | 19–21 | M1 to M9 found, no noise raised, three clean rehearsals |

Phases 1 and 2 feed everything else. Phase 0 depends on none of the decisions in section 3, so it can start straight away.

## 6. Needed from you

| Item | Needed by | Note |
|---|---|---|
| Decisions on section 3, above all issues 1 to 3 | Phase 1 | They set the numbers the cycle kit generates |
| Credit BA review of the cycle documents | Phase 1 | Not automatable, as with use case 1 |
| About US$2 to US$3 of model usage | Phase 4 | Same key as before; replay costs nothing |
