# Pitch brief (19 Nov 2026) against the two demos

Source: *Oxane AI Partner Pitches: Pitch requirements and measures of success, Use Cases 1 and 2*. Pitch window 23 to 25 November 2026, one hour, Use Case 2 first. Oxane attendees include the operational staff who run these workflows daily, so the demos must hold up to people who know the work.

What the brief changes for the demos:

1. **Order.** Use Case 2 (monitoring) is the priority and is shown first.
2. **Measures.** The brief names the success measures (section 5b). Each demo's scorecard should report against those measures, by name, and separate *measured* results from *assumed* efficiency.
3. **Domain depth.** The brief lists the real complications: nested definitions, the client's own model, query cycles and client waiting time, the Excel configuration, backbook loads, independent QC with presentation differences, varied channels and asset classes, blocking against warning checks, prior-period change, approval levels, headroom and early warning, self-service alerts, and commentary for weekly status calls. The demos should show these, as worked scenarios, not slides.
4. **Controls the brief makes explicit.** Correct document versions and effective terms; every value linked to its source; an audit trail of changes; confirmed issues kept apart from matters needing expert judgement; outputs traceable in Excel; no pooling of data across clients; clients who don't permit AI stay on the existing process.

## Use Case 2: ongoing ingestion and monitoring

| Brief step | Already shown | Gap to build |
|---|---|---|
| 1. Expect and receive | Expected-submissions inbox, a late report chased automatically | Show the channel (email, SFTP, API, data room, upload) and internal deadline for each submission; prior-period data reused where the client has agreed, labelled as such |
| 2. Map and ingest | AI maps a changed tape layout; stored mapping | Show the stored mapping reused when the layout is unchanged, mapping to Oxane's standard model (portfolio, facility, loan, test, stratification), raw data kept, a client-specific master-field override; mapping memory scoped to one client (no pooling) |
| 3. Validate | Roll-forward gap, charge-off mismatch, duplicate collateral | A validation stage with the brief's rule families (missing data, duplicates, reference data, data types, logical constraints, change against prior period), each marked **blocking** or **warning**; one blocking failure stops the load until resolved; one prior-period anomaly that needs context, explained by the AI |
| 4. Review and resolve | Triage queue, AI suggests, analyst decides; noise set aside with reasons; four-eyes | Reports marked **provisional** until review completes; approval levels configured per client (one client needs a third level) |
| 5. Calculate and report | Borrowing base, triggers, NAV LTV computed in code; lender pack text | Lender-facing **Excel output with live formulas**, each input cell noting its source; comparison with an independent QC calculation before release |
| 6. Monitor and alert | Rolling trigger and what-if | **Covenant headroom** view across facilities; **early-warning** indicators (rating downgrades, price moves) on a **CLO / broadly syndicated** facility; **client self-service alert**: a client asks in plain English, the AI turns it into a rule, code runs it against history |
| 7. Communicate | Lender pack drafted | **Weekly status-call brief** for the named contact: missing data, open questions, exclusions, identifier changes, missing financials |
| Asset classes | Auto ABS (two), fund finance (NAV) | Add **CLO / broadly syndicated** (ratings buckets, CCC excess, market value, identifier changes); middle-market noted as the next extension |
| Measures (5b) | 20 accuracy checks, issues found, no false alerts, cost | Report: accuracy and completeness of loaded updates, material issues missed, false alerts per cycle, hours per cycle, turnaround, cost per cycle, share of values linked to source plus audit trail, capacity per analyst; measured and assumed shown apart |
| Data handling | Sandbox, recorded run | A client that does not permit AI runs on the existing process (code checks only, no model calls), shown in the portfolio |

## Use Case 1: onboarding

| Brief step | Already shown | Gap to build |
|---|---|---|
| 1. Receive | Pack sorted, missing page found | Include the client's own model/template and reporting requirements in the pack |
| 2. Interpret | Terms with tiers and confidence, source on every value, amendment applied, ontology | **Nested definitions**: show the chain of defined terms that refer to each other (for example Eligible Receivable → Defaulted Receivable → Delinquent Receivable), each with its source, and the resolved rule |
| 3. Clarify | Queries drafted in the exception queue | **Agreement against the client's model**: differences found (for example how a rating or FICO bucket is treated) become client queries; a **query tracker** with sent and answered dates, so elapsed time is split into analyst time and client waiting time |
| 4. Codify | Rules from the agreement, with impact preview and four-eyes | Export the **configuration workbook** (source field → loader field → expected output) that today is built by hand |
| 5. Map and load | Tape mapped to the bank's fields | **Backbook** flavour: a batch of existing deals loaded with the stored mapping, exceptions only for what differs |
| 6. Configure | Rules and thresholds | Thresholds taken from the validated configuration, not typed |
| 7. QC and release | Code checks every loan; four-eyes approval | **Independent QC comparison**: platform output against the independent Excel calculation, variances classified as genuine or presentation (blank against dash, rounding, sign, per cent as decimal); reports stay provisional until QC passes |
| Measures (5b) | Field accuracy, issues, exceptions | Report: field-level accuracy against expert-verified records, material errors and omissions, exception rate, hours per onboarding by deal type, elapsed time split from client waiting, cost per onboarding, share of values linked to source, capacity released; measured and assumed shown apart |

## Closed in the Nov 2026 gap review

| Gap | Where it shows |
|---|---|
| UC1: no client model | Case › Client model: Oxane builds the model in code from the approved terms and rule set (AI words the notes only, figures filled by code), sends it through the portal, the client confirms or asks for changes (a new version each time), the wait counts as client waiting time in the query tracker, and QC waits until it is agreed |
| UC1: reporting requirements | Case › Reporting: report lines, frequency, format and due day captured as their own step; they feed the Report sheet of the configuration workbook and the built model, and the facility record at go-live |
| UC2: calculations without a trigger | A submission whose load passes validation runs reconciliation, calculations and covenant tests by itself (activity: *Workbench (automatic)*); a held load is released by a triage decision and then re-run by the analyst |
| UC2: partial reuse | Monitoring › Mapping › Reuse by bank and sender: each bank's rule library, the layouts reused per sender, and what each facility set for itself; new deals reuse a bank's library rules (re-checked against the new agreement) and show *Set up from* on the facility |
| Integration with Panorama | Outbound client and an in-app mock (a stub): load file at go-live, results on release, receipt in the audit trail |
| Clients that don't permit AI | Labelled *Existing process — outside AI scope*; not presented as a feature; no model call for them, tested |

## Out of scope

Use cases 3 to 6 are not scored. The pitch can mention extension briefly; the demos don't build for them.

## RFP review notes (internal review, Nov 2026)

The internal review asks two things of the demos: show the agent design (which agents, their tasks, triggers, dependencies and constraints, and which pain point each one answers), and cover the asset classes by their real document load. Agreed additions:

| Review point | Addition to the demos |
|---|---|
| Agents, tasks, triggers, interdependencies, constraints | **Agents console**: each agent (Intake, Classification, Extraction, Mapping, Triage, Drafting, Alerts, Status call) and each code-only engine (Validation, Calculation) with its task, trigger, inputs and outputs, dependencies and constraints; a run log per case and cycle with time, cost and outcome; which pain point each one addresses (calculations, communications, self-service alerts, weekly call summary) |
| Middle-market and back-leverage: most unstructured, judgement-heavy | **Middle-market facility** with 30 to 50 obligors: quarterly obligor financials and compliance certificates read by the model (leverage, interest cover), judgement items routed to an expert |
| Fund finance: subscription lines carry heavy investor documents | **Subscription line** facility: investor list, investor eligibility and concentration, an investor exclusion event that reduces the borrowing base |
| Recurring documents by asset class; CLO daily feeds; format variety | **Document schedules** per facility from its asset class (document, format, frequency); CLO daily position, price and rating feeds; a mapping library counting distinct layouts per document type and servicer |

Built in the May 2026 cycle (all generated by the cycle kit, all scored):

| Addition | Facility | Planted | Expected outcome |
|---|---|---|---|
| Middle-market | Ravenglass Direct Lending Fund I back-leverage facility (Calderwood): 40 obligors, quarterly financials in four layouts, compliance certificates in two forms, monthly portfolio report and borrowing base certificate | M13 Hexby leverage 6.43x over 6.00x, out of the base · M14 Calloway add-backs 34% against a 20% cap (5.70x, 6.06x or 6.37x by reading) · M15 Ashlar Q1 financials missing, excluded · M16 Kelsall waiver 5.50x to 6.25x for Q1 · N6 Pendle 4.83x reported, 4.84x recomputed | confirmed (James told) · expert (Ruth) · query (status call) · logged · logged |
| Subscription line | Wharfedale Infrastructure Partners III (Thornbury, no AI): 30 investors, April and May registers, capital call 7, distribution 4 | M17 Brackley downgraded to BB+, excluded: base US$214.75m against US$228m drawn, prepayment US$13.25m · M18 Northfleet 16.43% against 15%, US$3.29m off the base · M19 register not posted for Thirlmere · N7 distribution reconciles | confirmed (Laura told) · confirmed · query · logged |
| Schedules and feeds | Every facility's schedule from its asset-class template; Larkspur's daily positions, prices and ratings through May; the mapping library (22 layouts with versions) | M20 no price file for 21 May · N8 14 May position file 3 h 42 min late, complete | query · logged |

The model reads the obligor documents and the waiver notice, suggests triage and drafts the pack and brief section for Ravenglass. Until those calls are recorded the cycle runs the code fallbacks (the fund's portfolio report, a keyed waiver with its quote checked, rule suggestions, templates), lists each step as pending recording, and scores only what code settled. Record them with `docker compose exec api python -m app.monitoring.cycle --mode record --budget-usd 4`.

Points for the proposal and presentation rather than the demo: which asset class the UC2 pilot covers within the 16 weeks, the document volumes for a 15-facility pilot, the size of the labelled test set per document type, and how the agents sit beside Panorama and Accelerate (confirm in discovery).
