# Oxane Workbench: what we are delivering

Prepared for the Oxane AI partner pitch (Use Case 2 first, then Use Case 1). Everything below runs in the hosted app; all data is synthetic.

## How to open it

- **URL:** https://oxaneworkbench.livelypond-56376142.eastus2.azurecontainerapps.io
- **Onboarding** opens at `/cases`; **Monitoring** at `/monitoring`; switch between them in the header.
- **Personas:** pick who you are acting as from the user menu (top right). No sign-in in this demo build.
- **Access code:** needed only for uploads and live AI (user menu, *Access code*). It is in `.env.azure` as `OXANE_DEMO_ACCESS_CODE`.
- **Presenter mode:** header toggle, Alt+P or `?presenter=1` shows the numbered steps and short hints; off by default.
- **Sample documents** for a new deal: `/samples/harbourline-onboarding.zip`, `/samples/harbourline-monthly.zip`, `/samples/fenwick-onboarding.zip`, `/samples/fenwick-monthly.zip`.

## Design principles (what makes it safe for a lender)

- The AI reads, maps, suggests and drafts; **code computes every number**.
- **Every extracted figure is checked against its quoted source** on the page; a failed check blocks approval.
- Model-written text uses placeholders that **code fills with figures**, so a draft can't carry a wrong number.
- **Four-eyes**: whoever prepared work can't approve it; per-client approval levels (two or three).
- **Hash-chained audit trail** of every action, with the person and time.
- **No pooling of data across clients**; mapping memory is kept per client.
- **Clients that don't permit AI are outside the AI scope** and stay on the existing process, labelled *Existing process — outside AI scope*. The workbench still handles them (code checks and templates), and no model call is ever made for them.
- Live AI on the hosted app sits behind an access code and a **US$10 daily spend cap**.

## Personas and hand-offs

- Eight personas, one switch shared by both workbenches: Onboarding analyst (Hannah Cole), Credit expert (Ruth Adeyemi), QC analyst (Tom Fairley), Second analyst (Marcus Hale), Monitoring analyst (Priya Raman), Head of monitoring (Elena Varga), Client contacts (James Whitcombe, Laura Haskett, plus each new client's contact), Administrator (Alex Morgan).
- Each persona lands on **My work**: items assigned to them, waiting on them, and recent hand-offs, with age.
- Navigation and actions follow the role, enforced by the API, not just the screen.
- **Hand-offs are records**: each step creates a work item for the next person, shown in their queue, the notification bell, the record's history and the audit trail.
- **Client portal**: the client sees only their own queries, released reports, the status-call brief and alerts.

## Use Case 2: ongoing ingestion and monitoring

**Portfolio**: 26 facilities across two banks (Calderwood: AI permitted, two approval levels; Thornbury: existing process, outside AI scope, three levels) and five asset classes: auto ABF, consumer and equipment ABF, fund finance (NAV and subscription line), CLO / broadly syndicated, and middle-market back-leverage.

1. **Expect and receive**
   - Expected-documents schedule per facility from its asset-class template (document, format, frequency, channel, internal deadline).
   - Channel per submission (email, SFTP, API, data room, upload); late files chased; prior-period data reused only with recorded client consent.
   - CLO daily feeds (positions, prices, ratings) checked day by day: a missing price day and a late position file are flagged.
2. **Map and ingest** (partial reuse: Mapping › *Reuse by bank and sender* shows, per facility, the rules taken from its bank's compliance rule library, the layouts reused from each sender, and what was set for the facility alone)
   - Stored mapping reused when the layout is unchanged (no AI); the AI maps only what changed.
   - Oxane standard model (portfolio, facility, loan, test, stratification); raw data kept; client master-field overrides.
   - **Mapping library**: 22 layouts with counts, version history and which facilities use each.
3. **Validate**
   - Rule families: missing data, duplicates, reference data, data types, logical constraints, change against prior period; each marked **blocking** or **warning**. A blocking duplicate holds the load until resolved.
   - A prior-period jump explained by the AI from a quoted line in the servicer's commentary.
4. **Review and resolve**
   - One exceptions queue with IDs, owners and history; the AI (or a rule, for no-AI clients) suggests, the analyst decides; harmless differences logged with a reason.
   - Reports stay **provisional** until every approval level is complete.
5. **Calculate and report** (no manual trigger: once a load passes validation with no blocking failure, calculations and covenant tests run automatically, logged as *Workbench (automatic)*; after a held load is released the analyst re-runs it)
   - Borrowing base, triggers, covenants, concentration, NAV LTV, CCC excess, obligor leverage and interest cover, investor eligibility: all computed by the engine.
   - Lender **Excel workbook with live formulas** and a source note on every input; compared with an **independent QC workbook**, variances classed as presentation (blank vs dash, rounding, sign, per cent vs decimal) or genuine; a genuine variance blocks release.
6. **Monitor and alert**
   - Covenant **headroom** across facilities; **early warnings** (rating downgrades, price moves, rising trends, stale valuations).
   - **Client self-service alerts**: the client asks in plain English, the AI drafts the rule, code checks it and back-tests it on history, the analyst approves.
7. **Communicate**
   - Lender pack drafted with every figure filled by code.
   - **Weekly status-call brief** per client: missing data, open questions, exclusions, identifier changes, missing financials, early warnings.

**Worked scenarios** (planted and scored): 27 loans missing from a tape; servicer reports disagreeing on charge-offs; terms changed mid-year by amendment; a delinquency trigger close to breach with a what-if; leverage that depends on a guarantee (expert call); one car pledged to two facilities; a duplicate loan row that blocks a load; CCC share 8.41% against 7.5% with the haircut at market value; a 14.75-point price drop; an identifier change linked rather than booked as a trade; a middle-market obligor over its leverage covenant; EBITDA add-backs over the cap needing expert judgement; missing obligor financials; a covenant waiver; a subscription-line investor downgraded and excluded; investor concentration over limit; a capital call not posted to the investor register; a missing CLO price day.

**Result on the recorded cycle**: 20 of 20 planted issues found, 0 of 8 harmless items raised, 49 of 49 values correct.

## Use Case 1: onboarding

**Cases list**: 15 onboarding cases across five clients and deal types (auto ABF, consumer, SME, fund finance, CLO warehouse), Intake to Live, plus a four-deal backbook.

1. **Receive**: documents classified by type, version and effective date; a missing schedule found; the client's own model included. New cases record **the reporting the client needs** (report lines, frequency, format, due day) as their own step, which feeds the configuration workbook's Report sheet.
2. **Interpret**: key terms with tier, confidence and source; amendment applied; **nested definitions** traced through 23 terms to the borrowing base, reproduced to the cent.
3. **Clarify**: the **client's model compared with the agreement**, each difference costed (e.g. a stale 85% advance rate overstates the base by US$1.48m) and turned into a client query; **query tracker** splitting analyst time (9.5 h) from client waiting time (74 h). **Where the client has no model**, Oxane builds one in code from the approved terms and rule set (the AI may word the covering notes only), sends it through the portal for the client to confirm or change, and tracks the wait like any other query; QC waits until the model is agreed.
4. **Codify**: rules drafted from the agreement with impact preview and four-eyes; **configuration workbook** export (source field → loader field → expected output); every threshold checked against its source quote.
5. **Map and load**: tape mapped to the bank's fields; **backbook** batch loaded with the stored mapping, exceptions only where a deal differs.
6. **Configure**: thresholds taken from the validated configuration, not typed.
7. **QC and release**: **independent QC comparison**, 13 lines classified, two genuine variances block release until resolved; reports provisional until QC passes.

## End to end: a new deal from onboarding to monitoring

- **Create** clients (AI permitted or not, approval levels, master-field overrides), facilities and onboarding cases; upload, replace and remove documents; edit and archive.
- **New onboarding with live AI**: upload the agreement, amendments, tape and client model → the AI classifies and extracts terms with quotes, checked by code → analyst approves or edits with a reason → rules drafted and validated → tape mapped (stored per client) → engine validates the tape → exceptions → QC → four-eyes approval → load file and configuration workbook → **Go live** creates the monitoring facility.
- **First monitoring month** for that facility: upload → mapping reused → validation → reconciliation and triggers run automatically → triage → report and Excel workbook → approval levels → released to the client portal.
- **Panorama hand-off (stub)**: at go-live the approved load file, and on release each month's results (new deals and the scripted May cycle's packs), are posted to a mock Panorama endpoint inside the app; the request, response and receipt (*Sent to Panorama · receipt PNR-…*) go into the audit trail. The real endpoint and key are configuration only (`PANORAMA_BASE_URL`, `PANORAMA_API_KEY`).
- **Bank rule library**: a bank's second facility can reuse rules from its first; each is re-checked against the new agreement's own clause.
- **Clients outside the AI scope**: the same steps on the existing process: terms entered by hand with page references (code checks them), name-matching mapping, template notes, no model calls.

## Agents console

- Every **AI agent** (Intake and classification, Extraction, Definitions, Client-model comparison, Rule drafting, Mapping, Change explanation, Triage, Drafting, Alerts, Status-call brief) and every **code-only engine** (Quote check, Validation, Reconciliation, Calculation and covenants, QC comparison).
- For each: purpose, tasks, **trigger**, inputs and outputs, **dependencies**, **constraints**, use-case steps, **pain points addressed**, asset classes now and after pilot.
- **Dependency graph** by pipeline stage; **coverage matrix** of agents × pain points × asset classes.
- **Run log** of every model call with outcome, tokens, cost and duration; refusals for no-AI clients shown at zero cost.

## Administration

- **Settings › AI provider**: an administrator sets the Anthropic (or Microsoft Foundry) key, tests the connection, and saves it encrypted; it applies from the next call with no restart. The key is never shown back, only its last four characters.
- Clients, approval levels, AI permission and users managed by the Administrator persona.

## Platform and deployment

- One container on Azure Container Apps with PostgreSQL, Key Vault and Log Analytics; deployed by `infra/deploy.ps1`.
- Recorded AI runs replay with no key, so the pitch scenarios behave identically every time; new deals call the model live.
- Tests: API, engine, deal kit, web and browser end-to-end suites; generated documents rebuild byte for byte and are checked by manifest at build time.

## Verified on the hosted app (23 Nov 2026)

- All pages and APIs respond; no console errors; no sideways scroll at 1440 px.
- Monitoring scorecard on Azure: 49 of 49 values, 20 of 20 planted issues found, 0 of 8 noise items raised.
- Agents console: 16 agents and engines, run log populated; 9 personas in the switcher.
- **New deal end to end on Azure**: new client → Harbourline consumer onboarding (upload, AI classify and extract, terms approved, rules, mapping, validation, client query answered in the portal, QC by Tom, approval by Marcus) → go-live → first month (mapping reused, duplicate account held the load, roll-forward gap found, triggers, triage, report) → approved and released to the client. Every step completed in seconds.
- Before the pitch, open each workbench once to warm the server (the first load after a restart is slower).

## Known limits

- The middle-market (Ravenglass) model steps are not recorded yet (on hold); until then that facility uses its code fallback, and three of its values are not scored. New deals use recorded calls where they exist and the live model otherwise.
- No sign-in in this demo build: anyone with the URL can view; uploads and live AI need the access code.
- Walkthrough videos predate these changes and need re-recording.
