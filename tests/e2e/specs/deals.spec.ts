/* New deals end to end through the browser, switching persona at each hand-off:
 * (a) a new client and a consumer-instalment onboarding from upload to go-live,
 * (b) its first monitoring month to a released report,
 * (c) a client outside the AI scope (existing process), onboarded by hand, with the client
 *     model Oxane builds because the client has none, validated by the client in the portal.
 *
 * (a) and (b) need the model. They run against the deterministic test model when the API has
 * DEALS_STUB_MODEL=1 (the CI variant), and against the live model only when E2E_LIVE=1 and a key
 * is configured. (c) makes no model calls and always runs. Needs DEMO_ACCESS_CODE. */
import { expect, test, type Page } from "@playwright/test";
import { prepare, resetCase } from "./helpers";

const CODE = process.env.DEMO_ACCESS_CODE ?? "";
const FILES = process.env.NEWDEALS_DIR ?? "/newdeals";
const run = Math.random().toString(36).slice(2, 7);
const ASHGROVE = `Ashgrove Capital Partners LP ${run}`;
const KINGSGATE = `Kingsgate Bank N.A. ${run}`;
const state: { caseUrl?: string; facilityUrl?: string; contact?: string; subPath?: string; clientName?: string } = {};

test.describe.configure({ mode: "serial", timeout: 360_000 });

async function switchTo(page: Page, name: string, within = "") {
  await page.getByRole("button", { name: /^Acting as/ }).click();
  await page.getByRole("menuitemradio", { name: new RegExp(`${name}.*${within}`) }).click();
  await expect(page.getByRole("button", { name: new RegExp(`^Acting as ${name}`) })).toBeVisible();
}

async function enterCode(_page: Page) {
  // There is no access code any more: uploads, live AI and settings need only the right persona.
}

/** Click each matching button in turn, waiting each time until the screen has caught up. */
async function clickEach(page: Page, find: () => ReturnType<Page["getByRole"]>, before?: () => Promise<void>) {
  for (let i = 0; i < 40; i++) {
    const count = await find().count();
    if (!count || !(await find().first().isVisible().catch(() => false))) {
      return;
    }
    if (before) {
      await before();
    }
    await find().first().click();
    await expect.poll(() => find().count(), { timeout: 20_000 }).toBeLessThan(count);
  }
}

async function tab(page: Page, name: string) {
  await page.getByRole("navigation", { name: "Sections" }).getByRole("link", { name: new RegExp(`^${name}`) }).click();
}

async function createClient(page: Page, name: string, contact: string, ai: boolean) {
  await page.goto("/clients");
  await switchTo(page, "Alex Morgan");
  await page.goto("/clients");
  await page.getByRole("button", { name: "New client" }).click();
  await page.getByRole("button", { name: "Create client" }).click();
  await expect(page.getByText("Enter the client's legal name")).toBeVisible();
  await page.getByLabel("Legal name").fill(name);
  await page.getByLabel("Named client contact").fill(contact);
  if (!ai) {
    await page.getByLabel("AI").selectOption("no");
  }
  await page.getByRole("button", { name: "Create client" }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
}

async function openCase(page: Page, client: string, facility: string, dealType: string, commitment: string) {
  await switchTo(page, "Hannah Cole");
  await expect(page.getByRole("link", { name: new RegExp(`New client ${client}`) })).toBeVisible();
  await page.getByRole("link", { name: new RegExp(`New client ${client}`) }).click();
  await page.getByRole("button", { name: "New case" }).click();
  await page.getByLabel("Facility name").fill(facility);
  await page.getByLabel("Deal type").selectOption(dealType);
  await page.getByLabel("Commitment (US$)").fill(commitment);
  await page.getByRole("button", { name: "Open case" }).click();
  await expect(page.getByRole("heading", { level: 1, name: facility })).toBeVisible();
  state.caseUrl = page.url().replace(/\/documents$/, "");
}

async function recordReporting(page: Page) {
  await tab(page, "Reporting");
  await page.getByRole("button", { name: "Record requirements" }).click();
  await expect(page.getByText(/v1 · recorded by Hannah Cole/)).toBeVisible();
}

async function workAllExceptions(page: Page) {
  await tab(page, "Exceptions");
  await clickEach(
    page,
    () => page.getByRole("button", { name: "Accept", exact: true }),
    () => page.getByLabel(/^Note for/).first().fill("Reviewed against the documents"),
  );
}

async function qcAndApprove(page: Page, facility: string) {
  await tab(page, "QC");
  await page.getByRole("button", { name: "Submit for QC" }).click();
  await expect(page.getByText(/In QC · submitted by Hannah Cole/)).toBeVisible();
  await switchTo(page, "Tom Fairley");
  const casePath = new URL(state.caseUrl!).pathname;
  await page.locator(`main a[href="${casePath}/qc"]`).first().click();
  await expect(page.getByRole("button", { name: "Agrees", exact: true }).first()).toBeVisible();
  await clickEach(page, () => page.getByRole("button", { name: "Agrees", exact: true }));
  await page.getByRole("button", { name: "Complete QC" }).click();
  await expect(page.getByText(/Passed · Tom Fairley/)).toBeVisible();
  await switchTo(page, "Marcus Hale");
  await page.locator(`main a[href="${casePath}/approval"]`).first().click();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/Approved by Marcus Hale/)).toBeVisible();
  await page.getByRole("button", { name: "Go live" }).click();
  await expect(page.getByText(/Sent to Panorama · receipt PNR-/)).toBeVisible();
  await page.getByRole("link", { name: "Open facility" }).click();
  await expect(page.getByRole("heading", { level: 1, name: facility })).toBeVisible();
  state.facilityUrl = page.url();
}

test.beforeAll(async ({ request }) => {
  const status = await (await request.get("/api/deals/status")).json();
  expect(status.access_configured).toBe(true);
});

test("(a) a new client onboards a consumer-instalment deal from upload to go-live", async ({ page, request }) => {
  const status = await (await request.get("/api/deals/status")).json();
  test.skip(status.mode === "replay", "No model available: set DEALS_STUB_MODEL=1 or a key");
  test.skip(status.mode === "live" && process.env.E2E_LIVE !== "1", "Live model runs only with E2E_LIVE=1");
  const facility = "Harbourline Consumer Receivables LLC";
  await createClient(page, ASHGROVE, "Nadia Brooks", true);
  state.contact = "Nadia Brooks";
  await enterCode(page);
  await openCase(page, ASHGROVE, facility, "Consumer instalment", "150000000");
  await page.getByLabel("Choose files").setInputFiles([
    `${FILES}/harbourline/onboarding/Harbourline_Loan_and_Security_Agreement.pdf`,
    `${FILES}/harbourline/onboarding/Harbourline_First_Amendment.pdf`,
    `${FILES}/harbourline/onboarding/Harbourline_Loan_Tape_2026-09.csv`,
    `${FILES}/harbourline/onboarding/Ashgrove_Harbourline_BB_Model_v1.xlsx`,
    `${FILES}/harbourline/onboarding/Harbourline_Servicer_Report_September_2026.pdf`,
  ]);
  await expect(page.getByText("5 active")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Classify with AI" }).click();
  await expect(page.getByLabel("Type of Harbourline_First_Amendment.pdf")).toHaveValue("amendment");

  await tab(page, "Terms");
  await page.getByRole("button", { name: "Extract terms" }).click();
  await expect(page.getByText("86.00%", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/88\.00% \(Harbourline_Loan_and_Security_Agreement\.pdf p\.\d\)/)).toBeVisible();
  await page.getByRole("button", { name: "Approve verified Tier 2 and 3" }).click();
  await clickEach(page, () => page.getByRole("button", { name: "Approve", exact: true }));
  await expect(page.getByText(/13\/13 approved/)).toBeVisible();
  await recordReporting(page);

  await tab(page, "Rules");
  await page.getByRole("button", { name: "Draft with AI" }).click();
  if (status.mode === "live") {
    // The live model words its clause references its own way; what matters is a checked rule set.
    await expect(page.getByRole("button", { name: "Approve rule set" })).toBeEnabled({ timeout: 120_000 });
  } else {
    await expect(page.getByText("Schedule B, para 4 (added by the First Amendment)", { exact: false })).toBeVisible({ timeout: 60_000 });
  }
  await page.getByRole("button", { name: "Approve rule set" }).click();
  await expect(page.getByText(/approved by Hannah Cole/)).toBeVisible();

  await tab(page, "Mapping");
  await page.getByRole("button", { name: "Suggest mapping" }).click();
  await page.getByRole("button", { name: "Confirm and store" }).click();
  await expect(page.getByText(/confirmed by Hannah Cole/)).toBeVisible();

  await tab(page, "Validation");
  await page.getByLabel("Reporting date").fill("2026-09-30");
  await page.getByRole("button", { name: "Validate and run" }).click();
  await expect(page.getByText("US$13,687,998.52")).toBeVisible({ timeout: 60_000 });

  await tab(page, "Exceptions");
  const model = page.getByRole("listitem").filter({ hasText: "Client model advance rate 88.00 against 86.00" });
  await model.getByLabel(/^Note for/).fill("Your model uses 88%; the First Amendment sets 86% from 1 Sep 2026. Please confirm.");
  await model.getByRole("button", { name: "Query client" }).click();
  await expect(model.getByText("With client")).toBeVisible();
  await workAllExceptions(page);

  await switchTo(page, "Nadia Brooks", ASHGROVE);
  await expect(page).toHaveURL(/\/portal$/);
  await page.getByLabel("Answer").fill("Agreed: we will update our model to 86%.");
  await page.getByRole("button", { name: "Send answer" }).click();
  await expect(page.getByText("Your answer: Agreed")).toBeVisible();

  await switchTo(page, "Hannah Cole");
  await page.locator(`main a[href="${new URL(state.caseUrl!).pathname}/exceptions"]`).first().click();
  await page.getByRole("button", { name: "Close with this answer" }).click();
  await qcAndApprove(page, facility);
});

test("(b) its first monitoring month runs through to a released report", async ({ page, request }) => {
  const status = await (await request.get("/api/deals/status")).json();
  test.skip(status.mode === "replay" || (status.mode === "live" && process.env.E2E_LIVE !== "1"), "No model available");
  if (!state.facilityUrl) {
    // Run on its own: continue the latest consumer facility that went live from run (a).
    const facilities = await (await request.get("/api/deals/facilities", { headers: { "X-Acting-User": "priya" } })).json();
    const live = facilities.filter((f: { name: string; status: string; latest: { status: string } | null }) => f.name.startsWith("Harbourline") && f.status === "live" && f.latest?.status !== "released").at(-1);
    test.skip(!live, "Needs a facility from run (a)");
    state.facilityUrl = `/facilities/${live.id}`;
    state.clientName = live.client.name;
  }
  await page.goto(state.facilityUrl!);
  await switchTo(page, "Priya Raman");
  await page.locator(`main a[href="${new URL(state.facilityUrl!, "http://x").pathname}"]`).first().click();
  await page.getByRole("link", { name: "Open" }).first().click();
  state.subPath = new URL(page.url()).pathname;
  await enterCode(page);
  await page.getByLabel("Choose loan tape").setInputFiles(`${FILES}/harbourline/monthly/Harbourline_Loan_Tape_2026-10.csv`);
  await page.getByLabel("Choose servicer report").setInputFiles(`${FILES}/harbourline/monthly/Harbourline_Servicer_Report_October_2026.pdf`);
  await expect(page.getByText("Harbourline_Servicer_Report_October_2026.pdf", { exact: false }).first()).toBeVisible();
  await page.getByRole("button", { name: "Map tape" }).click();
  await expect(page.getByText(/Layout unchanged: the facility's stored mapping was reused, no AI/)).toBeVisible();
  // A status value the onboarding tape did not have (PAID_OFF) needs the analyst to confirm it.
  const confirm = page.getByRole("button", { name: "Confirm and store" });
  if (await confirm.isVisible().catch(() => false)) {
    await expect(page.getByLabel("Standard status for PAID_OFF")).toHaveValue("paid_off");
    await confirm.click();
    await expect(confirm).toBeHidden();
  }
  // No button to press: validation ran on its own and the blocking duplicate held the load.
  await expect(page.getByText(/The load is held by a blocking check/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/Automatic after validation by Workbench \(automatic\)/)).toBeVisible();
  const dup = page.getByRole("listitem").filter({ hasText: "Each loan appears once" });
  await dup.getByLabel(/^Outcome for/).selectOption("confirmed");
  await dup.getByLabel(/^Reason for/).fill("Duplicate account excluded; corrected tape requested from the servicer");
  await dup.getByRole("button", { name: "Decide" }).click();
  await expect(page.getByText(/Hold released by Priya Raman/)).toBeVisible();
  await page.getByRole("button", { name: "Re-run calculations" }).click();
  await expect(page.getByText("Borrowing base", { exact: true })).toBeVisible({ timeout: 60_000 });
  await clickEach(page, () => page.getByRole("button", { name: "Decide", exact: true }));
  await page.getByRole("button", { name: "Draft report" }).click();
  // The live model drafts its own wording; the stub's template starts "The pool stood at". Either
  // way the draft is ready when level 1 approval is offered.
  await expect(page.getByRole("button", { name: "Approve, level 1" })).toBeEnabled({ timeout: 120_000 });
  await page.getByRole("button", { name: "Approve, level 1" }).click();
  await switchTo(page, "Marcus Hale");
  await page.locator(`main a[href="${state.subPath}"]`).first().click();
  await page.getByRole("button", { name: "Approve, level 2" }).click();
  await expect(page.getByText("Released", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Sent to Panorama · receipt PNR-/)).toBeVisible();
  await switchTo(page, state.contact ?? "Nadia Brooks", state.clientName ?? ASHGROVE);
  await expect(page.getByText("Harbourline Consumer Receivables LLC").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Workbook" })).toBeVisible();
  await page.goto("/monitoring");
  await expect(page).toHaveURL(/\/portal$/);
});

test("(c) a client outside the AI scope onboards by hand, and validates the model Oxane built", async ({ page }) => {
  const facility = "Fenwick SME Funding LLC";
  await createClient(page, KINGSGATE, "Rosa Lind", false);
  await enterCode(page);
  await openCase(page, KINGSGATE, facility, "SME loans", "80000000");
  await page.getByLabel("Type", { exact: true }).selectOption("agreement");
  await page.getByLabel("Choose files").setInputFiles(`${FILES}/fenwick/onboarding/Fenwick_Receivables_Financing_Agreement.pdf`);
  await expect(page.getByText("1 active")).toBeVisible();
  await page.getByLabel("Type", { exact: true }).selectOption("loan_tape");
  await page.getByLabel("Choose files").setInputFiles(`${FILES}/fenwick/onboarding/Fenwick_Portfolio_2026-09.xlsx`);
  await expect(page.getByText("2 active")).toBeVisible();
  await expect(page.getByRole("button", { name: "Classify with AI" })).toBeDisabled();
  await expect(page.getByText("Existing process — outside AI scope").first()).toBeVisible();

  await tab(page, "Terms");
  await page.getByRole("button", { name: "Start manual entry" }).click();
  const doc = "Fenwick_Receivables_Financing_Agreement.pdf";
  const enter = async (label: string, key: string, value: string, pageNo: string) => {
    // One entry form at a time: wait for the last save to close its form.
    await expect(page.getByRole("button", { name: "Save and approve" })).toHaveCount(0);
    const row = page.getByRole("row").filter({ hasText: label }).first();
    await row.getByRole("button", { name: "Enter" }).click();
    await page.locator(`#v-${key}`).fill(value);
    await page.locator(`#d-${key}`).selectOption(doc);
    await page.locator(`#p-${key}`).fill(pageNo);
    await page.getByRole("button", { name: "Save and approve" }).click();
  };
  await enter("Facility limit", "commitment", "US$80,000,000", "1");
  await expect(page.getByText(/This value is not on page 1/)).toBeVisible();
  await page.locator("#p-commitment").fill("2");
  await page.getByRole("button", { name: "Save and approve" }).click();
  await expect(page.getByRole("row").filter({ hasText: "Facility limit" }).getByText("Approved")).toBeVisible();
  await enter("Advance rate", "advance_rate", "70.00%", "2");
  await enter("Delinquency trigger", "delinquency_trigger", "7.50%", "3");
  await clickEach(page, () => page.getByRole("button", { name: "Not in documents" }));
  await recordReporting(page);

  await tab(page, "Rules");
  await page.getByRole("button", { name: "Add rule" }).first().click();
  await page.getByLabel("Clause reference").fill("First Schedule (a)");
  await page.getByLabel("Plain English").fill("Not more than 30 days in arrears");
  await page.getByLabel("Clause text, copied from the document").fill("the loan is not more than 30 days in arrears;");
  await page.getByLabel("Field", { exact: true }).selectOption("days_past_due");
  await page.getByLabel("Threshold").fill("30");
  await page.getByRole("button", { name: "Check and add" }).click();
  await expect(page.getByText("days_past_due <= 30")).toBeVisible();
  await page.getByRole("button", { name: "Approve rule set" }).click();

  await tab(page, "Mapping");
  await page.getByRole("button", { name: "Suggest mapping" }).click();
  await expect(page.getByText(/Name matching/)).toBeVisible();
  await page.getByRole("button", { name: "Confirm and store" }).click();

  await tab(page, "Validation");
  await page.getByLabel("Reporting date").fill("2026-09-30");
  await page.getByRole("button", { name: "Validate and run" }).click();
  await expect(page.getByText("Borrowing base", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/model cost US\$0\.00/)).toBeVisible();

  // No client model: Oxane builds one in code and the client validates it.
  await tab(page, "Client model");
  await page.getByRole("button", { name: "Build client model" }).click();
  await expect(page.getByText(/Notes from the code template/)).toBeVisible();
  await page.getByRole("button", { name: "Send to client for validation" }).click();
  await expect(page.getByText(/v1 · With the client/)).toBeVisible();
  await workAllExceptions(page);
  await switchTo(page, "Rosa Lind", KINGSGATE);
  await expect(page).toHaveURL(/\/portal$/);
  await expect(page.getByRole("link", { name: "The model Oxane built for you" })).toBeVisible();
  await page.getByLabel("Answer").fill("The model matches how we calculate the base.");
  await page.getByRole("button", { name: "Confirm the model" }).click();
  await expect(page.getByText(/model confirmed/)).toBeVisible();
  await switchTo(page, "Hannah Cole");
  await page.goto(`${new URL(state.caseUrl!).pathname}/client-model`);
  await page.getByRole("button", { name: "Close: model agreed" }).click();
  await expect(page.getByText(/v1 · Confirmed by the client/)).toBeVisible();
  await expect(page.getByText(/model cost US\$0\.00/)).toBeVisible();
  await qcAndApprove(page, facility);
});

test("(d) the scripted case 0412 hands an escalation to the credit expert and back", async ({ page, request }) => {
  test.skip(test.info().project.name === "azure", "Resets the shared scripted case, so it runs locally only");
  await prepare(request, "worked");
  await page.addInitScript(() => window.localStorage.setItem("oxane.persona", "ruth"));
  await page.goto("/work");
  await expect(page.getByRole("button", { name: /^Acting as Ruth Adeyemi/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Expert judgement: X5, case 0412" }).first()).toBeVisible();
  await page.getByLabel("Decision and reasoning").fill("Treat the shared VINs as double pledged; keep excluded");
  await page.getByRole("button", { name: "Record decision" }).click();
  // It moves from waiting to recently done.
  await expect(page.getByText(/done .* by Ruth Adeyemi/).first()).toBeVisible();
  await switchTo(page, "Hannah Cole");
  await expect(page.getByRole("link", { name: "Expert decision: X5, case 0412" }).first()).toBeVisible();
  await expect(page.getByText(/handed over by Ruth Adeyemi/).first()).toBeVisible();
  await resetCase(request);
});
