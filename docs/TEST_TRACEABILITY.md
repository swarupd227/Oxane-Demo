# Oxane Workbench: requirements to test evidence

Built 23 Nov 2026 on branch `pitch-brief`, read-only against the code. The requirements come from `docs/DEMO_FEATURES.md` (every bullet), `docs/PITCH_BRIEF_GAPS.md` (Use Case 1 and 2 steps, measures 5b, data handling, RFP review notes) and the brief steps summarised there. Compound bullets are split into atomic rows. Evidence comes from reading the test bodies, not their names.

## How to read it

**Level:** U = unit (engine, deal kit, web vitest, or a pure function in the API suite); A = API (FastAPI TestClient against the real app and database); E = browser e2e (Playwright clicks the UI, local stack); Z = run against the hosted Azure app.

**Strength:** *Verified* = a test asserts the actual outcome. *Weak* = a test touches it but does not assert the outcome, or only through the stub model, or only the happy path. *None* = no test.

**AI path tags:** [stub] = deterministic test double (`app.deals.stub`, `DEALS_STUB_MODEL`), built to give correct answers, so it says nothing about how well the model reads documents. [rec] = real model output recorded earlier and replayed with no key. [live] = live model call.

**Evidence aliases:** `api:x` = `services/api/tests/test_x.py`; `eng:x` = `packages/engine/tests/test_x.py`; `kit:x` = `deal-kit/tests/test_x.py`; `web:x` = `apps/web/src/**/x.ts`; `e2e:x` = `tests/e2e/specs/x.spec.ts`; `azure:"1c"` = a test in `tests/e2e/specs/azure-gaps.spec.ts` (untracked, still being edited).

**Azure evidence:**
- Harbourline consumer deal, run end to end on Azure through the API on 23 Nov. Onboarding AI calls were replayed from recordings and the month report was drafted live. This was a manual run with no test in the repo, so it is cited only in PLT-04 and UC1-58.
- `azure-gaps.spec.ts`, run `kxrzf` on 23 Nov and still in progress when this was written. Steps 1a to 1j passed against the hosted app with the live model. That covers:
  - a new three-level client with a region override;
  - live classify;
  - live extract (13 terms, quotes verified, reserve reported missing rather than invented);
  - live rule drafting (10 rules, all passing the code check);
  - live mapping honouring the override;
  - validation;
  - a query answered in the portal;
  - Ruth deciding an escalation from her queue.
- **Step 1k failed:** after clicking "Close with this answer", the answered query and the decided escalation stayed `answered`/`decided`. Steps 1l to 5 (QC, approval, go-live, UI CRUD, the first monitoring month, the no-AI client, a fresh Harbourline month) have not run yet. Rows mark them `Z-pass`, `Z-FAIL` or `Z-pending`. Only `Z-pass` counts toward Level Z and Strength.

**Other caveats:**
- e2e `deals (a)` and `(b)` run only when the API has `DEALS_STUB_MODEL=1` or a live key with `E2E_LIVE=1`. Otherwise they are skipped.
- In the last full local rehearsal (`tests/e2e/rehearsal-full.log`), 62 tests passed. `deals (c)` failed on a strict-mode locator and passed on rerun.
- The monitoring, casework and agents run-log API tests skip when the recorded fixtures (`fixtures/cycle/cycle.json` and so on) are absent. They are present on this branch.

## Summary

### Counts by area

Level columns count the rows with evidence at that level; a row can count under several levels.

| Area | Rows | Verified | Weak | None | Unit | API | Browser e2e | Azure (passed) | No test | Azure spec pending |
|---|---|---|---|---|---|---|---|---|---|---|
| UC2 steps 1-7, portfolio | 68 | 54 | 8 | 6 | 26 | 49 | 1 | 2 | 6 | 1 |
| UC2 worked scenarios | 18 | 18 | 0 | 0 | 16 | 14 | 0 | 0 | 0 | 0 |
| UC2 scorecard and 5b | 13 | 8 | 5 | 0 | 0 | 13 | 0 | 0 | 0 | 0 |
| UC2 new deal, first month | 8 | 4 | 4 | 0 | 0 | 8 | 5 | 0 | 0 | 3 |
| UC1 steps 1-7, cases list | 40 | 36 | 4 | 0 | 14 | 35 | 10 | 0 | 0 | 0 |
| UC1 5b measures | 9 | 6 | 3 | 0 | 0 | 9 | 1 | 0 | 0 | 0 |
| UC1 new deal onboarding | 26 | 23 | 3 | 0 | 0 | 26 | 17 | 11 | 0 | 8 |
| Personas | 18 | 11 | 5 | 2 | 2 | 11 | 11 | 3 | 2 | 3 |
| Agents | 16 | 10 | 4 | 2 | 10 | 4 | 0 | 0 | 2 | 2 |
| Admin | 11 | 8 | 1 | 2 | 3 | 8 | 4 | 2 | 2 | 2 |
| Platform | 14 | 9 | 3 | 2 | 3 | 3 | 5 | 1 | 2 | 0 |
| Safety controls | 19 | 18 | 1 | 0 | 6 | 17 | 2 | 0 | 0 | 0 |
| **Total** | **260** | **205** | **41** | **14** | **80** | **197** | **56** | **19** | **14** | **19** |

### What the counts hide

- **Use Case 2 is shown first but has almost no browser coverage.** Of the 107 UC2 rows, 99 cover the scripted cycle, the worked scenarios and the measures, and only one of those (UC2-14) has a browser test. No Playwright test opens any `/monitoring/*` screen (submissions, mapping, validation, triage, pack, covenants, status call, results) except to check that a client is redirected to the portal. The UC2 controls are well verified at API and engine level, on recorded model output.
- **The Use Case 1 brief screens have no browser test.** Definitions, client model, query tracker, backbook, QC and configuration are verified through the API only. The scripted case 0412 screens (intake to scorecard) are well covered in the browser.
- **The new-deal AI path is verified in CI only through the stub.** The live path depends on the Azure run, which has passed onboarding through 1j and failed at 1k.
- **The Agents console is verified as a registry and run log only.** No browser test opens `/agents`.

### Top 20 untested or weakly tested requirements for the live pitch

Ordered by what will be demonstrated to Oxane's operational staff and what would embarrass if it broke.

1. **Monitoring workbench screens (UC2 steps 1-7, PLT-10).** No browser test opens any `/monitoring/*` screen: submissions, mapping, validation, triage, pack, covenants, status call and results are all untested in the browser. Every UC2 control is API-verified only, and accessibility and sideways-scroll checks cover onboarding screens only.
2. **Closing an answered query or decided escalation (UC1-75).** This failed on Azure in run kxrzf (step 1k): after clicking Close, both items stayed open. It blocks the UI path to QC, approval and go-live for a new deal. The cause, app or spec, is not yet established.
3. **Live-drafted month report text for a new deal (UC2-105).** CI checks stub text only. The Azure checks for unfilled slots, off-topic text and a stated trigger status (steps 3b and 5) have not run.
4. **Client self-service alert from typed plain English (UC2-57).** Only recorded preset requests work. A newly typed request is refused (422) in replay, and nothing has been tested against the live model.
5. **Monthly changed-layout mapping by live AI (UC2-15).** Verified only with the stub. Azure step 3a is pending.
6. **Three-level release for a new client, with nothing internal visible in the portal (UC2-107, PER-17).** Azure steps 3c and 3d are pending. CI covers two levels with the stub.
7. **Monitoring scorecard: 20/20 issues, 0/8 noise, 49/49 values (UC2-87 to 89).** API-only. The screen is never opened in a test, the Azure figures were checked by hand, and the number 49 is not asserted.
8. **Agents console screens (AGT-16, AGT-01, AGT-07).** No browser assertion on the agent list, graph, coverage matrix or run log. The 11 agent and 5 engine names are not asserted, and purpose, inputs and outputs are untested.
9. **Live calls appearing in the run log (AGT-13).** Only a synthetic row is tested. A real live deal step writing a row with tokens and cost is untested.
10. **Edit and archive a case in the UI, each in the case history (UC1-55 to 57).** The Azure spec falls back to the API if no control is found. The archived state and the replace, remove and archive audit entries are not asserted in CI.
11. **UC1 brief screens: definitions, client model, query tracker, backbook, QC and configuration workbook download (UC1-14, 18, 21, 27, 31, 35).** API-verified on recorded output, never opened in a browser. The stated figures (23 terms, 13 QC lines, 9.5 h against 74 h) are not asserted.
12. **Mapping library (UC2-19 to 21).** The 22 layouts, version history and the facilities using each layout are untested. Only the Ravenglass layout counts are checked.
13. **Status-call brief completeness (UC2-66, PER-15).** The early-warnings section is not asserted, and the brief in the client portal is untested.
14. **Client portal alerts and cross-client isolation (PER-16, PER-18).** No test that a client cannot see another client's queries or reports in the portal.
15. **US$10 daily spend cap (SAF-12).** The cap value and the hosted setting are not tested. The refusal itself is verified with a seeded US$1,000 spend.
16. **Oxane standard model and raw data retention (UC2-16, UC2-17).** No test at all. Operational staff are likely to ask.
17. **Exception owners and per-finding history (UC2-29, UC2-30).** Owners are not asserted, and history is checked only as the last audit entry.
18. **My work item age and notification bell contents (PER-06, PER-10).** Untested. The bell is only checked as visible.
19. **Administrator set-up of clients beyond creation (ADM-09 to 11).** Master-field overrides have no CI test (only the Azure run). Editing a client and managing users are untested.
20. **Monitoring arithmetic and schedules a domain expert may probe (UC2-45, UC2-103, UC2-06, UC2-09):**
    - obligor interest cover is never failed or asserted;
    - new-deal trigger results are not asserted;
    - schedule format and frequency are not asserted;
    - late-file chasing is tested only as notice text.

Also worth a check before the pitch, though not in the top 20:
- the sample zips at `/samples/*.zip` are untested (PLT-08);
- presenter mode is tested on onboarding only (PLT-07);
- thresholds flowing from the validated configuration into monitoring are untested (UC1-34);
- the new-deal lender workbook contents are untested (UC2-106);
- `deals (c)` failed once on a strict-mode locator.

## Matrix

| ID | Area | Requirement | Evidence | Level | Strength | Gap / what's missing |
|---|---|---|---|---|---|---|
| UC2-01 | UC2 portfolio | 26 facilities in the monitoring book (6 worked + 20 rest of book) | api:monitoring_brief::test_the_rest_of_the_book_is_worked_out_by_code_and_within_every_limit (20 book facilities, disjoint from worked); web:cycle.test "cover all six worked facilities" | U, A | Verified | Total of 26 never asserted in one place; no browser test of the facility list |
| UC2-02 | UC2 portfolio | Calderwood: AI permitted, two approval levels | api:monitoring_brief::test_calderwood_needs_two_levels; ::test_the_no_ai_client_makes_no_model_calls_and_gets_rule_suggestions (calderwood calls > 0) | A | Verified | - |
| UC2-03 | UC2 portfolio | Thornbury: no AI, three approval levels | api:monitoring_brief::test_thornbury_needs_a_third_level_from_a_different_person; ::test_the_no_ai_client_makes_no_model_calls_and_gets_rule_suggestions | A | Verified | - |
| UC2-04 | UC2 portfolio | Five asset classes covered (auto ABF, consumer/equipment ABF, fund finance NAV + sub line, CLO/BSL, middle-market back-leverage) | api:review_scenarios::test_every_facility_has_a_schedule_from_its_template (asserts only "CLO / BSL" and "Middle-market" templates) | A | Weak | Other three asset-class labels not asserted anywhere |
| UC2-05 | UC2 s1 | Expected-documents schedule per facility from its asset-class template | api:review_scenarios::test_every_facility_has_a_schedule_from_its_template | A | Verified | No UI test of the schedule screen |
| UC2-06 | UC2 s1 | Schedule lines carry document, format, frequency, channel, internal deadline | api:review_scenarios::test_every_facility_has_a_schedule_from_its_template (document, status only); api:monitoring_brief::test_submissions_carry_channel_deadline_and_consented_reuse (channel, deadline on submissions) | A | Weak | Format and frequency columns never asserted |
| UC2-07 | UC2 s1 | Channel per submission: email, SFTP, API, data room, upload | api:monitoring_brief::test_submissions_carry_channel_deadline_and_consented_reuse | A | Verified | - |
| UC2-08 | UC2 s1 | Internal deadline on or after due date per submission | api:monitoring_brief::test_submissions_carry_channel_deadline_and_consented_reuse | A | Verified | - |
| UC2-09 | UC2 s1 | Late files chased | web:desk.test "raises overdue files..." (notice text only) | U | Weak | No API test that a chase is generated/recorded for a late file; no UI test |
| UC2-10 | UC2 s1 | Prior-period data reused only with recorded client consent | api:monitoring_brief::test_submissions_carry_channel_deadline_and_consented_reuse | A | Verified | Refusal of reuse without consent not tested (happy path only) |
| UC2-11 | UC2 s1 | CLO daily feeds (positions, prices, ratings) checked day by day | eng:review_scenarios::test_daily_feeds_find_the_late_file_and_the_gap; api:review_scenarios::test_the_clo_daily_feeds_flag_one_late_day_and_one_gap | U, A | Verified | No UI test |
| UC2-12 | UC2 s1 | Missing CLO price day (21 May) flagged and queried | api:review_scenarios::test_the_clo_daily_feeds_flag_one_late_day_and_one_gap; kit:cycle::test_larkspur_daily_feeds_have_one_gap_and_month_end_matches | U, A | Verified | - |
| UC2-13 | UC2 s1 | Late position file (14 May, complete) flagged and logged, not raised | api:review_scenarios::test_the_clo_daily_feeds_flag_one_late_day_and_one_gap | A | Verified | - |
| UC2-14 | UC2 s2 | Stored mapping reused when the layout is unchanged, no AI | api:monitoring_brief::test_mapping_memory_is_scoped_to_each_client (northmoor unchanged, ai_used false); api:deals::test_first_month_reuses_the_mapping_holds_the_duplicate_and_reconciles (source "facility"); e2e:deals "(b)" ("Layout unchanged ... no AI") | A, E | Verified | e2e (b) runs only with stub model or E2E_LIVE; no UI test on the scripted cycle |
| UC2-15 | UC2 s2 | AI maps only the changed columns | api:deals::test_sme_layout_change_is_mapped_and_stored_per_client (changed_columns = 3) [stub]; Z-pending azure:"3a" [live] | A, Z | Weak | CI uses the stub; Azure onboarding mapping (1f) passed live, but the changed-layout monthly mapping (3a) has not run yet |
| UC2-16 | UC2 s2 | Oxane standard model (portfolio, facility, loan, test, stratification) | - | - | None | No test names or checks the five-level standard model |
| UC2-17 | UC2 s2 | Raw data kept alongside the mapped data | - | - | None | No test |
| UC2-18 | UC2 s2 | Client master-field overrides applied in mapping | api:monitoring_brief::test_mapping_memory_is_scoped_to_each_client (Larkspur override "lower_of"); Z-pass azure:"1a","1f" (region override on a new client) | A, Z | Verified | New-deal overrides (set in the client form, honoured by mapping) have no CI test; only the pending Azure spec |
| UC2-19 | UC2 s2 | Mapping library: 22 layouts with counts | api:review_scenarios::test_every_obligor_document_is_in_a_stored_layout (Ravenglass LAY-060 counts only) | A | Weak | Total of 22 layouts never asserted |
| UC2-20 | UC2 s2 | Mapping library: version history per layout | - | - | None | No test |
| UC2-21 | UC2 s2 | Mapping library: which facilities use each layout | - | - | None | No test |
| UC2-22 | UC2 s3 | Rule families: missing data, duplicates, reference data, data types, logical, prior-period change | api:monitoring_brief::test_validation_runs_every_rule_family_with_blocking_and_warning_rules; eng:brief_checks::test_bramble_warnings_are_found_and_do_not_block | U, A | Verified | Asserts families exist, not which rows each family catches (except duplicates/warnings) |
| UC2-23 | UC2 s3 | Each rule marked blocking or warning | api:monitoring_brief::test_validation_runs_every_rule_family_with_blocking_and_warning_rules | A | Verified | - |
| UC2-24 | UC2 s3 | Warnings do not hold the load | eng:brief_checks::test_bramble_warnings_are_found_and_do_not_block | U | Verified | - |
| UC2-25 | UC2 s3 | A blocking duplicate holds the load until resolved | api:monitoring_brief::test_a_blocking_failure_holds_the_northmoor_pack_until_resolved; eng:brief_checks::test_the_repeated_northmoor_line_blocks_the_load_and_collapses_on_resolution | U, A | Verified | No UI test on the scripted cycle |
| UC2-26 | UC2 s3 | Resolving a block needs a note | api:monitoring_brief::test_a_blocking_failure_holds_the_northmoor_pack_until_resolved (409 without note) | A | Verified | - |
| UC2-27 | UC2 s3 | Prior-period jump explained by the AI from a quoted line in the servicer commentary | api:monitoring_brief::test_the_prior_period_change_is_explained_with_a_found_quote [rec]; eng:brief_checks::test_bramble_pool_change_against_april_is_flagged | U, A | Verified | Recorded model output only |
| UC2-28 | UC2 s4 | One exceptions queue with unique IDs | api:monitoring_brief::test_findings_and_submissions_carry_references_and_dates | A | Verified | - |
| UC2-29 | UC2 s4 | Exceptions carry owners | - | - | None | Owner field never asserted |
| UC2-30 | UC2 s4 | Exceptions carry history (audit per finding) | api:monitoring_brief::test_audit_entries_name_the_record_they_touch | A | Weak | Only the last audit entry's subject is checked, not a per-finding history view |
| UC2-31 | UC2 s4 | AI suggests an outcome, the analyst decides | api:monitoring::test_changing_a_suggested_outcome_needs_a_reason; api:monitoring_brief::test_the_prior_period_change_is_explained_with_a_found_quote (suggested by AI) [rec] | A | Verified | No UI test |
| UC2-32 | UC2 s4 | For a no-AI client a rule suggests the outcome | api:monitoring_brief::test_the_no_ai_client_makes_no_model_calls_and_gets_rule_suggestions; api:review_scenarios::test_the_subscription_line_runs_on_code_only | A | Verified | - |
| UC2-33 | UC2 s4 | Changing a suggested outcome needs a reason | api:monitoring::test_changing_a_suggested_outcome_needs_a_reason | A | Verified | - |
| UC2-34 | UC2 s4 | Harmless differences logged with a reason | api:monitoring::test_noise_is_logged_by_rule_with_a_reason | A | Verified | - |
| UC2-35 | UC2 s4 | A pack cannot be approved until every finding is decided | api:monitoring::test_a_pack_cannot_be_approved_until_its_findings_are_decided | A | Verified | - |
| UC2-36 | UC2 s4 | Reports stay provisional until every approval level is complete | api:monitoring_brief::test_thornbury_needs_a_third_level_from_a_different_person; ::test_workbook_download_says_provisional_until_released | A | Verified | No UI test of the provisional label on the scripted cycle; Z-pending azure:"3b" checks it on a new deal |
| UC2-37 | UC2 s4 | The approver cannot triage; an approved pack locks its findings | api:monitoring::test_the_preparer_cannot_approve_and_the_approver_cannot_triage; ::test_an_approved_pack_locks_its_findings | A | Verified | - |
| UC2-38 | UC2 s5 | Borrowing base computed by the engine | eng:monitoring::test_bramble_borrowing_base_matches_the_key_and_the_certificate; eng:brief_checks::test_larkspur_ccc_excess_and_borrowing_base_match_the_key; eng:review_scenarios::test_obligor_covenants_and_the_borrowing_base_match_the_key; ::test_the_subscription_line_matches_the_key | U | Verified | - |
| UC2-39 | UC2 s5 | Triggers (rolling delinquency) computed | eng:monitoring::test_northmoor_delinquency_is_an_early_warning_and_june_what_if_breaches; api:monitoring_brief::test_a_book_delinquency_average_is_recomputed_from_the_reported_figures | U, A | Verified | - |
| UC2-40 | UC2 s5 | Covenants computed | eng:monitoring::test_leverage_passes_as_reported_and_breaches_with_the_guarantee; eng:answer_key::test_covenants_match_the_key | U | Verified | - |
| UC2-41 | UC2 s5 | Concentration limits computed | eng:answer_key::test_concentration_rule_matches_the_key; eng:monitoring::test_kestrel_nav_tests (position concentration) | U | Verified | - |
| UC2-42 | UC2 s5 | NAV loan-to-value computed (with markdown) | eng:monitoring::test_kestrel_nav_tests | U | Verified | - |
| UC2-43 | UC2 s5 | CCC excess computed | eng:brief_checks::test_larkspur_ccc_excess_and_borrowing_base_match_the_key | U | Verified | - |
| UC2-44 | UC2 s5 | Obligor leverage computed | eng:review_scenarios::test_obligor_covenants_and_the_borrowing_base_match_the_key; ::test_the_reported_leverage_differs_only_by_truncation | U | Verified | - |
| UC2-45 | UC2 s5 | Obligor interest cover computed | eng:review_scenarios::test_obligor_covenants_and_the_borrowing_base_match_the_key (ICR is an input to check_obligor) | U | Weak | No obligor fails or nears interest cover; the ICR value is never asserted |
| UC2-46 | UC2 s5 | Investor eligibility computed (rating floor) | eng:review_scenarios::test_investor_classes_follow_the_rating_floor | U | Verified | - |
| UC2-47 | UC2 s5 | Lender Excel workbook with live formulas | api:monitoring_brief::test_workbook_formulas_give_the_platform_figures (6 facilities); api:review_scenarios::test_review_workbooks_carry_formulas_and_source_notes | A | Verified | Formulas checked to start with "="; values matched to platform figures for 2-3 lines per facility |
| UC2-48 | UC2 s5 | Source note on every input cell | api:monitoring_brief::test_workbook_formulas_give_the_platform_figures | A | Verified | - |
| UC2-49 | UC2 s5 | Compared with an independent QC workbook | api:monitoring_brief::test_workbook_formulas_give_the_platform_figures ("QC comparison" sheet); ::test_qc_variances_are_classified_and_a_genuine_one_holds_release | A | Verified | - |
| UC2-50 | UC2 s5 | Variances classed presentation (blank vs dash, rounding, sign, per cent vs decimal) or genuine | eng:brief_checks::test_qc_variances_are_classified (9 cases); api:monitoring_brief::test_qc_variances_are_classified_and_a_genuine_one_holds_release | U, A | Verified | - |
| UC2-51 | UC2 s5 | A genuine variance blocks release until resolved with a note | api:monitoring_brief::test_qc_variances_are_classified_and_a_genuine_one_holds_release | A | Verified | No UI test |
| UC2-52 | UC2 s6 | Covenant headroom across facilities | api:monitoring_brief::test_headroom_covers_every_facility; eng:brief_checks::test_headroom_warns_when_close_or_moving_towards_the_limit | U, A | Verified | No UI test of the headroom view |
| UC2-53 | UC2 s6 | Early warning: rating downgrades | eng:brief_checks::test_early_warnings_find_the_downgrade_and_the_price_fall | U | Verified | - |
| UC2-54 | UC2 s6 | Early warning: price moves | eng:brief_checks::test_early_warnings_find_the_downgrade_and_the_price_fall | U | Verified | - |
| UC2-55 | UC2 s6 | Early warning: rising trends | eng:brief_checks::test_headroom_warns_when_close_or_moving_towards_the_limit; api:monitoring_brief::test_headroom_covers_every_facility (trend "towards") | U, A | Verified | - |
| UC2-56 | UC2 s6 | Early warning: stale valuations | eng:monitoring::test_kestrel_nav_tests (Harlow 106 days) | U | Verified | - |
| UC2-57 | UC2 s6 | Client self-service alert: client asks in plain English, AI drafts the rule | api:monitoring_brief::test_preset_alert_is_drafted_checked_and_back_tested [rec, preset requests only]; ::test_an_unrecorded_request_is_refused_in_replay_and_thornbury_has_no_ai_alerts (free text refused 422 in replay) | A | Weak | Only recorded preset wording works in replay; a newly typed request has never been tested against the live model, and is refused if the hosted cycle runs in replay. No UI test |
| UC2-58 | UC2 s6 | Code checks the drafted alert rule | eng:brief_checks::test_alert_rules_are_checked_and_back_tested; api:monitoring_brief::test_preset_alert_is_drafted_checked_and_back_tested | U, A | Verified | - |
| UC2-59 | UC2 s6 | Code back-tests the alert on history | eng:brief_checks::test_alert_rules_are_checked_and_back_tested; api:monitoring_brief::test_preset_alert_is_drafted_checked_and_back_tested | U, A | Verified | - |
| UC2-60 | UC2 s6 | Alert goes live only after the analyst approves it | api:monitoring_brief::test_an_alert_goes_live_only_after_the_analyst_approves_it | A | Verified | - |
| UC2-61 | UC2 s6 | No AI alerts for the no-AI client | api:monitoring_brief::test_an_unrecorded_request_is_refused_in_replay_and_thornbury_has_no_ai_alerts | A | Verified | - |
| UC2-62 | UC2 s6 | What-if on a trigger | api:monitoring::test_what_if_june_breaches_above_the_threshold; eng:monitoring::test_northmoor_delinquency_is_an_early_warning_and_june_what_if_breaches | U, A | Verified | No UI test |
| UC2-63 | UC2 s7 | Lender pack drafted with every figure filled by code | api:monitoring::test_every_number_in_the_lender_packs_comes_from_code [rec] | A | Verified | No UI test |
| UC2-64 | UC2 s7 | Weekly status-call brief per client | api:monitoring_brief::test_status_briefs_have_no_model_written_numbers | A | Verified | No UI test |
| UC2-65 | UC2 s7 | Brief sections: missing data, open questions, exclusions, identifier changes, missing financials | api:monitoring_brief::test_status_briefs_have_no_model_written_numbers (first five headings) | A | Verified | - |
| UC2-66 | UC2 s7 | Brief section: early warnings | - | - | None | Test checks only the first five headings |
| UC2-67 | UC2 s7 | Brief has no model-written numbers | api:monitoring_brief::test_status_briefs_have_no_model_written_numbers | A | Verified | - |
| UC2-68 | UC2 data handling | No-AI client runs on the existing process (code only), shown in the portfolio | api:monitoring_brief::test_the_no_ai_client_makes_no_model_calls_and_gets_rule_suggestions; ::test_the_guard_refuses_any_model_call_for_or_about_the_no_ai_client | A | Verified | "Shown in the portfolio" not checked in UI |
| UC2-69 | UC2 scenario | 27 loans missing from a tape (roll-forward gap) | eng:monitoring::test_roll_forward_finds_the_gap_and_the_missing_loans; kit:cycle::test_the_missing_loans_are_on_the_april_tape_and_absent_in_may; api:review_scenarios::test_the_scorecard_scores_the_new_issues_and_keeps_the_old_ones (M1-M20 found) | U, A | Verified | - |
| UC2-70 | UC2 scenario | Servicer reports disagreeing on charge-offs (nine loans) | eng:monitoring::test_charge_off_schedule_names_the_nine_loans; scorecard test as UC2-69 | U, A | Verified | - |
| UC2-71 | UC2 scenario | Terms changed mid-year by amendment (terms in force by date) | eng:monitoring::test_may_uses_the_terms_in_force_before_amendment_2 (hand-built versions); scorecard test as UC2-69 | U, A | Verified | Unit test uses hand-built term versions, not the documents |
| UC2-72 | UC2 scenario | Delinquency trigger close to breach, with what-if | eng:monitoring::test_northmoor_delinquency_is_an_early_warning_and_june_what_if_breaches; api:monitoring::test_what_if_june_breaches_above_the_threshold | U, A | Verified | - |
| UC2-73 | UC2 scenario | Leverage depends on a guarantee (expert call) | eng:monitoring::test_leverage_passes_as_reported_and_breaches_with_the_guarantee; scorecard test as UC2-69 | U, A | Verified | Routing to expert not asserted directly |
| UC2-74 | UC2 scenario | One car (VIN) pledged to two facilities | eng:monitoring::test_one_vin_is_pledged_across_facilities_and_none_within; kit:cycle::test_the_shared_vin_is_on_both_may_tapes | U | Verified | - |
| UC2-75 | UC2 scenario | Duplicate loan row blocks a load | eng:brief_checks::test_the_repeated_northmoor_line_blocks_the_load_and_collapses_on_resolution; api:monitoring_brief::test_a_blocking_failure_holds_the_northmoor_pack_until_resolved | U, A | Verified | - |
| UC2-76 | UC2 scenario | CCC share 8.41% against 7.5%, haircut at market value | eng:brief_checks::test_larkspur_ccc_excess_and_borrowing_base_match_the_key; ::test_moodys_only_would_miss_the_split_rated_loan | U | Verified | - |
| UC2-77 | UC2 scenario | 14.75-point price drop flagged | eng:brief_checks::test_early_warnings_find_the_downgrade_and_the_price_fall (issuer matched to key M12) | U | Verified | Size of the move not asserted literally |
| UC2-78 | UC2 scenario | Identifier change linked, not booked as a trade | eng:brief_checks::test_identifier_change_is_linked_not_missing_and_new | U | Verified | - |
| UC2-79 | UC2 scenario | Middle-market obligor over its leverage covenant (out of the base) | api:review_scenarios::test_every_obligor_is_tested_and_the_breach_leaves_the_base; eng:review_scenarios::test_obligor_covenants_and_the_borrowing_base_match_the_key | U, A | Verified | Obligor figures come from the code fallback (portfolio report) until the model steps are recorded |
| UC2-80 | UC2 scenario | EBITDA add-backs over the cap go to expert judgement, with each reading | api:review_scenarios::test_add_backs_over_the_cap_go_to_an_expert_with_each_reading; eng:review_scenarios::test_the_add_back_cap_gives_three_readings | U, A | Verified | - |
| UC2-81 | UC2 scenario | Missing obligor financials excluded | api:review_scenarios::test_every_obligor_is_tested_and_the_breach_leaves_the_base | A | Verified | - |
| UC2-82 | UC2 scenario | Covenant waiver applied to its test dates, quote found | api:review_scenarios::test_the_waiver_sets_the_level_and_its_quote_is_found; eng:review_scenarios::test_a_waiver_applies_only_to_its_test_dates | U, A | Verified | Waiver read by a keyed code fallback, not the model, until recorded |
| UC2-83 | UC2 scenario | Subscription-line investor downgraded and excluded, forcing a prepayment | api:review_scenarios::test_the_downgrade_excludes_the_investor_and_forces_a_prepayment; eng:review_scenarios::test_the_subscription_line_matches_the_key | U, A | Verified | - |
| UC2-84 | UC2 scenario | Investor concentration over limit reduces the base | api:review_scenarios::test_the_downgrade_excludes_the_investor_and_forces_a_prepayment | A | Verified | - |
| UC2-85 | UC2 scenario | Capital call not posted to the investor register (queried) | api:review_scenarios::test_notices_reconcile_and_the_stale_register_entry_is_queried; kit:cycle::test_wharfedale_register_misses_the_downgrade_and_one_investor_posting | U, A | Verified | - |
| UC2-86 | UC2 scenario | Missing CLO price day | as UC2-12 | U, A | Verified | - |
| UC2-87 | UC2 scorecard | 20 of 20 planted issues found | api:review_scenarios::test_the_scorecard_scores_the_new_issues_and_keeps_the_old_ones; api:monitoring::test_scorecard_finds_every_planted_issue_and_raises_no_noise [rec] | A | Verified | No UI test of the monitoring scorecard; Azure figure is a manual check |
| UC2-88 | UC2 scorecard | 0 of 8 harmless items raised | as UC2-87 | A | Verified | - |
| UC2-89 | UC2 scorecard | 49 of 49 values correct | api:monitoring::test_scorecard_finds_every_planted_issue_and_raises_no_noise (found == total) | A | Verified | The number 49 is not asserted; three Ravenglass values are unscored (known limit) |
| UC2-90 | UC2 5b | Scorecard reports the eight brief measures by name | api:monitoring_brief::test_scorecard_reports_the_brief_measures_by_name | A | Verified | - |
| UC2-91 | UC2 5b | Accuracy and completeness of loaded updates and reconciliations | api:monitoring_brief::test_scorecard_reports_the_brief_measures_by_name | A | Verified | - |
| UC2-92 | UC2 5b | Material issues missed = 0 | api:monitoring_brief::test_scorecard_reports_the_brief_measures_by_name | A | Verified | - |
| UC2-93 | UC2 5b | False alerts per cycle = 0 | api:monitoring_brief::test_scorecard_reports_the_brief_measures_by_name | A | Verified | - |
| UC2-94 | UC2 5b | Hours per cycle, by mandate | same test (asserts an assumed value exists) | A | Weak | Value not checked |
| UC2-95 | UC2 5b | Turnaround time per cycle | same test (name only) | A | Weak | Value not checked |
| UC2-96 | UC2 5b | Processing cost per cycle | same test (name only) | A | Weak | Value not checked against the run log |
| UC2-97 | UC2 5b | Share of values linked to source, with audit trail | same test (name only) | A | Weak | Value not checked |
| UC2-98 | UC2 5b | Additional deals supportable per analyst | same test (name only) | A | Weak | Value not checked |
| UC2-99 | UC2 5b | Measured and assumed shown apart | api:monitoring_brief::test_scorecard_reports_the_brief_measures_by_name (assumed on hours; assumptions listed) | A | Verified | - |
| UC2-100 | UC2 s1 (new deal) | First month: tape and servicer report uploaded to the submission | api:deals::test_first_month_reuses_the_mapping_holds_the_duplicate_and_reconciles; e2e:deals "(b)" [stub]; Z-pending azure:"3a" | A, E | Verified | - |
| UC2-101 | UC2 s3 (new deal) | First month: duplicate account holds the load; report draft refused while held | api:deals::test_first_month_reuses_the_mapping_holds_the_duplicate_and_reconciles (422 on draft); e2e:deals "(b)" | A, E | Verified | - |
| UC2-102 | UC2 s3 (new deal) | First month: reconciliation (roll-forward gap, missing loan, collections) | api:deals::test_first_month_reuses_the_mapping_holds_the_duplicate_and_reconciles | A | Verified | - |
| UC2-103 | UC2 s5 (new deal) | First month: triggers computed | api:deals::test_first_month_reuses_the_mapping_holds_the_duplicate_and_reconciles (delinquency_window == 2 only) | A | Weak | Trigger value and pass/fail not asserted |
| UC2-104 | UC2 s4 (new deal) | First month: triage of findings | deals_flow.triage_all via api:deals::test_first_month_...; e2e:deals "(b)" [stub] | A, E | Weak | Takes the suggested outcome; suggestions come from the stub |
| UC2-105 | UC2 s7 (new deal) | First month: report drafted with figures filled by code | api:deals::test_report_released_after_the_client_s_levels (no "{{", "US$" present) [stub]; e2e:deals "(b)" [stub]; Z-pending azure:"3b","5" [live] (no unfilled slot, no off-topic text, trigger status stated) | A, E | Weak | Live-drafted report text not checked by any passing test; the Azure spec was added specifically to check it |
| UC2-106 | UC2 s5 (new deal) | First month: lender Excel workbook downloadable | api:deals::test_report_released_after_the_client_s_levels (client gets 200) | A | Weak | Contents (formulas, source notes) not checked for new-deal workbooks |
| UC2-107 | UC2 s4 (new deal) | First month: client's approval levels, then released to the portal | api:deals::test_report_released_after_the_client_s_levels; e2e:deals "(b)" [stub, 2 levels]; Z-pending azure:"3c","3d" (3 levels) | A, E | Verified | Three-level release for a new client only in the pending Azure spec |
| UC1-01 | UC1 cases list | 15 onboarding cases listed | e2e:drills "the case list opens another case's summary" (16 rows incl. header); api:cases::test_the_pipeline_holds_the_active_case_its_backbook_and_the_generated_cases (10-15) | A, E | Verified | - |
| UC1-02 | UC1 cases list | Five clients and deal types (auto ABF, consumer, SME, fund finance, CLO warehouse) | api:cases::test_the_pipeline_holds_the_active_case_its_backbook_and_the_generated_cases (deal types) | A | Verified | Five clients not asserted |
| UC1-03 | UC1 cases list | Stages Intake to Live | api:cases::test_case_0412_moves_through_the_stages_with_the_session; kit:casework::test_pipeline_counts_are_worked_out_and_consistent | U, A | Verified | - |
| UC1-04 | UC1 cases list | Four-deal backbook in the list | api:cases::test_the_pipeline_holds_the_active_case_its_backbook_and_the_generated_cases | A | Verified | - |
| UC1-05 | UC1 cases list | Totals are the sums of the rows | api:cases::test_totals_are_the_sums_of_the_rows | A | Verified | - |
| UC1-06 | UC1 s1 | Documents classified by type | api:recorded_run::test_replay_reproduces_the_recorded_run_with_no_client [rec]; e2e:flow (8 rows after intake) | A, E | Verified | - |
| UC1-07 | UC1 s1 | Documents classified by version and effective date | api:pipeline::test_advance_rate_keeps_both_versions (indirect) | A | Weak | No test asserts a document's version/effective date at intake |
| UC1-08 | UC1 s1 | Missing schedule found (Schedule 4) | api:pipeline::test_missing_schedule_is_found_by_code; e2e:flow "Intake" ("Expected but not received", "Schedule 4") | U, E | Verified | - |
| UC1-09 | UC1 s1 | Client's own model included in the pack | kit:casework::test_client_model_cells_hold_the_values_the_key_names; api:casework::test_client_model_differences_become_queries_with_code_filled_figures | U, A | Verified | No UI test of /client-model |
| UC1-10 | UC1 s1 | Reporting requirements included in the pack | api:casework::test_configuration_workbook_thresholds_match_their_sources_and_say_provisional ("Report lines" sheet exists) | A | Weak | No test that a reporting-requirements document is received and read |
| UC1-11 | UC1 s1 | Pack files recognised by content; stray or changed files named and refused | api:spec_gaps::test_each_pack_file_is_recognised_by_content_even_when_renamed; ::test_a_changed_file_is_refused; e2e:drills "the real pack is accepted when dropped", "a stray or missing file is named" | A, E | Verified | - |
| UC1-12 | UC1 s2 | Key terms with tier, confidence and source | api:workbench::test_workbench_has_every_seeded_section; ::test_every_text_citation_has_a_highlight; api:recorded_run::test_recorded_run_is_real_output_with_no_unexplained_items [rec]; e2e:flow "Terms" | A, E | Verified | - |
| UC1-13 | UC1 s2 | Amendment applied (both versions kept) | api:pipeline::test_advance_rate_keeps_both_versions; api:workbench::test_advance_rate_cites_both_documents; e2e:flow ("Amendment No. 1, 2(a)") | A, E | Verified | - |
| UC1-14 | UC1 s2 | Nested definitions traced, each quoted on its page, no cycles | api:casework::test_every_definition_is_quoted_on_its_page_and_the_chain_resolves [rec]; kit:casework::test_definitions_key_finds_every_definition_in_the_pack | U, A | Verified | Count of 23 not asserted (test asserts > 10); no UI test of /definitions |
| UC1-15 | UC1 s2 | Definition chain reproduces the borrowing base to the cent | api:casework::test_every_definition_is_quoted_on_its_page_and_the_chain_resolves (US$48,193,346.69) | A | Verified | - |
| UC1-16 | UC1 s2 | Tier 1 cannot be bulk approved; every sourced term must be approved | api:controls::test_tier_1_cannot_be_bulk_approved; ::test_every_sourced_term_must_be_approved_not_only_tier_1; ::test_approval_needs_every_tier_1_value | A | Verified | - |
| UC1-17 | UC1 s2 | A disagreeing second read lowers a Tier 1 value | api:pipeline::test_a_disagreeing_second_read_lowers_a_tier_1_value | U | Verified | Built from scripted model answers |
| UC1-18 | UC1 s3 | Client's model compared with the agreement; differences listed | api:casework::test_client_model_differences_become_queries_with_code_filled_figures [rec]; kit:casework::test_each_difference_is_worked_out_against_the_agreed_borrowing_base | U, A | Verified | No UI test |
| UC1-19 | UC1 s3 | Each difference costed (stale 85% overstates base by US$1.48m) | api:casework::test_client_model_differences_become_queries_with_code_filled_figures (1,478,462.91) | A | Verified | - |
| UC1-20 | UC1 s3 | Each difference turned into a client query with code-filled figures | api:casework::test_client_model_differences_become_queries_with_code_filled_figures | A | Verified | - |
| UC1-21 | UC1 s3 | Query tracker with sent and answered dates; no answer before sending | api:casework::test_query_tracker_splits_analyst_time_from_client_waiting | A | Verified | No UI test of /queries |
| UC1-22 | UC1 s3 | Elapsed time split into analyst time and client waiting time | api:casework::test_query_tracker_splits_analyst_time_from_client_waiting; ::test_business_hours_skip_nights_and_weekends | U, A | Verified | Stated figures (9.5 h / 74 h) not asserted |
| UC1-23 | UC1 s4 | Rules drafted from the agreement, each with clause and page | api:recorded_run::test_replay_reproduces_the_recorded_run_with_no_client [rec]; eng:rules::test_there_are_17_rules | U, A | Verified | - |
| UC1-24 | UC1 s4 | Impact preview of a rule edit | api:workbench::test_rule_preview_reports_the_change; eng:rules::test_impact_preview_shows_what_an_edit_would_change; e2e:flow "Rules" ("Loans becoming ineligible") | U, A, E | Verified | - |
| UC1-25 | UC1 s4 | Four-eyes on rule changes; pending change blocks approval | api:spec_gaps::test_preparer_cannot_decide_their_own_rule_change; api:controls::test_a_pending_rule_change_blocks_approval_until_a_reviewer_decides; e2e:drills "a second analyst can approve a rule change"; e2e:flow "Approve" (decline) | A, E | Verified | - |
| UC1-26 | UC1 s4 | Approved rule change moves the numbers; declined leaves them | api:spec_gaps::test_an_approved_rule_change_moves_the_numbers; ::test_a_declined_rule_change_leaves_the_numbers_alone | A | Verified | - |
| UC1-27 | UC1 s4 | Configuration workbook export (source field, loader field, expected output) | api:casework::test_configuration_workbook_thresholds_match_their_sources_and_say_provisional (sheets Field map, Report lines, Client conventions) | A | Verified | No UI download test for case 0412 |
| UC1-28 | UC1 s4 | Every threshold checked against its source quote | api:casework::test_configuration_workbook_thresholds_match_their_sources_and_say_provisional; ::test_an_approved_rule_change_shows_against_its_source | A | Verified | - |
| UC1-29 | UC1 s5 | Tape mapped to the bank's fields | api:spec_gaps::test_accepting_every_column_accepts_the_mapping; ::test_approval_needs_the_mapping_accepted; e2e:flow "Mapping" (38 columns) | A, E | Verified | - |
| UC1-30 | UC1 s5 | A mapping whose values do not fit the field is rejected | api:pipeline::test_mapping_rejects_a_column_whose_values_do_not_fit; api:ontology::test_a_mapping_whose_concept_disagrees_is_held_for_review | U | Verified | - |
| UC1-31 | UC1 s5 | Backbook batch loaded with the stored mapping | api:casework::test_backbook_loads_only_after_every_suggestion_checks_out; kit:casework::test_backbook_tapes_use_the_stored_layout_except_where_planted | U, A | Verified | No UI test of /backbook |
| UC1-32 | UC1 s5 | Backbook exceptions only where a deal differs | api:casework::test_backbook_loads_only_after_every_suggestion_checks_out (ashdown 0 exceptions) | A | Verified | - |
| UC1-33 | UC1 s5 | Leaving rows out is never accepted without an expert | api:casework::test_leaving_rows_out_is_never_accepted_without_an_expert | U | Verified | - |
| UC1-34 | UC1 s6 | Thresholds taken from the validated configuration, not typed | api:spec_gaps::test_an_approved_rule_change_moves_the_numbers (engine uses the approved rule set) | A | Weak | No test that the validated configuration feeds the monitoring facility's thresholds |
| UC1-35 | UC1 s7 | Independent QC comparison against the Excel calculation | api:casework::test_a_genuine_qc_variance_holds_the_report_until_resolved_and_released_by_a_reviewer; kit:casework::test_qc_workbook_has_two_genuine_variances_and_each_presentation_class | U, A | Verified | No UI test of /qc |
| UC1-36 | UC1 s7 | 13 QC lines classified | kit:casework::test_qc_workbook_has_two_genuine_variances_and_each_presentation_class | U | Weak | 13 never asserted; classes present asserted |
| UC1-37 | UC1 s7 | Two genuine variances block release until resolved | api:casework::test_a_genuine_qc_variance_holds_the_report_until_resolved_and_released_by_a_reviewer | A | Verified | - |
| UC1-38 | UC1 s7 | Resolution needs a listed reason; only a reviewer releases | same test (free-text resolution 409; preparer release 409) | A | Verified | - |
| UC1-39 | UC1 s7 | Reports provisional until QC passes, final after release | api:casework::test_configuration_workbook_thresholds_match_their_sources_and_say_provisional; ::test_a_genuine_qc_variance_... (config final after release) | A | Verified | - |
| UC1-40 | UC1 s7 | Load file only after approval, carries evidence and audit head | api:controls::test_load_file_needs_approval_and_carries_its_evidence; api:spec_gaps::test_load_file_carries_every_loan_and_section; e2e:flow "Approve" (2,400 loans downloaded) | A, E | Verified | - |
| UC1-41 | UC1 5b | Onboarding scorecard reports the eight brief measures by name | api:casework::test_scorecard_reports_the_brief_measures_by_name | A | Verified | - |
| UC1-42 | UC1 5b | Field-level accuracy against expert-verified records | api:casework::test_scorecard_reports_the_brief_measures_by_name (passed); api:controls::test_scorecard_reports_the_recorded_run; ::test_scorecard_catches_a_wrong_value; e2e:flow "Scorecard" | A, E | Verified | - |
| UC1-43 | UC1 5b | Material errors and omissions | api:controls::test_scorecard_catches_a_wrong_value | A | Verified | - |
| UC1-44 | UC1 5b | Exception rate | api:controls::test_scorecard_reports_the_recorded_run (10 of 10, 0 false positives) | A | Verified | - |
| UC1-45 | UC1 5b | Hours per onboarding by deal type (assumed) | api:casework::test_scorecard_reports_the_brief_measures_by_name | A | Weak | Only checks an assumed value exists |
| UC1-46 | UC1 5b | Elapsed time split from client waiting | as UC1-22 | A | Verified | - |
| UC1-47 | UC1 5b | Cost per onboarding | api:controls::test_scorecard_reports_the_recorded_run (0 < cost < 2) | A | Weak | Range only |
| UC1-48 | UC1 5b | Share of values linked to source; capacity released | api:casework::test_scorecard_reports_the_brief_measures_by_name (names only) | A | Weak | Values not checked |
| UC1-49 | UC1 5b | Scorecard claims nothing from seed data | api:controls::test_scorecard_claims_nothing_from_seed_data | A | Verified | - |
| UC1-50 | UC1 s1 (new deal) | Create an onboarding case, with inline validation | api:deals::test_case_crud_validates_inline_and_audits; e2e:deals "(a)","(c)" (openCase); Z-pass azure:"1b" | A, E, Z | Verified | - |
| UC1-51 | UC1 s1 (new deal) | Upload documents | api:deals::test_case_crud_validates_inline_and_audits; e2e:deals "(a)" ("5 active"), "(c)" | A, E, Z | Verified | - |
| UC1-52 | UC1 s1 (new deal) | Replace a document (new version) | api:deals::test_case_crud_validates_inline_and_audits (version 2); Z-pending azure:"2" (UI) | A | Verified | No CI browser test |
| UC1-53 | UC1 s1 (new deal) | Remove a document | api:deals::test_case_crud_validates_inline_and_audits; Z-pending azure:"2" (UI) | A | Verified | No CI browser test |
| UC1-54 | UC1 s1 (new deal) | Duplicate upload refused | api:deals::test_case_crud_validates_inline_and_audits (422) | A | Verified | - |
| UC1-55 | UC1 s1 (new deal) | Edit a case | api:deals::test_case_crud_validates_inline_and_audits (PATCH); Z-pending azure:"2" (soft check whether a UI control exists) | A | Verified | Browser: the Azure spec falls back to the API when no edit control is found, so a missing UI control would not fail it |
| UC1-56 | UC1 s1 (new deal) | Archive a case | api:deals::test_case_crud_validates_inline_and_audits (200 only); Z-pending azure:"2" (soft) | A | Weak | Archived state and its audit entry not asserted; UI control may not exist (same fallback as UC1-55) |
| UC1-57 | UC1 s1 (new deal) | Every create, edit, upload, replace, remove and archive is in the record's history | api:deals::test_case_crud_validates_inline_and_audits (first three event types, chain intact) | A | Weak | Replace, remove and archive entries not asserted in CI; azure:"2" soft-asserts them (pending) |
| UC1-58 | UC1 s1 (new deal) | AI classifies uploaded documents | api:deals (consumer fixture, classify) [stub]; e2e:deals "(a)" (amendment typed) [stub]; Z-pass azure:"1b" [live]; Harbourline on Azure 23 Nov via API (classify replayed from recordings) | A, E, Z | Verified | Live classification passed on Azure (run kxrzf, 23 Nov); CI uses the stub |
| UC1-59 | UC1 s2 (new deal) | AI extracts terms with quotes; amendment applied | api:deals::test_terms_are_read_with_quotes_and_the_amendment_applied [stub]; e2e:deals "(a)" [stub]; Z-pass azure:"1c" [live] | A, E, Z | Verified | Live extraction passed on Azure (13 terms, quotes verified, reserve not invented); CI uses the stub |
| UC1-60 | UC1 s2 (new deal) | Code checks each extracted figure against its quote; failure blocks approval | api:deals::test_a_figure_not_in_its_quote_is_flagged (tampered stub answers; approve 422) | A | Verified | - |
| UC1-61 | UC1 s2 (new deal) | Nothing invented when a term is absent | api:deals::test_sme_layout_change_is_mapped_and_stored_per_client (reserve absent, blocking item); ::test_unfamiliar_documents_degrade_without_inventing_numbers [stub]; Z-pass azure:"1c" [live] | A, Z | Verified | Live model behaviour only in pending Azure spec |
| UC1-62 | UC1 s2 (new deal) | Analyst approves terms, or edits with a reason | api:deals (flow.approve_terms); api:controls::test_edits_need_a_reason (scripted case); e2e:deals "(a)" (13/13 approved); Z-pass azure:"1d" (edit with reason) | A, E, Z | Verified | Edit-with-reason on a new-deal case only in the pending Azure spec |
| UC1-63 | UC1 s4 (new deal) | AI drafts rules; code validates; failed rules removed, never approved | api:deals::test_rules_carry_their_clause_and_page [stub]; e2e:deals "(a)" [stub]; Z-pass azure:"1e" [live] | A, E, Z | Verified | Live drafting passed on Azure (10 rules, all passed code check); the failed-rule removal path has never been exercised |
| UC1-64 | UC1 s5 (new deal) | Tape mapping suggested and stored per client | api:deals::test_sme_layout_change_is_mapped_and_stored_per_client (2 mappings for the client); e2e:deals "(a)" [stub]; Z-pass azure:"1f" | A, E, Z | Verified | - |
| UC1-65 | UC1 s5 (new deal) | Engine validates the uploaded tape and matches the independent key | api:deals::test_engine_on_the_uploaded_tape_matches_the_independent_key; e2e:deals "(a)" (US$13,687,998.52) | A, E, Z | Verified | - |
| UC1-66 | UC1 s3 (new deal) | Client-model difference becomes an exception and a client query, answered in the portal | api:deals::test_the_client_model_difference_is_an_exception; ::test_query_goes_to_the_client_and_back; e2e:deals "(a)"; Z-pass azure:"1h","1i" | A, E, Z | Verified | - |
| UC1-67 | UC1 s7 (new deal) | Independent QC by Tom; the preparer cannot do QC | api:deals::test_four_eyes_qc_approval_and_go_live (Hannah QC 403); e2e:deals "(a)","(c)"; Z-pending azure:"1l" | A, E | Verified | QC items are all marked "agrees"; a disagreeing QC line on a new deal is never tested |
| UC1-68 | UC1 s7 (new deal) | Four-eyes approval by Marcus | api:deals::test_four_eyes_qc_approval_and_go_live; e2e:deals "(a)","(c)" | A, E | Verified | - |
| UC1-69 | UC1 s7 (new deal) | Load file and configuration workbook (final) after approval | api:deals::test_four_eyes_qc_approval_and_go_live; Z-pending azure:"1k","1m" (provisional then final download) | A | Verified | No CI browser download |
| UC1-70 | UC1 s7 (new deal) | Go live creates the monitoring facility with its submission schedule and a hand-off to Priya | api:deals::test_four_eyes_qc_approval_and_go_live; e2e:deals "(a)","(c)" | A, E | Verified | - |
| UC1-71 | UC1 (no-AI new deal) | Terms entered by hand with page references; a wrong page is refused | api:deals::test_no_ai_client_runs_manually_with_page_references; e2e:deals "(c)"; Z-pending azure:"4" | A, E | Verified | e2e (c) failed once on a strict-mode locator in the last full rehearsal, passed on rerun |
| UC1-72 | UC1 (no-AI new deal) | Rule entered by hand is checked against the clause text | api:deals::test_no_ai_client_runs_manually_with_page_references (mismatch 422); e2e:deals "(c)" | A, E | Verified | - |
| UC1-73 | UC1 (no-AI new deal) | Name-matching mapping (no AI) | api:deals::test_no_ai_client_runs_manually_with_page_references (source "rules"); e2e:deals "(c)" | A, E | Verified | - |
| UC1-74 | UC1 (no-AI new deal) | Zero model calls; a model step asked for is refused | api:deals::test_no_ai_client_runs_manually_with_page_references (extract 409, calls 0, no spend rows); e2e:deals "(c)" (US$0.00); Z-pending azure:"4" (run log refusals at zero) | A, E | Verified | - |
| UC1-75 | UC1 s3 (new deal) | Analyst closes an answered client query / a decided escalation with that answer | api:deals::test_four_eyes_qc_approval_and_go_live (close via API); e2e:deals "(a)" ("Close with this answer") [stub flow]; Z-FAIL azure:"1k" (23 Nov run: both items stayed "answered"/"decided" after clicking Close) | A, E, Z | Weak | Failed on Azure in the latest run; cause not yet established (app or spec). Blocks submit-for-QC in the UI path |
| PER-01 | Personas | Eight roles exist (onboarding analyst, expert, QC, reviewer, monitoring analyst, head, client, admin) | api:deals::test_roles_are_enforced_by_the_api (role set) | A | Verified | - |
| PER-02 | Personas | Named personas in the switcher (Hannah, Ruth, Tom, Marcus, Priya, Elena, James, Laura, Alex, plus new client contacts) | e2e:drills "the acting user switches"; e2e:settings (four personas); e2e:deals (switchTo across 6 personas) | E | Weak | Names and the count of 9 never asserted as a list |
| PER-03 | Personas | One persona switch shared by both workbenches | e2e:settings "other personas cannot see Settings" (switch then /monitoring) | E | Weak | Persona persistence across workbenches not asserted directly |
| PER-04 | Personas | Switching persona lands on My work | e2e:drills "the acting user switches from the user menu" | E | Verified | - |
| PER-05 | Personas | My work shows items assigned / waiting / recent hand-offs | e2e:deals "(d)" (waiting link, "done ... by Ruth", "handed over by Ruth"); api:deals (_items "waiting") | A, E | Verified | - |
| PER-06 | Personas | My work shows the age of each item | - | - | None | No test |
| PER-07 | Personas | Navigation follows the role | web:persona.test "shows each role only the areas it uses"; web:aiProvider.test "shows Settings to the administrator only"; e2e:settings | U, E | Verified | - |
| PER-08 | Personas | Actions follow the role, enforced by the API not the screen | api:deals::test_roles_are_enforced_by_the_api; api:controls::test_the_screen_is_not_the_control_a_forged_actor_name_is_refused; api:sign_in::test_a_forged_actor_in_the_body_is_ignored | A | Verified | - |
| PER-09 | Personas | Each hand-off creates a work item in the next person's queue | api:deals::test_four_eyes_qc_approval_and_go_live (Tom, Priya); ::test_report_released_after_the_client_s_levels (Marcus level 2); api:review_scenarios::test_a_confirmed_finding_hands_off_to_the_client_contact; e2e:deals "(d)"; Z-pending azure:"1j","1k" | A, E, Z | Verified | - |
| PER-10 | Personas | Hand-off shown in the notification bell | e2e:flow "Approve" (Notifications button visible); web:desk.test "notices" | U, E | Weak | Bell contents never asserted in the browser |
| PER-11 | Personas | Hand-off in the record's history and the audit trail | api:deals::test_scripted_escalation_hands_off_to_the_expert_and_back ("Handed to Ruth Adeyemi", chain intact) | A | Verified | - |
| PER-12 | Personas | Expert decides an escalation from her queue; a note is required | api:deals::test_scripted_escalation_hands_off_to_the_expert_and_back (422 without note); e2e:deals "(d)"; Z-pass azure:"1j" | A, E, Z | Verified | - |
| PER-13 | Personas | Client portal: own queries, answerable | api:deals::test_query_goes_to_the_client_and_back; e2e:deals "(a)" [stub flow]; Z-pass azure:"1i" | A, E, Z | Verified | - |
| PER-14 | Personas | Client portal: released reports and workbook | api:deals::test_report_released_after_the_client_s_levels; e2e:deals "(b)" [stub flow]; Z-pending azure:"3d" | A, E | Verified | - |
| PER-15 | Personas | Client portal: status-call brief | - | - | None | No test |
| PER-16 | Personas | Client portal: alerts | api:monitoring_brief::test_an_alert_goes_live_only_after_the_analyst_approves_it (client request via scripted events, not the portal) | A | Weak | Portal alert view/request never tested |
| PER-17 | Personas | Client sees nothing internal; internal records refused | api:deals::test_query_goes_to_the_client_and_back (no cost data); ::test_report_released_after_the_client_s_levels (case 403); ::test_roles_are_enforced_by_the_api (workbench, cycle 403); e2e:deals "(b)" (/monitoring redirects to portal); Z-pending azure:"3d" (leak scan) | A, E | Verified | - |
| PER-18 | Personas | Client sees only their own client's items | api:review_scenarios::test_a_confirmed_finding_hands_off_to_the_client_contact (Laura gets it, James does not) | A | Weak | Portal cross-client isolation (another client's queries/reports) not asserted |
| AGT-01 | Agents | Console lists every AI agent (11 named) | api:agents::test_the_console_endpoints (count = registry); ::test_every_gateway_task_in_the_code_maps_to_exactly_one_agent | A | Weak | Names/count of 11 never asserted; consistency with code is |
| AGT-02 | Agents | Console lists every code-only engine (5), which call no model | api:agents::test_model_agents_carry_the_no_ai_constraint_and_code_engines_call_no_model | U | Verified | Count of 5 not asserted |
| AGT-03 | Agents | Every model call in the code belongs to exactly one agent | api:agents::test_every_gateway_task_in_the_code_maps_to_exactly_one_agent; ::test_every_registered_task_is_called_somewhere; ::test_every_recorded_task_maps_to_an_agent | U | Verified | - |
| AGT-04 | Agents | Each agent has a trigger | api:agents::test_registry_has_no_problems | U | Verified | - |
| AGT-05 | Agents | Each agent's dependencies resolve and run forward | api:agents::test_every_dependency_resolves_and_runs_forward; ::test_registry_has_no_problems | U | Verified | - |
| AGT-06 | Agents | Each agent's constraints (no-AI constraint on model agents, deterministic on engines) | api:agents::test_model_agents_carry_the_no_ai_constraint_and_code_engines_call_no_model | U | Verified | - |
| AGT-07 | Agents | Each agent's purpose, tasks, inputs and outputs | - | - | None | Fields present in the registry but no test checks them |
| AGT-08 | Agents | Each agent's use-case steps and pain points addressed | api:agents::test_every_agent_answers_a_pain_point_and_a_use_case_step | U | Verified | - |
| AGT-09 | Agents | Asset classes now and after pilot per agent | api:agents::test_registry_has_no_problems (ids valid) | U | Weak | Only checks ids resolve |
| AGT-10 | Agents | Dependency graph by pipeline stage | web:graph.test (layout: bands by stage, edges left to right, no loops) | U | Verified | Rendered graph never opened in a browser test |
| AGT-11 | Agents | Coverage matrix: agents x pain points x asset classes | api:agents::test_every_agent_answers_a_pain_point_and_a_use_case_step (pain-point coverage) | U | Weak | Matrix view not tested |
| AGT-12 | Agents | Run log of every recorded model call with outcome, tokens, cost, duration | api:agents::test_the_run_log_lists_every_recorded_call_once_with_its_cost [rec] | A | Verified | - |
| AGT-13 | Agents | Live calls appear in the run log | api:agents::test_record_run_writes_a_live_run_the_log_shows (synthetic row) | A | Weak | No test that a real live deal step writes a run-log row; Z-pending azure:"4" reads the log for refusals only |
| AGT-14 | Agents | Refusals for no-AI clients shown at zero cost | api:agents::test_the_no_ai_client_makes_no_calls_and_shows_its_refusals; ::test_record_run_commits_on_its_own_and_refuses_an_unknown_outcome; Z-pending azure:"4" | A | Verified | - |
| AGT-15 | Agents | Acceptance statistics over decided runs | api:agents::test_stats_count_acceptance_over_decided_runs_only | U | Verified | - |
| AGT-16 | Agents | Agents console screens render (16 entries, run log populated) | Z-pending azure:"4" (screenshot only, no assertion) | - | None | No browser assertion on /agents, its graph, matrix or run log |
| ADM-01 | Admin | Administrator sets the Anthropic key in Settings > AI provider | api:admin_settings::test_no_response_ever_returns_the_key (PUT saves); web:aiProvider.test | U, A | Verified | Save through the browser not tested (e2e tests a dummy key only) |
| ADM-02 | Admin | Microsoft Foundry provider supported | api:admin_settings::test_the_connection_test_on_foundry_sends_one_token (network stubbed) | A | Weak | Network stubbed; no real Foundry call |
| ADM-03 | Admin | Test the connection | api:admin_settings::test_the_connection_test_reports_a_working_key, ::..._explains_a_refused_key..., ::..._survives_the_network_failing (stubbed); e2e:settings "the administrator tests a dummy key" (real provider refuses) | A, E | Verified | A working key's success path only with stubbed network |
| ADM-04 | Admin | Key saved encrypted at rest | api:admin_settings::test_the_key_is_encrypted_at_rest_and_round_trips; ::test_a_different_encryption_key_cannot_read_it; ::test_the_saved_key_path_is_never_written_in_plaintext; ::test_without_an_encryption_key_nothing_is_saved | A | Verified | Azure Key Vault-held encryption key not tested |
| ADM-05 | Admin | New key applies from the next call, no restart | api:admin_settings::test_a_model_client_picks_up_a_new_key_on_the_next_call; ::test_the_new_deals_gateway_and_status_use_the_resolved_key | U, A | Verified | Fake SDK |
| ADM-06 | Admin | Key never shown back, only its last four characters | api:admin_settings::test_no_response_ever_returns_the_key; ::test_a_bad_key_is_refused_without_echoing_it; ::test_scrub_removes_any_key_shaped_text; e2e:settings; web:aiProvider.test "starts empty and never holds a saved key" | U, A, E | Verified | - |
| ADM-07 | Admin | Only the administrator, with the access code, reaches AI provider settings | api:admin_settings::test_only_the_administrator_with_the_access_code_gets_in; e2e:settings "other personas cannot see Settings, and the API refuses them" | A, E | Verified | - |
| ADM-08 | Admin | Administrator creates clients with AI permission and approval levels | api:deals (flow.new_client); ::test_roles_are_enforced_by_the_api (others 403, field validation); e2e:deals createClient (validation message); Z-pass azure:"1a" | A, E, Z | Verified | - |
| ADM-09 | Admin | Client master-field overrides set by the administrator | Z-pending azure:"1a","2" | Z | Verified | Only the Azure run covers it (client created with region override, mapping honoured it); no CI test |
| ADM-10 | Admin | Edit a client (recorded in its history) | Z-pending azure:"2" | - | None | No CI test of client PATCH or its history |
| ADM-11 | Admin | Users managed by the administrator | - | - | None | No test |
| PLT-01 | Platform | Hosted on Azure Container Apps with PostgreSQL, Key Vault, Log Analytics, deployed by infra/deploy.ps1 | api:api::test_health_reports_database (local) | A | Weak | No automated check of the Azure deployment or deploy script |
| PLT-02 | Platform | Recorded AI runs replay with no key, identically every time | api:recorded_run::test_replay_reproduces_the_recorded_run_with_no_client; api:monitoring::test_replay_reproduces_the_recorded_cycle; api:casework::test_replay_reproduces_the_recorded_casework_without_a_model; api:pipeline::test_replay_needs_no_network | A | Verified | - |
| PLT-03 | Platform | Replay refuses unrecorded or changed prompts | api:pipeline::test_replay_refuses_an_unrecorded_request; ::test_a_changed_prompt_cannot_reuse_an_old_answer; ::test_recordings_from_old_prompts_are_pruned | U | Verified | - |
| PLT-04 | Platform | New deals call the model live | Z-pass azure:"1b","1c","1e","1f" (Fenwick, live, run kxrzf); Harbourline on Azure 23 Nov via API (onboarding replayed from recordings, month report drafted live; manual, no test in repo) | Z | Verified | Live onboarding steps pass on Azure; live monthly mapping and live report drafting (3a, 3b, 5) not yet passed; CI uses the stub |
| PLT-05 | Platform | New deals use recorded calls where they exist, live otherwise | - (services/api/tests/record_deals.py is a recording script, not a test) | - | None | No test of the recorded-then-live fallback |
| PLT-06 | Platform | Generated documents rebuild byte for byte and are checked by manifest | kit:pack::test_pack_rebuilds_byte_for_byte; ::test_manifest_covers_the_casework_files_and_their_key; kit:cycle::test_cycle_rebuilds_byte_for_byte; kit:newdeals::test_new_deals_rebuild_byte_for_byte | U | Verified | - |
| PLT-07 | Platform | Presenter mode: off by default, header toggle, Alt+P, ?presenter=1 | e2e:drills "presenter mode is off by default...", "Alt+P turns presenter mode on and off", "square brackets move between steps..." | E | Verified | Onboarding workbench only; presenter hints on /monitoring not tested |
| PLT-08 | Platform | Sample documents at /samples/*.zip | - | - | None | No test that the four zips are served |
| PLT-09 | Platform | Onboarding at /cases, Monitoring at /monitoring, switch in the header | e2e:screens "cases"; e2e:drills (case list) | E | Weak | /monitoring opened only to check client redirect or Settings; header switch not tested |
| PLT-10 | Platform | Pages respond, accessible, no sideways scroll at 1440 px | e2e:screens (10 onboarding scripted screens: axe WCAG A/AA, no overflow at 1920/1440, no "demo" wording) | E | Weak | None of /monitoring/*, /agents, /deals, /facilities, /portal, /clients, /work, UC1 casework screens covered; Azure check was manual |
| PLT-11 | Platform | Errors on stage are shown with a retry | e2e:drills "when something goes wrong on stage" (6 tests) | E | Verified | Onboarding scripted case only |
| PLT-12 | Platform | Access code entered from the user menu | e2e:deals, e2e:settings (enterCode) | E | Verified | - |
| PLT-13 | Platform | Middle-market model steps not recorded: code fallback runs, steps listed as pending | api:review_scenarios::test_unrecorded_model_steps_are_listed_and_their_code_fallbacks_ran; ::test_once_recorded_the_obligor_figures_come_from_the_documents (test double) | A | Verified | - |
| PLT-14 | Platform | Recording budget stops before a live call | api:review_scenarios::test_the_recording_budget_stops_before_a_live_call | U | Verified | - |
| SAF-01 | Safety controls | Code computes every number; model text carries no figures | api:monitoring::test_every_number_in_the_lender_packs_comes_from_code; api:monitoring_brief::test_status_briefs_have_no_model_written_numbers; api:casework::test_client_model_differences_become_queries_with_code_filled_figures; kit:content::test_drafted_text_has_no_figures_of_its_own | U, A | Verified | Recorded output only; live-drafted new-deal text unverified (see UC2-105) |
| SAF-02 | Safety controls | Every extracted figure is checked against its quoted source on the page | api:pipeline::test_a_made_up_quote_is_caught; ::test_an_unverified_value_is_queued_and_marked_low; api:deals::test_a_figure_not_in_its_quote_is_flagged; api:workbench::test_every_text_citation_has_a_highlight | U, A | Verified | - |
| SAF-03 | Safety controls | A failed check blocks approval | api:deals::test_a_figure_not_in_its_quote_is_flagged (approve 422); api:controls::test_a_value_that_was_not_found_cannot_be_approved | A | Verified | - |
| SAF-04 | Safety controls | Placeholders filled by code; unknown placeholder left visible, never invented | web:cycle.test "fillText"; kit:content::test_drafted_text_uses_only_known_placeholders; api:monitoring::test_every_number_in_the_lender_packs_comes_from_code | U, A | Verified | - |
| SAF-05 | Safety controls | Four-eyes: whoever prepared work cannot approve it | api:controls::test_preparer_cannot_approve_their_own_case; api:monitoring::test_the_preparer_cannot_approve_and_the_approver_cannot_triage; api:deals::test_four_eyes_qc_approval_and_go_live; api:sign_in::test_one_person_on_both_lists_still_cannot_approve_their_own_case; e2e:flow "Approve" | A, E | Verified | - |
| SAF-06 | Safety controls | Per-client approval levels (two or three), third level by a different person | api:monitoring_brief::test_thornbury_needs_a_third_level_from_a_different_person; api:deals::test_report_released_after_the_client_s_levels | A | Verified | Three levels for a new client only in Z-pending azure:"3c" |
| SAF-07 | Safety controls | Hash-chained audit trail; history cannot be changed | api:controls::test_the_database_refuses_to_change_history; ::test_a_tampered_event_breaks_the_chain; ::test_reset_keeps_the_old_session_in_the_log; api:deals::test_case_crud_validates_inline_and_audits | A | Verified | - |
| SAF-08 | Safety controls | Audit entries name the person and the record touched | api:cases::test_audit_entries_name_the_records_they_touched; api:monitoring_brief::test_audit_entries_name_the_record_they_touch; api:deals::test_four_eyes_qc_approval_and_go_live (actors) | A | Verified | Timestamps not asserted |
| SAF-09 | Safety controls | No pooling of data across clients; mapping memory per client | api:monitoring_brief::test_mapping_memory_is_scoped_to_each_client; api:deals::test_sme_layout_change_is_mapped_and_stored_per_client | A | Verified | - |
| SAF-10 | Safety controls | No-AI clients make zero model calls (guarded, including content about them) | api:monitoring_brief::test_the_guard_refuses_any_model_call_for_or_about_the_no_ai_client; api:agents::test_the_no_ai_client_makes_no_calls_and_shows_its_refusals; api:deals::test_no_ai_client_runs_manually_with_page_references; e2e:deals "(c)" | A, E | Verified | - |
| SAF-11 | Safety controls | Live AI and uploads need the access code | api:deals::test_access_code_cap_and_upload_limits (403 missing/wrong/unset) | A | Verified | - |
| SAF-12 | Safety controls | US$10 daily spend cap refuses live calls before they are made | api:deals::test_access_code_cap_and_upload_limits (seeded US$1,000 spend -> 429, cap_reached) | A | Weak | The US$10 value is not asserted; no check of the hosted setting |
| SAF-13 | Safety controls | Upload type, content and size limits | api:deals::test_access_code_cap_and_upload_limits (422 exe/non-pdf, 413 size) | A | Verified | - |
| SAF-14 | Safety controls | Correct document versions and effective terms used | eng:rules::test_advance_rate_follows_the_effective_date; ::test_fico_limit_does_not_apply_before_the_amendment; eng:monitoring::test_may_uses_the_terms_in_force_before_amendment_2; api:deals::test_terms_are_read_with_quotes_and_the_amendment_applied | U, A | Verified | - |
| SAF-15 | Safety controls | Confirmed issues kept apart from matters needing expert judgement | api:review_scenarios::test_add_backs_over_the_cap_go_to_an_expert_with_each_reading; api:deals::test_scripted_escalation_hands_off_to_the_expert_and_back | A | Verified | - |
| SAF-16 | Safety controls | Edits and changed outcomes need a reason | api:controls::test_edits_need_a_reason; api:monitoring::test_changing_a_suggested_outcome_needs_a_reason | A | Verified | - |
| SAF-17 | Safety controls | Approved work locks | api:controls::test_second_analyst_can_approve_and_the_case_then_locks; api:monitoring::test_an_approved_pack_locks_its_findings | A | Verified | - |
| SAF-18 | Safety controls | Engine is deterministic (same input, same result; digest changes with thresholds) | eng:rules::test_same_input_gives_the_same_result; ::test_changing_a_threshold_changes_the_digest_but_not_the_original | U | Verified | - |
| SAF-19 | Safety controls | Pipeline never reads the answer key | api:pipeline::test_pipeline_never_reads_the_answer_key; kit:pack::test_verifier_imports_nothing_from_the_generators | U | Verified | - |
