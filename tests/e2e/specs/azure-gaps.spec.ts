/* The end-to-end checks that need the hosted app on Azure, through the browser, switching
 * persona at each hand-off:
 *   1. a fresh live-AI onboarding of the Fenwick SME deal for a new three-level client,
 *   2. create / edit / replace / remove / archive in the UI, each checked in the record's history,
 *   3. Fenwick's first monitoring month (changed layout) to a released report seen in the portal,
 *   4. a client that does not permit AI, with zero model calls,
 *   5. a fresh Harbourline month, to check the drafted report text.
 *
 * Skipped unless BASE_URL is the Azure app. Needs DEMO_ACCESS_CODE. Steps share ids through
 * AZURE_E2E_DIR/state.json, so a failed step can be rerun with --grep without repeating the
 * live model calls before it. Run with --trace=off: a trace would keep the typed access code. */
import { expect, test, type APIRequestContext, type Locator, type Page, type Response } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const AZURE = "https://oxaneworkbench.livelypond-56376142.eastus2.azurecontainerapps.io";
const CODE = process.env.DEMO_ACCESS_CODE ?? "";
const OUT = process.env.AZURE_E2E_DIR ?? "test-results/azure-e2e";
const FILES = process.env.NEWDEALS_DIR ?? "../../deal-kit/output/newdeals";
const STATE = path.join(OUT, "state.json");
const FENWICK = "Fenwick SME Funding LLC";
const OFF_TOPIC = /placeholder|source document|no documents|not been (checked|verified)|were (not )?provided|supplied|as an ai|i (cannot|can't|don't)/i;
const TRIGGER_WORDS = /within limits|near the limit|breached/;

type State = Record<string, any>;

function load(): State {
  try {
    return JSON.parse(fs.readFileSync(STATE, "utf8"));
  } catch {
    return {};
  }
}

function save(patch: State): State {
  const next = { ...load(), ...patch };
  fs.writeFileSync(STATE, JSON.stringify(next, null, 1));
  return next;
}

function evidence(key: string, value: unknown) {
  const s = load();
  save({ evidence: { ...(s.evidence ?? {}), [key]: value } });
}

test.describe.configure({ mode: "serial", timeout: 900_000 });

test.beforeAll(async ({ request }) => {
  test.skip(process.env.BASE_URL !== AZURE, "Runs only against the Azure app");
  test.skip(!CODE, "DEMO_ACCESS_CODE is not set");
  fs.mkdirSync(path.join(OUT, "shots"), { recursive: true });
  fs.mkdirSync(path.join(OUT, "downloads"), { recursive: true });
  if (!load().run) {
    save({ run: Math.random().toString(36).slice(2, 7) });
  }
  const status = await (await request.get("/api/deals/status")).json();
  expect(status.access_configured).toBe(true);
});

const H = (persona: string, code = false) => ({ "X-Acting-User": persona, ...(code ? { "X-Demo-Access-Code": CODE } : {}) });

async function getJson(request: APIRequestContext, url: string, persona = "hannah") {
  const res = await request.get(url, { headers: H(persona) });
  expect(res.status(), `GET ${url}`).toBe(200);
  return res.json();
}

async function shot(page: Page, name: string) {
  const file = path.join(OUT, "shots", `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

async function switchTo(page: Page, name: string, within = "") {
  await page.getByRole("button", { name: /^Acting as/ }).click();
  await page.getByRole("menuitemradio", { name: new RegExp(`${name}.*${within}`) }).click();
  await expect(page.getByRole("button", { name: new RegExp(`^Acting as ${name}`) })).toBeVisible();
}

/** Typed into the access-code dialog; no screenshot is taken while it is open. */
async function enterCode(page: Page) {
  await page.getByRole("button", { name: /^Acting as/ }).click();
  await page.getByRole("menuitem", { name: "Access code" }).click();
  await page.getByRole("textbox", { name: "Code" }).fill(CODE);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
}

/** Click, wait for the write it sends, and fail with the request and response when it is refused. */
async function act(page: Page, target: Locator, match: string | RegExp, timeout = 240_000): Promise<Response> {
  const [res] = await Promise.all([
    page.waitForResponse((r) => r.request().method() !== "GET" && (typeof match === "string" ? r.url().includes(match) : match.test(r.url())), { timeout }),
    target.click(),
  ]);
  if (res.status() !== 200) {
    const body = await res.text().catch(() => "");
    const file = await shot(page, `bug-${Date.now()}`);
    const bugs = load().bugs ?? [];
    save({ bugs: [...bugs, { at: new Date().toISOString(), request: `${res.request().method()} ${res.url()}`, body: res.request().postData(), status: res.status(), response: body.slice(0, 1500), screenshot: file }] });
    expect(res.status(), `${res.request().method()} ${res.url()} -> ${body.slice(0, 600)}`).toBe(200);
  }
  return res;
}

async function download(page: Page, link: Locator, prefix: string) {
  const [d] = await Promise.all([page.waitForEvent("download", { timeout: 60_000 }), link.click()]);
  const file = path.join(OUT, "downloads", `${prefix}-${d.suggestedFilename()}`);
  await d.saveAs(file);
  return file;
}

async function tab(page: Page, name: string) {
  await page.getByRole("navigation", { name: "Sections" }).getByRole("link", { name: new RegExp(`^${name}`) }).click();
}

async function clickEach(page: Page, find: () => Locator, match: string | RegExp, before?: () => Promise<void>) {
  // Let the screen load first, so an empty count is real.
  await page.locator("main h1").first().waitFor();
  await page.waitForLoadState("networkidle");
  for (let i = 0; i < 40; i++) {
    const count = await find().count();
    if (!count || !(await find().first().isVisible().catch(() => false))) {
      return;
    }
    if (before) {
      await before();
    }
    await act(page, find().first(), match);
    await expect.poll(() => find().count(), { timeout: 20_000 }).toBeLessThan(count);
  }
}

async function createClient(page: Page, name: string, contact: string, ai: boolean, levels: number, override?: [string, string]) {
  await page.goto("/clients");
  await switchTo(page, "Alex Morgan");
  await page.goto("/clients");
  await page.getByRole("button", { name: "New client" }).click();
  await page.getByLabel("Legal name").fill(name);
  await page.getByLabel("Named client contact").fill(contact);
  if (!ai) {
    await page.getByLabel("AI", { exact: true }).selectOption("no");
  }
  await page.getByLabel("Approval levels").selectOption(String(levels));
  if (override) {
    await page.getByRole("button", { name: "Add override" }).click();
    await page.getByLabel("Field", { exact: true }).selectOption(override[0]);
    await page.getByLabel("Column", { exact: true }).fill(override[1]);
  }
  await act(page, page.getByRole("button", { name: "Create client" }), "/api/deals/clients");
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  return Number(new URL(page.url()).pathname.split("/").pop());
}

async function openCase(page: Page, client: string, facility: string, dealType: string, commitment: string) {
  await switchTo(page, "Hannah Cole");
  await page.goto("/work");
  // The new client is a hand-off to the onboarding analyst.
  await expect(page.getByRole("link", { name: new RegExp(`New client ${client}`) }).first()).toBeVisible();
  await page.getByRole("link", { name: new RegExp(`New client ${client}`) }).first().click();
  await page.getByRole("button", { name: "New case" }).click();
  await page.getByLabel("Facility name").fill(facility);
  await page.getByLabel("Deal type").selectOption(dealType);
  await page.getByLabel("Commitment (US$)").fill(commitment);
  await act(page, page.getByRole("button", { name: "Open case" }), "/api/deals/cases");
  await expect(page.getByRole("heading", { level: 1, name: facility })).toBeVisible();
  return Number(new URL(page.url()).pathname.split("/")[3]);
}

async function spent(request: APIRequestContext) {
  return (await (await request.get("/api/deals/status")).json()).spent_today_usd as number;
}

// 1. Fresh live-AI onboarding of Fenwick

test("1a admin creates a three-level AI client with a master-field override", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.fenwickClientChecked), "done");
  const name = `Marlow Bank plc ${s.run}`;
  let id = s.fenwickClient;
  if (!id) {
    save({ spendStart: await spent(request) });
    id = await createClient(page, name, `Owen Pryce ${s.run}`, true, 3, ["region", "Region"]);
    save({ fenwickClient: id, fenwickClientName: name, fenwickContact: `Owen Pryce ${s.run}` });
  } else {
    await page.goto("/work");
    await switchTo(page, "Alex Morgan");
    await page.goto(`/clients/${id}`);
  }
  await expect(page.getByText(/CLT-\d+ · 3 approval levels · AI permitted/)).toBeVisible();
  await expect(page.getByText("Overrides: region ← Region")).toBeVisible();
  await expect(page.getByText(/Created client .*AI permitted, 3 approval levels/).first()).toBeVisible();
  const client = await getJson(request, `/api/deals/clients/${id}`, "alex");
  expect(client.ai_permitted).toBe(true);
  expect(client.approval_levels).toBe(3);
  expect(client.master_field_overrides).toEqual({ region: "Region" });
  save({ fenwickClientChecked: true });
  evidence("1a", { client: client.ref, id, shot: await shot(page, "1a-client") });
});

test("1b Hannah opens the case, uploads the Fenwick documents and the AI classifies them", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.fenwickCase), "done");
  await page.goto("/work");
  const id = await openCase(page, s.fenwickClientName, FENWICK, "SME loans", "80000000");
  save({ fenwickCase: id });
  await enterCode(page);
  await page.getByLabel("Choose files").setInputFiles([
    `${FILES}/fenwick/onboarding/Fenwick_Receivables_Financing_Agreement.pdf`,
    `${FILES}/fenwick/onboarding/Fenwick_Portfolio_2026-09.xlsx`,
  ]);
  await expect(page.getByText("2 active")).toBeVisible({ timeout: 60_000 });
  await act(page, page.getByRole("button", { name: "Classify with AI" }), "/classify");
  await expect(page.getByLabel("Type of Fenwick_Receivables_Financing_Agreement.pdf")).toHaveValue("agreement");
  await expect(page.getByLabel("Type of Fenwick_Portfolio_2026-09.xlsx")).toHaveValue("loan_tape");
  const view = await getJson(request, `/api/deals/cases/${id}`);
  evidence("1b", { case: view.ref, id, kinds: view.documents_list.map((d: any) => [d.name, d.kind, d.kind_source]), shot: await shot(page, "1b-classified") });
});

test("1c the AI extracts the terms: quotes, verified checks, and the reserve not found", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.extracted), "done");
  await page.goto("/work");
  await switchTo(page, "Hannah Cole");
  await enterCode(page);
  await page.goto(`/deals/cases/${s.fenwickCase}/terms`);
  await act(page, page.getByRole("button", { name: "Extract terms" }), "/extract", 420_000);
  await expect(page.getByText("70.00%").first()).toBeVisible({ timeout: 60_000 });
  const view = await getJson(request, `/api/deals/cases/${s.fenwickCase}`);
  const terms = view.state.terms;
  const table = Object.values(terms).map((t: any) => ({ key: t.key, value: t.value, status: t.status, verified: t.verified, page: t.page, quote: t.quote, problem: t.problem, confidence: t.confidence }));
  evidence("1c-terms", table);
  for (const [key, typed] of [["commitment", 80000000], ["advance_rate", 70], ["delinquency_trigger", 7.5]] as const) {
    expect.soft(terms[key].verified, `${key} verified`).toBe(true);
    expect.soft(Number(terms[key].typed), `${key} value`).toBe(typed);
    expect.soft(terms[key].quote, `${key} quote`).toBeTruthy();
  }
  // Nothing invented for the reserve.
  expect(terms.reserve.value ?? null).toBeNull();
  expect(terms.reserve.status).toBe("missing");
  const reserveRow = page.getByRole("row").filter({ hasText: "Reserve" }).first();
  await expect(reserveRow).toContainText("Missing");
  expect(await page.locator("tbody q").count()).toBeGreaterThan(3);
  save({ extracted: true });
  evidence("1c", { shot: await shot(page, "1c-terms-extracted"), cost: view.cost });
});

test("1d Hannah approves the terms, edits one with a reason and confirms the reserve is absent", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.termsDone), "done");
  await page.goto("/work");
  await switchTo(page, "Hannah Cole");
  await page.goto(`/deals/cases/${s.fenwickCase}/terms`);
  await act(page, page.getByRole("button", { name: "Approve verified Tier 2 and 3" }), "/terms/approve-verified");
  await clickEach(page, () => page.getByRole("button", { name: "Approve", exact: true }), /\/terms\//);
  await clickEach(page, () => page.getByRole("button", { name: "Not in documents" }), /\/terms\//);
  // Edit one term with a reason.
  const row = page.getByRole("row").filter({ hasText: "Governing law" }).first();
  await row.getByRole("button", { name: "Edit" }).click();
  await page.locator("#r-governing_law").fill("Checked against clause 5: New York law, wording standardised");
  await act(page, page.getByRole("button", { name: "Save and approve" }), "/terms/governing_law");
  await expect(page.getByText(/Edited from .*: Checked against clause 5/)).toBeVisible();
  const view = await getJson(request, `/api/deals/cases/${s.fenwickCase}`);
  const left = Object.values(view.state.terms).filter((t: any) => !["approved", "absent"].includes(t.status));
  evidence("1d-left", left);
  expect(left, "every term approved or absent").toHaveLength(0);
  expect(view.state.terms.reserve.status).toBe("absent");
  await expect(page.getByText(/13\/13 approved/)).toBeVisible();
  save({ termsDone: true });
  evidence("1d", { shot: await shot(page, "1d-terms-approved"), edited: view.state.terms.governing_law.edited });
});

test("1e the AI drafts the rules; code checks them; Hannah approves the rule set", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.rulesDone), "done");
  await page.goto("/work");
  await switchTo(page, "Hannah Cole");
  await enterCode(page);
  await page.goto(`/deals/cases/${s.fenwickCase}/rules`);
  await act(page, page.getByRole("button", { name: "Draft with AI" }), "/rules/draft", 420_000);
  let view = await getJson(request, `/api/deals/cases/${s.fenwickCase}`);
  const rules = view.state.rules;
  evidence("1e-rules", { eligibility: rules.eligibility.map((r: any) => [r.id, r.describe, r.verified, r.problem]), concentration: rules.concentration.map((r: any) => [r.id, r.describe, r.verified, r.problem]), not_codable: rules.not_codable });
  await shot(page, "1e-rules-drafted");
  // A rule that failed its code check is removed, never approved.
  const failed = page.getByRole("row").filter({ hasText: "Failed" }).getByRole("button", { name: "Remove" });
  await clickEach(page, () => failed, /\/rules$/);
  await act(page, page.getByRole("button", { name: "Approve rule set" }), /\/rules$/);
  await expect(page.getByText(/approved by Hannah Cole/)).toBeVisible();
  view = await getJson(request, `/api/deals/cases/${s.fenwickCase}`);
  save({ rulesDone: true });
  evidence("1e", { eligibility: view.state.rules.eligibility.length, concentration: view.state.rules.concentration.length, shot: await shot(page, "1e-rules-approved") });
});

test("1f the AI suggests the mapping, the override holds, Hannah confirms", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.mappingDone), "done");
  await page.goto("/work");
  await switchTo(page, "Hannah Cole");
  await enterCode(page);
  await page.goto(`/deals/cases/${s.fenwickCase}/mapping`);
  await act(page, page.getByRole("button", { name: "Suggest mapping" }), "/mapping/suggest", 300_000);
  await expect(page.getByText(/AI suggestion · not confirmed/)).toBeVisible();
  await expect(page.getByLabel("Field for Region")).toHaveValue("region");
  await expect(page.getByLabel("Field for Arrears Days")).toHaveValue("days_past_due");
  await shot(page, "1f-mapping-suggested");
  await act(page, page.getByRole("button", { name: "Confirm and store" }), /\/mapping$/);
  await expect(page.getByText(/confirmed by Hannah Cole/)).toBeVisible();
  const view = await getJson(request, `/api/deals/cases/${s.fenwickCase}`);
  save({ mappingDone: true });
  evidence("1f", { columns: view.state.mapping.columns, statuses: view.state.mapping.status_map, shot: await shot(page, "1f-mapping-confirmed") });
});

test("1g the engine validates the tape", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.validated), "done");
  await page.goto("/work");
  await switchTo(page, "Hannah Cole");
  await page.goto(`/deals/cases/${s.fenwickCase}/validation`);
  await page.getByLabel("Reporting date").fill("2026-09-30");
  await act(page, page.getByRole("button", { name: "Validate and run" }), "/validate");
  await expect(page.getByText("Borrowing base", { exact: true })).toBeVisible();
  await expect(page.getByText("US$65,148,156.18")).toBeVisible();
  const view = await getJson(request, `/api/deals/cases/${s.fenwickCase}`);
  const e = view.state.validation.engine;
  save({ validated: true });
  evidence("1g", { gross: e.gross_pool_cents / 100, eligible: e.eligible_pool_cents / 100, bb: e.borrowing_base_cents / 100, key_eligible: 49460929.8, rows: view.state.validation.rows, shot: await shot(page, "1g-validation") });
});

test("1h Hannah works the exceptions: one query to the client, one escalation to Ruth", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.queryRef), "done");
  await page.goto("/work");
  await switchTo(page, "Hannah Cole");
  await page.goto(`/deals/cases/${s.fenwickCase}/exceptions`);
  const main = await getJson(request, `/api/deals/cases/${s.fenwickCase}`);
  const mainOpen = main.state.exceptions.filter((e: any) => !["accepted", "resolved"].includes(e.status) && e.severity !== "info");
  evidence("1h-main-case-exceptions", { open: mainOpen.length, all: main.state.exceptions.map((e: any) => [e.ref, e.type, e.severity, e.status, e.title]) });
  await shot(page, "1h-main-case-no-open-exceptions");
  // Fenwick's tape is clean and every term reading closes when the term is approved, so the
  // main case has nothing left to route. A second Fenwick case is routed before its terms are
  // approved, the point where the "check the reading" exceptions are open.
  let exc = s.excCase;
  if (!exc) {
    await page.goto(`/clients/${s.fenwickClient}`);
    await page.getByRole("button", { name: "New case" }).click();
    await page.getByLabel("Facility name").fill(`${FENWICK} (exceptions route)`);
    await page.getByLabel("Deal type").selectOption("SME loans");
    await page.getByLabel("Commitment (US$)").fill("80000000");
    await act(page, page.getByRole("button", { name: "Open case" }), "/api/deals/cases");
    await page.waitForURL(/\/deals\/cases\/\d+\/documents/);
    exc = Number(new URL(page.url()).pathname.split("/")[3]);
    save({ excCase: exc });
  }
  await enterCode(page);
  let view = await getJson(request, `/api/deals/cases/${exc}`);
  if (!view.documents_list.length) {
    await page.goto(`/deals/cases/${exc}/documents`);
    await page.getByLabel("Type", { exact: true }).selectOption("agreement");
    await page.getByLabel("Choose files").setInputFiles(`${FILES}/fenwick/onboarding/Fenwick_Receivables_Financing_Agreement.pdf`);
    await expect(page.getByText("1 active")).toBeVisible({ timeout: 60_000 });
  }
  if (!Object.keys(view.state.terms ?? {}).length) {
    await page.goto(`/deals/cases/${exc}/terms`);
    await act(page, page.getByRole("button", { name: "Extract terms" }), "/extract", 420_000);
  }
  await page.goto(`/deals/cases/${exc}/exceptions`);
  view = await getJson(request, `/api/deals/cases/${exc}`);
  const open = view.state.exceptions.filter((e: any) => e.status === "open" && e.severity !== "info");
  evidence("1h-open", open.map((e: any) => [e.ref, e.type, e.severity, e.title]));
  expect(open.length, "at least two open exceptions to route").toBeGreaterThanOrEqual(2);
  const q = open.find((e: any) => e.severity !== "blocking") ?? open[0];
  const x = open.find((e: any) => e.ref !== q.ref && e.severity !== "blocking") ?? open.find((e: any) => e.ref !== q.ref);
  const qItem = page.getByRole("listitem").filter({ hasText: q.title }).first();
  await qItem.getByLabel(`Note for ${q.ref}`).fill(`Please confirm the position on ${q.title.toLowerCase()}.`);
  await act(page, qItem.getByRole("button", { name: "Query client" }), `/exceptions/${q.ref}`);
  const xItem = page.getByRole("listitem").filter({ hasText: x.title }).first();
  await xItem.getByLabel(`Note for ${x.ref}`).fill("Credit judgement needed before the load: is this reading right?");
  await act(page, xItem.getByRole("button", { name: "Send to expert" }), `/exceptions/${x.ref}`);
  save({ queryRef: q.ref, queryTitle: q.title, escRef: x.ref, escTitle: x.title });
  await expect(page.getByText("With client").first()).toBeVisible();
  await expect(page.getByText("With expert").first()).toBeVisible();
  view = await getJson(request, `/api/deals/cases/${exc}`);
  evidence("1h", { case: view.ref, id: exc, query: q.ref, escalated: x.ref, cost: view.cost, shot: await shot(page, "1h-exceptions-routed") });
});

test("1i the client contact answers the query in the portal and sees nothing internal", async ({ page }) => {
  const s = load();
  test.skip(Boolean(s.answered), "done");
  await page.goto("/work");
  await switchTo(page, s.fenwickContact, s.fenwickClientName);
  await expect(page).toHaveURL(/\/portal$/);
  await expect(page.getByText(s.queryTitle).first()).toBeVisible();
  await expect(page.getByText(s.escTitle)).toHaveCount(0);
  await expect(page.getByText("Credit judgement needed")).toHaveCount(0);
  await page.getByLabel("Answer").first().fill("Confirmed: the September tape is correct as sent.");
  await act(page, page.getByRole("button", { name: "Send answer" }).first(), "/answer");
  await expect(page.getByText("Your answer: Confirmed").first()).toBeVisible();
  save({ answered: true });
  evidence("1i", { shot: await shot(page, "1i-portal-answered") });
});

test("1j Ruth decides the escalation from her queue", async ({ page }) => {
  const s = load();
  test.skip(Boolean(s.decided), "done");
  await page.goto("/work");
  await switchTo(page, "Ruth Adeyemi");
  await page.goto("/work");
  const link = page.getByRole("link", { name: new RegExp(`Expert judgement: ${s.escTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`) }).first();
  await expect(link).toBeVisible();
  await shot(page, "1j-ruth-queue");
  await link.click();
  await expect(page).toHaveURL(new RegExp(`/deals/cases/${s.excCase}/exceptions`));
  await page.getByLabel(`Decision for ${s.escRef}`).fill("Include: within the agreement's terms on the evidence given");
  await act(page, page.getByRole("button", { name: "Record decision" }), "/decide");
  await expect(page.getByText(/Expert: Include/)).toBeVisible();
  save({ decided: true });
  evidence("1j", { shot: await shot(page, "1j-ruth-decided") });
});

test("1k Hannah closes both and submits for QC", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.submittedQc), "done");
  await page.goto("/work");
  await switchTo(page, "Hannah Cole");
  await page.goto("/work");
  await expect(page.getByRole("link", { name: new RegExp(`Client answered ${s.queryRef}`) }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: new RegExp(`Expert decided ${s.escRef}`) }).first()).toBeVisible();
  await shot(page, "1k-hannah-queue");
  await page.goto(`/deals/cases/${s.excCase}/exceptions`);
  await expect(page.getByRole("button", { name: "Close with this answer" }).first()).toBeVisible();
  await clickEach(page, () => page.getByRole("button", { name: "Close with this answer" }), /\/exceptions\//);
  const exc = await getJson(request, `/api/deals/cases/${s.excCase}`);
  const routed = exc.state.exceptions.filter((e: any) => [s.queryRef, s.escRef].includes(e.ref));
  evidence("1k-routed", routed.map((e: any) => ({ ref: e.ref, status: e.status, query: e.query, answer: e.answer, escalation: e.escalation, decision: e.decision })));
  expect(routed.map((e: any) => e.status)).toEqual(["accepted", "accepted"]);
  await shot(page, "1k-closed");
  await page.goto(`/deals/cases/${s.fenwickCase}/approval`);
  // The configuration workbook before approval is provisional.
  save({ configProvisional: await download(page, page.getByRole("link", { name: /Configuration workbook \(provisional\)/ }), "1k") });
  await tab(page, "QC");
  await act(page, page.getByRole("button", { name: "Submit for QC" }), "/submit-qc");
  await expect(page.getByText(/In QC · submitted by Hannah Cole/)).toBeVisible();
  const view = await getJson(request, `/api/deals/cases/${s.fenwickCase}`);
  save({ submittedQc: true });
  evidence("1k", { readiness: view.readiness, shot: await shot(page, "1k-submitted-qc") });
});

test("1l Tom completes independent QC", async ({ page }) => {
  const s = load();
  test.skip(Boolean(s.qcDone), "done");
  await page.goto("/work");
  await switchTo(page, "Tom Fairley");
  await page.goto("/work");
  const casePath = `/deals/cases/${s.fenwickCase}`;
  await page.locator(`main a[href="${casePath}/qc"]`).first().click();
  await expect(page.getByRole("button", { name: "Agrees", exact: true }).first()).toBeVisible();
  await clickEach(page, () => page.getByRole("button", { name: "Agrees", exact: true }), /\/qc$/);
  await act(page, page.getByRole("button", { name: "Complete QC" }), "/qc/complete");
  await expect(page.getByText(/Passed · Tom Fairley/)).toBeVisible();
  save({ qcDone: true });
  evidence("1l", { shot: await shot(page, "1l-qc-passed") });
});

test("1m Marcus approves, downloads the load file and configuration workbook, and goes live", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.fenwickFacility), "done");
  await page.goto("/work");
  await switchTo(page, "Marcus Hale");
  await page.goto("/work");
  const casePath = `/deals/cases/${s.fenwickCase}`;
  await page.locator(`main a[href="${casePath}/approval"]`).first().click();
  await act(page, page.getByRole("button", { name: "Approve", exact: true }), "/approve");
  await expect(page.getByText(/Approved by Marcus Hale/)).toBeVisible();
  const loadFile = await download(page, page.getByRole("link", { name: /Load file/ }), "1m");
  const config = await download(page, page.getByRole("link", { name: /Configuration workbook \(final\)/ }), "1m");
  await act(page, page.getByRole("button", { name: "Go live" }), "/go-live");
  await page.getByRole("link", { name: "Open facility" }).click();
  await expect(page.getByRole("heading", { level: 1, name: FENWICK })).toBeVisible();
  const facility = Number(new URL(page.url()).pathname.split("/").pop());
  const view = await getJson(request, `/api/deals/cases/${s.fenwickCase}`);
  save({ fenwickFacility: facility, loadFile, configFinal: config });
  evidence("1m", { facility, loadFile, config, shot: await shot(page, "1m-facility") });
  // Fresh live calls for this case.
  expect(view.cost.live_calls).toBeGreaterThan(0);
  evidence("1-cost", view.cost);
});

// 2. Create, edit, replace, remove, archive, each in the record's history

test("2 CRUD in the UI, each in the record's history", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.crudDone), "done");
  // Edit the client and set a second master-field override.
  await page.goto("/work");
  await switchTo(page, "Alex Morgan");
  await page.goto(`/clients/${s.fenwickClient}`);
  if (!s.crudClientEdited) {
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Short name").fill(`Marlow ${s.run}`);
  await page.getByRole("button", { name: "Add override" }).click();
  await page.getByLabel("Field", { exact: true }).last().selectOption("sector");
  await page.getByLabel("Column", { exact: true }).last().fill("Sector");
  await act(page, page.getByRole("button", { name: "Save changes" }), `/api/deals/clients/${s.fenwickClient}`);
  await expect(page.getByText("Overrides: region ← Region, sector ← Sector")).toBeVisible();
  await expect(page.getByText(/Changed short name, master field overrides/)).toBeVisible();
  save({ crudClientEdited: true });
  }
  await expect(page.getByText("Overrides: region ← Region, sector ← Sector")).toBeVisible();
  await expect(page.getByText(/Changed short name, master field overrides/)).toBeVisible();
  await shot(page, "2-client-edited");

  // A throwaway case: upload, replace (new version), remove.
  await switchTo(page, "Hannah Cole");
  await enterCode(page);
  let id: number = s.crudCase;
  if (!id) {
  await page.goto(`/clients/${s.fenwickClient}`);
  await page.getByRole("button", { name: "New case" }).click();
  await page.getByLabel("Facility name").fill(`Fenwick CRUD check ${s.run}`);
  await page.getByLabel("Deal type").selectOption("SME loans");
  await page.getByLabel("Commitment (US$)").fill("1000000");
  await act(page, page.getByRole("button", { name: "Open case" }), "/api/deals/cases");
  await page.waitForURL(/\/deals\/cases\/\d+\/documents/);
  id = Number(new URL(page.url()).pathname.split("/")[3]);
  save({ crudCase: id });
  await page.getByLabel("Type", { exact: true }).selectOption("agreement");
  await page.getByLabel("Choose files").setInputFiles(`${FILES}/fenwick/onboarding/Fenwick_Receivables_Financing_Agreement.pdf`);
  await expect(page.getByText("1 active")).toBeVisible({ timeout: 60_000 });
  await page.getByLabel("Type", { exact: true }).selectOption("loan_tape");
  await page.getByLabel("Choose files").setInputFiles(`${FILES}/fenwick/onboarding/Fenwick_Portfolio_2026-09.xlsx`);
  await expect(page.getByText("2 active")).toBeVisible({ timeout: 60_000 });
  const tapeRow = page.getByRole("row").filter({ hasText: "Fenwick_Portfolio_2026-09.xlsx" });
  const [replaced] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/replace")),
    tapeRow.locator('input[type="file"]').setInputFiles(`${FILES}/fenwick/monthly/Fenwick_Portfolio_2026-10.xlsx`),
  ]);
  expect(replaced.status()).toBe(200);
  }
  await page.goto(`/deals/cases/${id}/documents`);
  await expect(page.getByRole("row").filter({ hasText: "Fenwick_Portfolio_2026-10.xlsx" })).toContainText("v2");
  const agreementRow = page.getByRole("row").filter({ hasText: "Fenwick_Receivables_Financing_Agreement.pdf" });
  await act(page, agreementRow.getByRole("button", { name: "Remove" }), /\/documents\/\d+$/);
  await expect(page.getByText("1 active")).toBeVisible();
  await shot(page, "2-documents");

  // Edit a case field and archive the case: is there a control for each?
  const editCase = page.getByRole("button", { name: /Edit case|^Edit$/ });
  const archiveCase = page.getByRole("button", { name: /Archive/ });
  const hasEdit = await editCase.count();
  const hasArchive = await archiveCase.count();
  evidence("2-ui-controls", { editCaseButton: hasEdit, archiveCaseButton: hasArchive });
  expect.soft(hasEdit, "a control to edit the case's fields").toBeGreaterThan(0);
  expect.soft(hasArchive, "a control to archive the case").toBeGreaterThan(0);
  if (hasEdit) {
    await editCase.first().click();
    await page.getByLabel("Commitment (US$)").fill("2000000");
    await act(page, page.getByRole("button", { name: /Save/ }), `/api/deals/cases/${id}`);
  } else {
    // No control in the UI: check the API records it, so the gap is the screen only.
    const res = await request.patch(`/api/deals/cases/${id}`, { headers: H("hannah"), data: { commitment: 2000000 } });
    expect(res.status(), await res.text()).toBe(200);
  }
  if (hasArchive) {
    await archiveCase.first().click();
    const reason = page.getByLabel(/Reason|Note/);
    if (await reason.count()) {
      await reason.first().fill("Test case for the Azure checks");
    }
    const confirm = page.getByRole("button", { name: /Archive/ }).last();
    await act(page, confirm, `/api/deals/cases/${id}/archive`);
  } else {
    const res = await request.post(`/api/deals/cases/${id}/archive`, { headers: H("hannah"), data: { note: "Test case for the Azure checks" } });
    expect(res.status(), await res.text()).toBe(200);
  }
  await page.goto(`/deals/cases/${id}/activity`);
  for (const text of [/Uploaded|Added/, /Replaced Fenwick_Portfolio_2026-09\.xlsx v1 with Fenwick_Portfolio_2026-10\.xlsx v2/, /Removed Fenwick_Receivables_Financing_Agreement\.pdf/, /Changed commitment/, /Archived the case/]) {
    await expect.soft(page.getByText(text).first(), String(text)).toBeVisible();
  }
  const view = await getJson(request, `/api/deals/cases/${id}`);
  evidence("2-case-history", view.history.entries.map((e: any) => [e.type, e.text, e.actor]));
  evidence("2", { case: view.ref, id, archived: view.archived_at ?? view.state?.archived_at ?? null, shot: await shot(page, "2-case-activity") });
  const client = await getJson(request, `/api/deals/clients/${s.fenwickClient}`, "alex");
  evidence("2-client-history", client.history.entries.map((e: any) => [e.type, e.text, e.actor]));
  save({ crudDone: true });
});

// 3. Fenwick's first monitoring month

test("3a Priya receives October, the changed layout is mapped by AI and confirmed", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.fenwickMapped), "done");
  await page.goto("/work");
  await switchTo(page, "Priya Raman");
  await page.goto("/work");
  await page.locator(`main a[href="/facilities/${s.fenwickFacility}"]`).first().click();
  await expect(page.getByRole("heading", { level: 1, name: FENWICK })).toBeVisible();
  await page.getByRole("link", { name: "Open" }).first().click();
  const sub = Number(new URL(page.url()).pathname.split("/").pop());
  save({ fenwickSub: sub });
  await enterCode(page);
  await page.getByLabel("Choose loan tape").setInputFiles(`${FILES}/fenwick/monthly/Fenwick_Portfolio_2026-10.xlsx`);
  await expect(page.getByText("Fenwick_Portfolio_2026-10.xlsx").first()).toBeVisible({ timeout: 60_000 });
  await page.getByLabel("Choose servicer report").setInputFiles(`${FILES}/fenwick/monthly/Fenwick_Monthly_Report_October_2026.pdf`);
  await expect(page.getByText("Fenwick_Monthly_Report_October_2026.pdf").first()).toBeVisible({ timeout: 60_000 });
  await act(page, page.getByRole("button", { name: "Map tape" }), "/map", 300_000);
  await expect(page.getByText(/Layout changed \(.*\): AI suggested the changed columns; confirm below/)).toBeVisible();
  await expect(page.getByLabel("Field for Days in Arrears")).toHaveValue("days_past_due");
  await shot(page, "3a-mapping-changed");
  await act(page, page.getByRole("button", { name: "Confirm and store" }), /\/mapping$/);
  const view = await getJson(request, `/api/deals/submissions/${sub}`, "priya");
  expect(view.state.mapping.confirmed).toBe(true);
  expect(view.state.mapping.source).toBe("ai");
  save({ fenwickMapped: true });
  evidence("3a", { sub: view.ref, id: sub, changed: view.state.mapping.changed_columns, columns: view.state.mapping.columns, source: view.state.mapping.source });
});

test("3b validate, reconcile, triggers, triage and draft the report", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.fenwickDrafted), "done");
  await page.goto("/work");
  await switchTo(page, "Priya Raman");
  await enterCode(page);
  await page.goto(`/facilities/${s.fenwickFacility}/submissions/${s.fenwickSub}`);
  await act(page, page.getByRole("button", { name: "Run the month" }), "/process", 300_000);
  let view = await getJson(request, `/api/deals/submissions/${s.fenwickSub}`, "priya");
  evidence("3b-findings", view.state.findings.map((f: any) => [f.ref, f.check, f.severity, f.title, f.suggested.outcome]));
  evidence("3b-tests", view.state.tests);
  evidence("3b-reconciliation", view.state.reconciliation);
  evidence("3b-report-figures", view.state.report_figures);
  await shot(page, "3b-run");
  // Blocking findings and expert suggestions are decided as confirmed with a reason; the rest take the suggestion.
  for (const f of view.state.findings) {
    if (f.decision) continue;
    const row = page.getByRole("listitem").filter({ hasText: f.title }).first();
    if (f.severity === "blocking" || f.suggested.outcome === "expert") {
      await row.getByLabel(`Outcome for ${f.ref}`).selectOption("confirmed");
      await row.getByLabel(`Reason for ${f.ref}`).fill("Confirmed against the October tape and report; client informed");
    }
    await act(page, row.getByRole("button", { name: "Decide" }), `/triage/${f.ref}`);
  }
  view = await getJson(request, `/api/deals/submissions/${s.fenwickSub}`, "priya");
  const waiting = view.state.findings.filter((f: any) => !f.decision);
  for (const f of waiting) {
    await act(page, page.getByRole("listitem").filter({ hasText: f.title }).first().getByRole("button", { name: "Decide" }), `/triage/${f.ref}`);
  }
  await act(page, page.getByRole("button", { name: "Draft report" }), "/report/draft", 300_000);
  view = await getJson(request, `/api/deals/submissions/${s.fenwickSub}`, "priya");
  const report = view.state.report;
  evidence("3b-report", { drafted_by: report.drafted_by, text: report.text, template: report.template });
  expect(["ai", "template"]).toContain(report.drafted_by);
  for (const p of report.text) {
    expect.soft(p, "no unfilled placeholder").not.toMatch(/\{\{|\}\}/);
    expect.soft(p, "no paragraph about documents or placeholders").not.toMatch(OFF_TOPIC);
    expect.soft(p, "no empty slot").not.toMatch(/ as \.|  |\( ?\)| ,/);
  }
  if (report.template.some((p: string) => p.includes("{{trigger_status}}")) || view.state.tests.delinquency_average) {
    expect(report.text.join(" "), "trigger status stated").toMatch(new RegExp(`${TRIGGER_WORDS.source}|above the trigger|below the trigger`));
  }
  await expect(page.getByText("Provisional", { exact: true }).first()).toBeVisible();
  save({ fenwickDrafted: true, fenwickWorkbookProvisional: await download(page, page.getByRole("link", { name: /Lender workbook \(provisional\)/ }), "3b") });
  evidence("3b", { shot: await shot(page, "3b-report-drafted"), cost: view.cost });
});

test("3c Priya, Marcus and Elena approve the three levels and the report is released", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.fenwickReleased), "done");
  const subPath = `/facilities/${s.fenwickFacility}/submissions/${s.fenwickSub}`;
  await page.goto("/work");
  await switchTo(page, "Priya Raman");
  await page.goto(subPath);
  await act(page, page.getByRole("button", { name: "Approve, level 1" }), "/approve");
  for (const [who, level] of [["Marcus Hale", 2], ["Elena Varga", 3]] as const) {
    await switchTo(page, who);
    await page.goto("/work");
    await page.locator(`main a[href="${subPath}"]`).first().click();
    await act(page, page.getByRole("button", { name: `Approve, level ${level}` }), "/approve");
  }
  await expect(page.getByText("Released", { exact: true }).first()).toBeVisible();
  const view = await getJson(request, `/api/deals/submissions/${s.fenwickSub}`, "priya");
  expect(view.state.report.approvals.map((a: any) => a.by)).toEqual(["Priya Raman", "Marcus Hale", "Elena Varga"]);
  const workbook = await download(page, page.getByRole("link", { name: /Lender workbook \(released\)/ }), "3c");
  save({ fenwickReleased: true, fenwickWorkbookReleased: workbook });
  evidence("3c", { approvals: view.state.report.approvals, workbook, shot: await shot(page, "3c-released") });
});

test("3d the client contact sees the released report and workbook, nothing internal", async ({ page, request }) => {
  const s = load();
  await page.goto("/work");
  await switchTo(page, s.fenwickContact, s.fenwickClientName);
  await expect(page).toHaveURL(/\/portal$/);
  const reports = page.locator("li").filter({ hasText: FENWICK }).filter({ has: page.getByRole("link", { name: "Workbook" }) });
  await expect(reports.first()).toBeVisible();
  const workbook = await download(page, reports.first().getByRole("link", { name: "Workbook" }), "3d-portal");
  const text = await page.locator("main").innerText();
  const leaks = ["Credit judgement needed", "Include: within", "Tom Fairley", "Ruth Adeyemi", "Elena Varga", "Provisional", "provisional", "Expert", s.escTitle].filter((w) => text.includes(w));
  evidence("3d", { leaks, workbook, shot: await shot(page, "3d-portal") });
  expect(leaks).toEqual([]);
  // Internal records are refused to a client user.
  const persona = `client-${s.fenwickClient}`;
  const caseRes = await request.get(`/api/deals/cases/${s.fenwickCase}`, { headers: H(persona) });
  const subRes = await request.get(`/api/deals/submissions/${s.fenwickSub}`, { headers: H(persona) });
  evidence("3d-api", { case: caseRes.status(), submission: subRes.status() });
  expect(caseRes.status()).toBe(403);
  expect(subRes.status()).toBe(403);
  await page.goto("/monitoring");
  await expect(page).toHaveURL(/\/portal$/);
  save({ fenwickPortalWorkbook: workbook });
});

// 4. A client that does not permit AI

test("4 a no-AI client onboards by hand with page references and zero model calls", async ({ page, request }) => {
  const s = load();
  test.skip(Boolean(s.noAiFacility), "done");
  const name = `Kingsgate Bank N.A. ${s.run}`;
  const clientId = s.noAiClient ?? (await createClient(page, name, `Rosa Lind ${s.run}`, false, 2));
  save({ noAiClient: clientId, noAiClientName: name });
  await page.goto("/work");
  const caseId = await openCase(page, name, FENWICK, "SME loans", "80000000");
  save({ noAiCase: caseId });
  await enterCode(page);
  await page.getByLabel("Type", { exact: true }).selectOption("agreement");
  await page.getByLabel("Choose files").setInputFiles(`${FILES}/fenwick/onboarding/Fenwick_Receivables_Financing_Agreement.pdf`);
  await expect(page.getByText("1 active")).toBeVisible({ timeout: 60_000 });
  await page.getByLabel("Type", { exact: true }).selectOption("loan_tape");
  await page.getByLabel("Choose files").setInputFiles(`${FILES}/fenwick/onboarding/Fenwick_Portfolio_2026-09.xlsx`);
  await expect(page.getByText("2 active")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Classify with AI" })).toBeDisabled();

  await tab(page, "Terms");
  await act(page, page.getByRole("button", { name: "Start manual entry" }), "/terms/manual");
  const doc = "Fenwick_Receivables_Financing_Agreement.pdf";
  const enter = async (label: string, key: string, value: string, pageNo: string) => {
    await expect(page.getByRole("button", { name: "Save and approve" })).toHaveCount(0);
    await page.getByRole("row").filter({ hasText: label }).first().getByRole("button", { name: "Enter" }).click();
    await page.locator(`#v-${key}`).fill(value);
    await page.locator(`#d-${key}`).selectOption(doc);
    await page.locator(`#p-${key}`).fill(pageNo);
    await page.getByRole("button", { name: "Save and approve" }).click();
  };
  await enter("Facility limit", "commitment", "US$80,000,000", "1");
  await expect(page.getByText(/This value is not on page 1/)).toBeVisible();
  await shot(page, "4-wrong-page-rejected");
  await page.locator("#p-commitment").fill("2");
  await act(page, page.getByRole("button", { name: "Save and approve" }), "/terms/commitment");
  await expect(page.getByRole("row").filter({ hasText: "Facility limit" }).getByText("Approved")).toBeVisible();
  await enter("Advance rate", "advance_rate", "70.00%", "2");
  await enter("Delinquency trigger", "delinquency_trigger", "7.50%", "3");
  await expect(page.getByRole("row").filter({ hasText: "Delinquency trigger" }).getByText("Approved")).toBeVisible();
  await clickEach(page, () => page.getByRole("button", { name: "Not in documents" }), /\/terms\//);

  await tab(page, "Rules");
  await page.getByRole("button", { name: "Add rule" }).first().click();
  await page.getByLabel("Clause reference").fill("First Schedule (a)");
  await page.getByLabel("Plain English").fill("Not more than 30 days in arrears");
  await page.getByLabel("Clause text, copied from the document").fill("the loan is not more than 30 days in arrears;");
  await page.getByLabel("Field", { exact: true }).selectOption("days_past_due");
  await page.getByLabel("Threshold").fill("30");
  await act(page, page.getByRole("button", { name: "Check and add" }), /\/rules$/);
  await expect(page.getByText("days_past_due <= 30")).toBeVisible();
  await act(page, page.getByRole("button", { name: "Approve rule set" }), /\/rules$/);

  await tab(page, "Mapping");
  await act(page, page.getByRole("button", { name: "Suggest mapping" }), "/mapping/suggest");
  await expect(page.getByText(/Name matching/)).toBeVisible();
  await act(page, page.getByRole("button", { name: "Confirm and store" }), /\/mapping$/);

  await tab(page, "Validation");
  await page.getByLabel("Reporting date").fill("2026-09-30");
  await act(page, page.getByRole("button", { name: "Validate and run" }), "/validate");
  await expect(page.getByText("Borrowing base", { exact: true })).toBeVisible();
  await expect(page.getByText(/model cost US\$0\.00/)).toBeVisible();
  await tab(page, "Exceptions");
  await clickEach(page, () => page.getByRole("button", { name: "Accept", exact: true }), /\/exceptions\//, () => page.getByLabel(/^Note for/).first().fill("Reviewed against the documents"));
  await tab(page, "QC");
  await act(page, page.getByRole("button", { name: "Submit for QC" }), "/submit-qc");
  await switchTo(page, "Tom Fairley");
  await page.goto("/work");
  await page.locator(`main a[href="/deals/cases/${caseId}/qc"]`).first().click();
  await clickEach(page, () => page.getByRole("button", { name: "Agrees", exact: true }), /\/qc$/);
  await act(page, page.getByRole("button", { name: "Complete QC" }), "/qc/complete");
  await switchTo(page, "Marcus Hale");
  await page.goto("/work");
  await page.locator(`main a[href="/deals/cases/${caseId}/approval"]`).first().click();
  await act(page, page.getByRole("button", { name: "Approve", exact: true }), "/approve");
  await act(page, page.getByRole("button", { name: "Go live" }), "/go-live");
  await page.getByRole("link", { name: "Open facility" }).click();
  const facility = Number(new URL(page.url()).pathname.split("/").pop());
  save({ noAiFacility: facility });
  await shot(page, "4-live");

  const view = await getJson(request, `/api/deals/cases/${caseId}`);
  await page.goto("/agents");
  await shot(page, "4-agents-console");
  evidence("4", { case: view.ref, caseId, facility, cost: view.cost });
  expect(view.cost.calls).toBe(0);
  expect(view.cost.cost_usd).toBe(0);
});

test("4b a model step asked for anyway is refused for the no-AI client and logged at zero", async ({ page, request }) => {
  const s = load();
  await page.goto("/work");
  await switchTo(page, "Hannah Cole");
  await enterCode(page);
  let probe: number = s.noAiProbe;
  if (!probe) {
    await page.goto(`/clients/${s.noAiClient}`);
    await page.getByRole("button", { name: "New case" }).click();
    await page.getByLabel("Facility name").fill(`Kingsgate refusal probe ${s.run}`);
    await page.getByLabel("Deal type").selectOption("SME loans");
    await page.getByLabel("Commitment (US$)").fill("1000000");
    await act(page, page.getByRole("button", { name: "Open case" }), "/api/deals/cases");
    await page.waitForURL(/\/deals\/cases\/\d+\/documents/);
    probe = Number(new URL(page.url()).pathname.split("/")[3]);
    save({ noAiProbe: probe });
    await page.getByLabel("Type", { exact: true }).selectOption("agreement");
    await page.getByLabel("Choose files").setInputFiles(`${FILES}/fenwick/onboarding/Fenwick_Receivables_Financing_Agreement.pdf`);
    await expect(page.getByText("1 active")).toBeVisible({ timeout: 60_000 });
  }
  await page.goto(`/deals/cases/${probe}/documents`);
  await expect(page.getByRole("button", { name: "Classify with AI" })).toBeDisabled();
  await page.goto(`/deals/cases/${probe}/terms`);
  await expect(page.getByRole("button", { name: "Start manual entry" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Extract terms" })).toHaveCount(0);
  const refused = [];
  for (const step of ["classify", "extract"]) {
    const res = await request.post(`/api/deals/cases/${probe}/${step}`, { headers: H("hannah", true) });
    refused.push([step, res.status(), (await res.text()).slice(0, 200)]);
  }
  const view = await getJson(request, `/api/deals/cases/${probe}`);
  const runs = await getJson(request, `/api/agents/runs?client=deal:${s.noAiClient}`);
  await page.goto("/agents");
  await shot(page, "4b-agents-console");
  evidence("4b", { probe: view.ref, refused, cost: view.cost, runs: runs.runs.map((r: any) => [r.task, r.outcome, r.cost_usd, r.tokens_in, r.tokens_out, r.subject]), stats: runs.stats });
  for (const [, status, text] of refused) {
    expect.soft(status).toBe(409);
    expect.soft(String(text)).toMatch(/does not permit AI/);
  }
  expect(view.cost.calls).toBe(0);
  expect(runs.runs.length).toBeGreaterThan(0);
  expect(runs.runs.every((r: any) => r.outcome === "refused" && r.cost_usd === 0 && r.tokens_in === 0)).toBe(true);
  expect(runs.stats.runs).toBe(0);
  expect(runs.stats.cost_usd).toBe(0);
});

// 5. A fresh Harbourline month, for the report text (through the API: the UI path is test 3)

test("5 a fresh Harbourline month drafts a report with the trigger status filled", async ({ request }) => {
  const s = load();
  test.skip(Boolean(s.harbourDrafted), "done");
  const h = (p: string, code = false) => ({ headers: H(p, code) });
  const ok = async (res: Promise<import("@playwright/test").APIResponse>) => {
    const r = await res;
    expect(r.status(), `${r.url()} ${(await r.text()).slice(0, 500)}`).toBe(200);
    return r.json();
  };
  // The released FAC-2001 report from the earlier run, as it stands.
  const old = await ok(request.get("/api/deals/submissions/1", h("priya")));
  evidence("5-old-FAC-2001", { ref: old.ref, drafted_by: old.state.report?.drafted_by, text: old.state.report?.text });

  const client = s.harbourClient ?? (await ok(request.post("/api/deals/clients", { ...h("alex"), data: { name: `Ashgrove Capital Partners LP ${s.run}`, contact_name: `Nadia Brooks ${s.run}`, ai_permitted: true, approval_levels: 2 } }))).id;
  save({ harbourClient: client });
  let c = s.harbourCase ? await ok(request.get(`/api/deals/cases/${s.harbourCase}`, h("hannah"))) : await ok(request.post("/api/deals/cases", { ...h("hannah"), data: { client_id: client, facility_name: "Harbourline Consumer Receivables LLC", deal_type: "Consumer instalment", commitment: 150000000 } }));
  const cid = c.id;
  save({ harbourCase: cid });
  const step = (name: string, body?: unknown, persona = "hannah", code = false) => ok(request.post(`/api/deals/cases/${cid}/${name}`, { ...h(persona, code), data: body ?? {} }));
  if (!c.facility_id) {
    if (!c.documents_list?.length) {
      for (const f of ["Harbourline_Loan_and_Security_Agreement.pdf", "Harbourline_First_Amendment.pdf", "Harbourline_Loan_Tape_2026-09.csv", "Ashgrove_Harbourline_BB_Model_v1.xlsx", "Harbourline_Servicer_Report_September_2026.pdf"]) {
        c = await ok(request.post(`/api/deals/cases/${cid}/documents?name=${f}&kind=auto`, { ...h("hannah", true), data: fs.readFileSync(`${FILES}/harbourline/onboarding/${f}`) }));
      }
      c = await step("classify", {}, "hannah", true);
      c = await step("extract", {}, "hannah", true);
      c = await step("terms/approve-verified");
      for (const [key, t] of Object.entries<any>(c.state.terms)) {
        if (t.status === "proposed" && t.verified && t.typed !== null) c = await step(`terms/${key}`, { action: "approve" });
        else if (["missing", "proposed"].includes(t.status) && !["commitment", "advance_rate"].includes(key)) c = await step(`terms/${key}`, { action: "absent", reason: "Checked: not stated in the agreement" });
      }
      c = await step("rules/draft", {}, "hannah", true);
      for (const kind of ["eligibility", "concentration"]) {
        for (const r of c.state.rules[kind]) {
          if (!r.verified) c = await step("rules", { action: "remove", kind, id: r.id, reason: `Failed code check: ${r.problem}` });
        }
      }
      c = await step("rules", { action: "approve" });
      c = await step("mapping/suggest", {}, "hannah", true);
      c = await step("mapping", {});
      c = await step("validate", { as_of: "2026-09-30" });
    }
    for (const e of c.state.exceptions) {
      if (e.status !== "open" || e.severity === "info") continue;
      c = await step(`exceptions/${e.ref}`, { action: e.type === "Client model" ? "query" : "accept", note: e.type === "Client model" ? "Please confirm the rate your model uses" : "Reviewed against the documents" });
    }
    for (const e of c.state.exceptions.filter((x: any) => x.status === "with_client")) {
      await ok(request.post(`/api/deals/queries/${cid}/${e.ref}/answer`, { ...h(`client-${client}`), data: { text: "We will update our model to 86%." } }));
    }
    c = await ok(request.get(`/api/deals/cases/${cid}`, h("hannah")));
    for (const e of c.state.exceptions.filter((x: any) => ["answered", "decided"].includes(x.status))) {
      c = await step(`exceptions/${e.ref}`, { action: "close" });
    }
    c = await step("submit-qc");
    for (const item of c.qc_items) c = await step("qc", { item: item.id, result: "agrees" }, "tom");
    c = await step("qc/complete", {}, "tom");
    c = await step("approve", { reason: null }, "marcus");
    c = await step("go-live", {}, "marcus");
  }
  const facility = await ok(request.get(`/api/deals/facilities/${c.facility_id}`, h("priya")));
  const sid = facility.submissions[0].id;
  save({ harbourFacility: c.facility_id, harbourSub: sid });
  const sub = (name: string, body?: unknown, code = false) => ok(request.post(`/api/deals/submissions/${sid}/${name}`, { ...h("priya", code), data: body ?? {} }));
  for (const [f, kind] of [["Harbourline_Loan_Tape_2026-10.csv", "loan_tape"], ["Harbourline_Servicer_Report_October_2026.pdf", "servicer_report"]]) {
    await ok(request.post(`/api/deals/submissions/${sid}/documents?name=${f}&kind=${kind}`, { ...h("priya", true), data: fs.readFileSync(`${FILES}/harbourline/monthly/${f}`) }));
  }
  let v = await sub("map", {}, true);
  if (!v.state.mapping.confirmed) v = await sub("mapping", {});
  v = await sub("process", {}, true);
  for (let round = 0; round < 3; round++) {
    for (const f of v.state.findings) {
      if (f.decision) continue;
      v = await sub(`triage/${f.ref}`, f.severity === "blocking" || f.suggested.outcome === "expert" ? { outcome: "confirmed", note: "Rows excluded from the load; corrected file requested" } : { outcome: f.suggested.outcome, note: "" });
    }
  }
  v = await sub("report/draft", {}, true);
  const report = v.state.report;
  evidence("5", { facility: facility.ref, sub: v.ref, drafted_by: report.drafted_by, text: report.text, template: report.template, tests: { avg: v.state.tests.delinquency_average, limit: v.state.tests.delinquency_limit }, cost: v.cost });
  save({ harbourDrafted: true });
  for (const p of report.text) {
    expect.soft(p).not.toMatch(/\{\{|\}\}/);
    expect.soft(p).not.toMatch(OFF_TOPIC);
    expect.soft(p).not.toMatch(/ as \.|  /);
  }
  expect(report.text.join(" ")).toMatch(/within limits|near the limit|breached|below the trigger|above the trigger/);
});
