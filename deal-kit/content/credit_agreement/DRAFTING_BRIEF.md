# Drafting brief: synthetic credit agreement

This is fictional text for a software demo. It must read like a real US middle-market auto warehouse credit agreement, governed by New York law, between a special purpose borrower and one bank lender.

The clauses that drive calculations are already written in `core.txt` and `defs_core.txt`. Read both before you write anything. Never contradict them, and never restate their numbers.

## Parties and terms you may use

Use these placeholders exactly, including the double braces: `{{borrower}}`, `{{parent}}`, `{{lender}}`, `{{servicer}}`, `{{threshold_amount}}`.

Capitalised terms used across the agreement: Agreement, Borrower, Lender, Servicer, Parent, Verification Agent, Administrative Agent (the Lender acts as administrative agent), Closing Date, Transaction Documents, Fee Letter, Servicing Agreement, Security Agreement, Purchase Agreement, Obligations, Collateral, Collections, Collection Account, Receivable, Pool, Pool Receivable, Defaulted Receivable, Obligor, Dealer, Financed Vehicle, Originator, Loan Tape, Servicer Report, Responsible Officer, Subsidiary, Affiliate, Debt, Lien, Permitted Lien, GAAP, Term SOFR, Interest Period, Insolvency Event, Change of Control, Servicer Default, Material Adverse Effect.

## Hard rules

1. No dollar amounts and no percentages. If a threshold is needed, use `{{threshold_amount}}` or reword to avoid one. Day and Business Day periods are fine.
2. Do not name any real company, person, or court case. Statutes such as the UCC, the Investment Company Act and the Truth in Lending Act are fine.
3. Do not define or restate: eligibility criteria, concentration limits, advance rate, margin, reserve, facility limit, financial covenants, delinquency trigger, reporting deadlines, or dates. Refer to the relevant Section or Schedule instead.
4. Refer to other sections only by these numbers, and only numbers that exist in the section map below.
5. Use real legal drafting: long sentences, provisos and "provided that", nested (a), (b), (i), (ii). Vary the length of sections. Avoid filler and repetition, because a credit expert will read this.

## File format

Plain UTF-8 text.

```text
## 5.3 Title of Section
First paragraph of the section.

(a) A lettered paragraph. Leave a blank line between paragraphs.

(i) A roman paragraph under (a).
```

A definitions file has one definition per block, separated by a blank line, and each begins with the term in straight double quotes:

```text
"Collateral" has the meaning given in Section 2.9.

"Lien" means any mortgage, pledge, ...
```

Do not write article headings. Use only straight quotes and plain hyphens. Do not use markdown bold.

## Section map

| Article | Sections |
|---|---|
| 1 Definitions | 1.1 Defined Terms; 1.2 Rules of Interpretation; 1.3 Accounting Terms; 1.4 Computation of Time |
| 2 The Facility | 2.1 The Commitment*; 2.2 Advances and Borrowing Procedure; 2.3 Advance Rate*; 2.4 Borrowing Base Deficiency; 2.5 Prepayments and Commitment Reduction; 2.6 Interest*; 2.7 Interest Periods and Payment Dates*; 2.8 Fees; 2.9 Security; 2.10 Collections and Application of Funds; 2.11 Benchmark Replacement; 2.12 Increased Costs; 2.13 Taxes; 2.14 Payments Generally |
| 3 Conditions | 3.1 Conditions to Closing; 3.2 Conditions to Each Advance; 3.3 Conditions to Release of Collateral; 3.4 Determinations |
| 4 Representations | 4.1 Organization and Good Standing; 4.2 Power and Authority; 4.3 Enforceability; 4.4 No Conflict; 4.5 Litigation; 4.6 Compliance with Law; 4.7 Financial Statements; 4.8 No Material Adverse Effect; 4.9 Taxes; 4.10 Investment Company; 4.11 Solvency; 4.12 Special Purpose Status; 4.13 Title to Collateral; 4.14 Perfection; 4.15 Receivables Representations; 4.16 Dealer Agreements; 4.17 Consumer Laws; 4.18 Sanctions and Anti-Corruption; 4.19 Accuracy of Information; 4.20 Accounts |
| 5 Affirmative Covenants | 5.1 Existence; 5.2 Compliance with Law; 5.3 Books and Records; 5.4 Inspection and Field Examinations; 5.5 Delivery of Reports; 5.6 Notice of Certain Events; 5.7 Taxes; 5.8 Insurance; 5.9 Collateral Maintenance; 5.10 Servicing; 5.11 Credit and Collection Policy; 5.12 Collection Account; 5.13 Hedging; 5.14 Further Assurances; 5.15 Separateness; 5.16 Use of Proceeds |
| 6 Negative Covenants | 6.1 Debt; 6.2 Liens; 6.3 Mergers and Fundamental Changes; 6.4 Dispositions; 6.5 Investments; 6.6 Restricted Payments; 6.7 Transactions with Affiliates; 6.8 Business Activities; 6.9 Amendments to Documents; 6.10 Change of Accounts; 6.11 Credit Policy Changes; 6.12 Financial Covenants*; 6.13 Sanctions; 6.14 Subsidiaries; 6.15 Fiscal Year |
| 7 Performance Triggers | 7.1 Delinquency Trigger*; 7.2 Servicer Termination; 7.3 Replacement Servicer; 7.4 Cash Dominion; 7.5 Effect of Cure |
| 8 Default | 8.1 Events of Default*; 8.2 Remedies; 8.3 Application of Proceeds; 8.4 Waivers |
| 9 Agents | 9.1 Appointment; 9.2 Delegation; 9.3 Exculpation; 9.4 Reliance; 9.5 Notice of Default; 9.6 Indemnification; 9.7 Resignation; 9.8 Verification Agent; 9.9 Reports of the Verification Agent; 9.10 Fees of the Verification Agent |
| 10 Miscellaneous | 10.1 Amendments and Waivers; 10.2 Notices*; 10.3 Costs and Expenses; 10.4 Indemnity; 10.5 Assignments; 10.6 Set-Off; 10.7 Severability; 10.8 Counterparts; 10.9 Governing Law*; 10.10 Jurisdiction; 10.11 Waiver of Jury Trial; 10.12 Confidentiality; 10.13 Patriot Act; 10.14 Non-Petition; 10.15 Limited Recourse; 10.16 Entire Agreement |

Sections marked * are already written. Do not write them.

Schedules: Schedule 1 Eligibility Criteria; Schedule 2 Concentration Limits; Schedule 3 Reporting Requirements; Schedule 4 Restricted Jurisdictions. Annex A Commitment Schedule. Exhibit A Form of Borrowing Base Certificate; Exhibit B Form of Advance Request; Exhibit C Form of Compliance Certificate.

Only refer to Schedule 4 through the term Restricted Jurisdiction.
