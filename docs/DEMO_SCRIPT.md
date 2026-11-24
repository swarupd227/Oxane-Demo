# Oxane Workbench: demo script

Step by step, onboarding and then monitoring, first for a client that permits AI and then for one that does not. Every step below is one the browser tests run on the hosted app, except where marked.

**App:** https://oxaneworkbench.livelypond-56376142.eastus2.azurecontainerapps.io (no sign-in).
**Switch person:** user menu, top right. Each step says who you are.
**Sample documents:** download and unzip from `/samples/harbourline-onboarding.zip`, `harbourline-monthly.zip`, `fenwick-onboarding.zip`, `fenwick-monthly.zip` (same address).

## Before you start

1. Open `/cases` and `/monitoring` once, so the server is warm.
2. Only XYZ Bank should be in *Clients*. If a rehearsal left more, ask for the test data to be cleared.
3. Do one dry run of Part 1 first. Live AI steps take from a few seconds to about a minute each, and the first month of a new deal uses the live model.

---

## Part 1. Onboarding a client that permits AI (Ashgrove, Harbourline consumer deal)

**Alex Morgan (Administrator)**

1. *Clients* › **New client**. Legal name: `Ashgrove Credit` (any name). Named client contact: `Nadia Brooks`. AI: permitted. Approval levels: 2. **Create client**.

**Hannah Cole (Onboarding analyst)**

2. *Clients* › open the new client › **New case**. Facility name `Harbourline Consumer Receivables LLC`, deal type *Consumer instalment*, commitment `150000000` › **Open case**.
3. *Documents*: **Choose files**, select the five files from `harbourline-onboarding.zip` (agreement, first amendment, loan tape, client model, servicer report). Wait for "5 active". Click **Classify with AI**: the amendment is recognised as an amendment.
4. *Terms*: **Extract terms**. The advance rate shows **86.00%** with the First Amendment applied; the original 88.00% is shown with its source page. Open any term to see the quoted page highlighted: every figure is checked against its quote.
   - **Approve verified Tier 2 and 3**, then **Approve** each Tier 1 term. Counter reads 13/13 approved.
   - *Reporting*: **Record requirements** (the report lines the client needs).
5. *Rules*: **Draft with AI**. Each rule carries its clause and page, including the one the amendment adds. **Approve rule set**.
6. *Mapping*: **Suggest mapping** › **Confirm and store**. The mapping is kept for this client and reused every month.
7. *Validation*: Reporting date `2026-09-30` › **Validate and run**. The engine runs on 1,400 loan rows: gross pool US$16,632,199.97, **eligible pool US$13,687,998.52**, advance rate 86.00%, **borrowing base US$10,628,282.29**, delinquency 3.48%.
8. *Exceptions*: the client's model uses 88% against the agreement's 86%. Type a note and **Query client**. Work the rest with **Accept** and a note.

**Nadia Brooks (client contact)**

9. Opens her portal. Answer: "Agreed: we will update our model to 86%." › **Send answer**.

**Hannah Cole**

10. *Exceptions* › **Close with this answer**. *QC* › **Submit for QC**.

**Tom Fairley (QC analyst)**

11. Open the case from *My work* › *QC*. **Agrees** on each line › **Complete QC**.

**Marcus Hale (Second analyst)**

12. Open the case from *My work* › *Approval* › **Approve** (four-eyes: he did not prepare it) › **Go live**. The audit trail shows "Sent to Panorama · receipt PNR-…". **Open facility**.

## Part 2. First monitoring month for that facility (AI)

**Priya Raman (Monitoring analyst)**

1. *Facilities* › the new facility › **Open** the October submission.
2. Upload `Harbourline_Loan_Tape_2026-10.csv` and `Harbourline_Servicer_Report_October_2026.pdf` (from `harbourline-monthly.zip`) › **Map tape**. It says the stored mapping was reused, no AI. Confirm the new status value `PAID_OFF` if asked.
3. Nothing to press: validation and calculations run on their own. The load is **held by a blocking check** (a duplicate account).
4. Decide the duplicate: outcome *Confirmed*, a reason › **Decide**. "Hold released by Priya Raman". **Re-run calculations**: the borrowing base appears.
5. **Decide** each remaining finding. **Draft report**: the AI words it, code fills every figure. **Approve, level 1**.

**Marcus Hale**

6. Open the submission › **Approve, level 2**. Status *Released*, with the Panorama receipt.

**Nadia Brooks (client portal)**

7. Sees the released report and the **Workbook** (Excel with live formulas). Nothing internal, nothing of other clients.

### Monitoring tour on the existing portfolio (26 facilities, Calderwood, AI permitted)

Open `/monitoring` as **Priya Raman** and walk the left menu in order:
*Portfolio* (26 facilities, filters, a facility's document schedule) › *Submissions* (channels, deadlines, a late servicer report, CLO daily feeds) › *Mapping* (stored mapping reused, one changed layout confirmed, layout library) › *Validation* (warnings logged; a held load) › *Reconciliation* (27 missing loans; an identifier change) › *Terms* › *Covenants* (CCC excess, obligor leverage, investor exclusion) › *Exceptions* (every finding decided; expert judgement goes to Ruth Adeyemi and back) › *Reports* (QC variance blocks release; workbook provisional to released) › *Alerts* (headroom, early warnings, a client's alert drafted and back-tested) › *Status calls* (weekly brief per client) › *Metrics* (**20 of 20** planted issues found, **0 of 8** noise raised, **49 of 49** values right).

---

## Part 3. Onboarding a client that does not permit AI (Kingsgate, Fenwick SME deal)

Say it plainly: this client is **outside the AI scope** and stays on the existing process. The workbench still does the work, with code checks and templates, and makes no model calls.

**Alex Morgan**

1. *Clients* › **New client**. Name `Kingsgate Bank N.A.`, contact `Rosa Lind`, AI: **Not permitted: existing process, outside AI scope**. **Create client**.

**Hannah Cole**

2. Open the client › **New case**. Facility `Fenwick SME Funding LLC`, deal type *SME loans*, commitment `80000000` › **Open case**.
3. *Documents*: set Type to *agreement* and choose `Fenwick_Receivables_Financing_Agreement.pdf`; set Type to *loan tape* and choose `Fenwick_Portfolio_2026-09.xlsx` (from `fenwick-onboarding.zip`). **Classify with AI is disabled** and the "Existing process — outside AI scope" badge shows.
4. *Terms*: **Start manual entry**. For each term, **Enter** a value, choose the document and the page.
   - Facility limit `US$80,000,000`, page 1: code answers **"This value is not on page 1"**. Change the page to 2 › **Save and approve**.
   - Advance rate `70.00%`, page 2. Delinquency trigger `7.50%`, page 3.
   - Click **Not in documents** on the rest.
   - *Reporting*: **Record requirements**.
5. *Rules*: **Add rule**. Clause reference `First Schedule (a)`; plain English `Not more than 30 days in arrears`; clause text `the loan is not more than 30 days in arrears;`; field `days_past_due`; threshold `30` › **Check and add** (code confirms the clause is on the page) › **Approve rule set**.
6. *Mapping*: **Suggest mapping** (name matching, no AI) › **Confirm and store**.
7. *Validation*: date `2026-09-30` › **Validate and run**. Borrowing base appears; the case shows **model cost US$0.00**.
8. *Client model*: the client has none, so **Build client model** (Oxane builds it in code from the approved terms; notes come from a code template) › **Send to client for validation**. Work the exceptions with **Accept**.

**Rosa Lind (client contact)**

9. Portal: open "The model Oxane built for you" › answer "The model matches how we calculate the base." › **Confirm the model**.

**Hannah Cole, then Tom Fairley, then Marcus Hale**

10. *Client model* › **Close: model agreed**. *QC* › **Submit for QC**. Tom: **Agrees** on each line › **Complete QC**. Marcus: **Approve** › **Go live**.

## Part 4. Monitoring for a client that does not permit AI

- **Thornbury (existing portfolio, three approval levels).** In `/monitoring` as Priya, filter by client. A Thornbury report needs **three levels**: Priya prepares, Marcus Hale approves level 2, **Elena Varga (Head of monitoring)** releases at level 3. Its status-call brief is a code template. Open *Agents* (left menu, bottom) › the run log: Thornbury's calls are **refused at zero cost**.
- **Fenwick first month (new deal).** As Priya: facility › **Open** › upload `Fenwick_Portfolio_2026-10.xlsx` and `Fenwick_Monthly_Report_October_2026.pdf` (from `fenwick-monthly.zip`) › **Map tape** › same validation, hold, **Re-run calculations**, **Draft report** (code template) › levels 1 and 2 › released. **This month is covered by the API tests but has not been run in the browser on the hosted app: do a dry run first.**

## Closing points

- The AI reads, maps, suggests and drafts. **Code computes every number**, and every figure is checked against its quote.
- Reports stay provisional until every approval level is done. Whoever prepared work cannot approve it.
- Every action is in the hash-chained audit trail.
- Administrator › *Settings* › *AI provider* is where the key is set and tested.
