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

## Out of scope

Use cases 3 to 6 are not scored. The pitch can mention extension briefly; the demos don't build for them.
