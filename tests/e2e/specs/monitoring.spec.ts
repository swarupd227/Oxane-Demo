/* The monitoring workbench's scripted May 2026 cycle, worked through the browser by each persona in
 * turn: Priya prepares, Ruth decides what needs expert judgement, Tom clears the independent QC
 * variance, Marcus and Elena approve at the levels each client requires, and the client contacts
 * see only what has been released to them. The tests run in order on one cycle session, which is
 * reset first through the app's own reset, as the other specs do. */
import { expect as baseExpect, test, type Page } from "@playwright/test";
import { isHosted, kpi, myWork, openAs, resetCycle, switchTo, waitForScreen } from "./personas";
import { readDownload, readWorkbook } from "./xlsx";

// The shared local stack can be slow while other suites run; wait on state, for longer.
const expect = baseExpect.configure({ timeout: 30_000 });

test.describe.configure({ mode: process.env.DEV_CONTINUE ? "default" : "serial", timeout: 300_000 });

const BRAMBLE = "Bramble Auto Receivables I";
const NORTHMOOR = "Northmoor Motor Credit Trust";
const LARKSPUR = "Larkspur CLO 2026-1 Warehouse";

test.beforeAll(async ({ request, baseURL }) => {
  test.skip(isHosted(baseURL), "Resets the shared cycle session, so it runs against a local stack only");
  await resetCycle(request);
});

async function monitoring(page: Page, path: string, heading: string, persona = "Priya Raman") {
  await openAs(page, persona, path);
  await waitForScreen(page, heading);
}

/** The row count a data table reports in its toolbar ("26 records", or "2 of 26"). */
function records(page: Page) {
  return page.getByText(/^(\d+ records|\d+ of \d+)$/).first();
}

function facilityTab(page: Page, name: string) {
  return page.getByRole("tab", { name: new RegExp(`^${name}`) });
}

/** The sign-off panel that lists what blocks approval; the Approve button stays disabled meanwhile. */
function blocked(page: Page) {
  return page.getByRole("status").filter({ hasText: "Approval is blocked" });
}

/** Ask the API directly to approve a facility's report as the acting persona, as a client that
 * ignored the disabled button would: the server must still refuse. */
async function approveDirectly(page: Page, facility: string) {
  return page.evaluate(async (id) => {
    const response = await fetch("/api/monitoring/session/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "approve-pack", actor: "analyst", payload: { facility: id } }),
    });
    return { status: response.status, detail: ((await response.json()) as { detail?: string }).detail ?? "" };
  }, facility);
}

async function packFor(page: Page, persona: string, facility: string) {
  await monitoring(page, "/monitoring/pack", "Reports", persona);
  await facilityTab(page, facility).click();
  await expect(page.getByRole("heading", { level: 2, name: facility })).toBeVisible();
}

test("portfolio: 26 facilities across both clients, filters and the facility drawer with its document schedule", async ({ page }) => {
  await monitoring(page, "/monitoring", "Portfolio");
  const client = page.getByRole("combobox", { name: "Client" });

  // The scripted book: 18 Calderwood facilities and 8 Thornbury, 26 in all. Facilities onboarded
  // as new deals belong to their own clients, so the two scripted clients are counted apart.
  await client.selectOption({ label: "Calderwood Bank plc" });
  await expect(kpi(page, "Facilities")).toHaveText("18");
  await expect(records(page)).toHaveText("18 records");
  await client.selectOption({ label: "Thornbury Bank N.A." });
  await expect(kpi(page, "Facilities")).toHaveText("8");
  await expect(records(page)).toHaveText("8 records");

  // Thornbury: five CLO warehouses; two facilities in breach (Larkspur's CCC bucket and Wharfedale's base).
  await page.getByRole("combobox", { name: "Asset class" }).selectOption("CLO / BSL");
  await expect(records(page)).toHaveText("5 records");
  await page.getByRole("combobox", { name: "Asset class" }).selectOption("all");
  await page.getByRole("combobox", { name: "Status" }).selectOption("breach");
  await expect(records(page)).toHaveText("2 records");
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: LARKSPUR })).toHaveCount(1);
  await expect(rows.filter({ hasText: "Wharfedale Infrastructure Partners III" })).toHaveCount(1);
  for (const row of await rows.all()) {
    await expect(row.getByText("Breach", { exact: true })).toBeVisible();
  }

  // The drawer: Larkspur's files and its daily-feed document schedule.
  await rows.filter({ hasText: LARKSPUR }).click();
  const drawer = page.getByRole("complementary", { name: `${LARKSPUR} details` });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("Thornbury Bank N.A.", { exact: false }).first()).toBeVisible();
  await expect(drawer.getByText("SUB-2026-05-0014", { exact: true })).toBeVisible();
  await expect(drawer.getByText("SUB-2026-05-0015", { exact: true })).toBeVisible();
  await expect(drawer.getByRole("link", { name: "CLO / BSL" })).toBeVisible();
  const line = (document: string) => drawer.locator("tr").filter({ hasText: document });
  await expect(line("Daily position file")).toContainText("20/20");
  await expect(line("Daily position file")).toContainText("Received late");
  await expect(line("Daily prices")).toContainText("19/20");
  await expect(line("Daily prices")).toContainText("Outstanding");
  await expect(line("Daily ratings feed")).toContainText("Complete");
  await expect(drawer.getByRole("link", { name: "EXC-2026-05-0160" })).toBeVisible();
  await expect(page).toHaveURL(/facility=larkspur/);
  await drawer.getByRole("button", { name: "Close" }).click();
  await expect(drawer).toBeHidden();
});

test("submissions: channels, deadlines, the late servicer report's chases and Larkspur's daily feeds", async ({ page }) => {
  await monitoring(page, "/monitoring/submissions", "Submissions");
  await expect(kpi(page, "Expected")).toHaveText("154");
  await expect(kpi(page, "Overdue")).toHaveText("3");
  await expect(kpi(page, "Received late")).toHaveText("7");
  await expect(kpi(page, "Reused")).toHaveText("1");
  await expect(kpi(page, "Deadline missed")).toHaveText("2");

  const byChannel = page.locator("section").filter({ has: page.getByRole("heading", { name: "By channel" }) });
  for (const [channel, count] of [["Email", 66], ["Data room", 47], ["SFTP", 18], ["Upload", 18], ["API", 5]] as const) {
    await expect(byChannel.locator("li").filter({ hasText: channel })).toContainText(String(count));
  }
  await page.getByRole("combobox", { name: "Channel" }).selectOption("API");
  await expect(records(page)).toHaveText("5 records");
  await page.getByRole("combobox", { name: "Channel" }).selectOption("all");

  // The late servicer report: overdue, internal deadline due today, two chases logged.
  await page.getByRole("combobox", { name: "Status" }).selectOption("late");
  await expect(records(page)).toHaveText("3 records");
  const late = page.locator("tbody tr").filter({ hasText: "SUB-2026-05-0010" });
  await expect(late).toContainText("Servicer report, May");
  await expect(late).toContainText("Overdue");
  await expect(late).toContainText("Due today");
  await late.getByRole("button", { name: "2 chases" }).click();
  const dialog = page.getByRole("dialog", { name: "SUB-2026-05-0010 · chase log" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("li")).toHaveCount(2);
  await expect(dialog.getByText(/^To: /).first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // Daily feeds: 59 of 60 deliveries; the 21 May price file never came, the 14 May position file came late.
  await page.getByRole("tab", { name: /^Daily feeds/ }).click();
  await expect(page).toHaveURL(/view=daily/);
  await expect(page.getByRole("tab", { name: /^Daily feeds/ })).toContainText("2");
  await expect(page.getByText("59 of 60 deliveries · 20 business days")).toBeVisible();
  const exceptions = page.locator("section").filter({ has: page.getByRole("heading", { name: "Exceptions", exact: true }) });
  const missing = exceptions.locator("li").filter({ hasText: "Daily prices, 21 May 2026" });
  await expect(missing).toContainText("Not received by 2026-05-21 18:00; no resend");
  await expect(missing).toContainText("Query");
  const lateFile = exceptions.locator("li").filter({ hasText: "Daily position file, 14 May 2026" });
  await expect(lateFile).toContainText("3 h 42 min after the deadline; 60 rows");
  await expect(lateFile).toContainText("Logged");
  await expect(page.getByLabel("Daily prices, 21 May 2026: missing")).toBeVisible();
  await expect(page.getByLabel("Daily position file, 14 May 2026: late")).toBeVisible();

  // Schedules: every facility's expected documents, outstanding ones first.
  await page.getByRole("tab", { name: "Schedules" }).click();
  await page.getByRole("combobox", { name: "Schedule status" }).selectOption("missing");
  await expect(page.locator("tbody tr").filter({ hasText: "Daily prices" })).toContainText(LARKSPUR);
});

test("mapping: stored mapping reused, Bramble's changed layout confirmed, and the layout library with its versions", async ({ page }) => {
  await monitoring(page, "/monitoring/mapping", "Mapping");
  await expect(page.getByText("May 2026 · 5 files · 22 stored layouts")).toBeVisible();
  const file = (name: string) => page.locator("tbody tr").filter({ hasText: name });
  await expect(file("Bramble")).toContainText("2 new columns");
  await expect(file("Bramble")).toContainText("38 of 40");
  await expect(file("Northmoor")).toContainText("Unchanged");
  await expect(file("Northmoor")).toContainText("27 of 27");
  await expect(file("Larkspur")).toContainText("11 of 11");
  await expect(file("Larkspur")).toContainText("No AI");

  // The two new Bramble columns are logged, then confirmed by the analyst.
  await expect(page.getByText("From stored mapping 38/40 · new 2")).toBeVisible();
  for (const column of ["CoBorrower", "GAPCoverage"]) {
    await expect(page.locator("li").filter({ has: page.locator("code", { hasText: column }) })).toContainText("Logged");
  }
  await expect(page.getByText("Awaiting confirmation")).toBeVisible();
  await page.getByRole("button", { name: "Confirm mapping" }).click();
  await expect(page.getByRole("button", { name: "Confirm mapping" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("Confirmed", { exact: true }).first()).toBeVisible();

  // The library: 22 layouts; the loan tape layout has two versions.
  await page.getByRole("tab", { name: "Layout library" }).click();
  await expect(page).toHaveURL(/view=library/);
  await expect(kpi(page, "Stored layouts")).toHaveText("22");
  await expect(records(page)).toHaveText("22 records");
  await page.getByRole("combobox", { name: "Document type" }).selectOption("Loan tape");
  await expect(records(page)).toHaveText("2 records");
  await page.locator("tbody tr").filter({ hasText: "LAY-0101" }).click();
  const history = page.locator("section").filter({ has: page.getByRole("heading", { name: "Version history" }) });
  await expect(history.locator("li")).toHaveCount(2);
  await expect(history.getByText("v2")).toBeVisible();
  await expect(history.getByText("v1")).toBeVisible();
});

test("reconciliation: Bramble's 27 missing loans and Larkspur's identifier change", async ({ page }) => {
  await monitoring(page, "/monitoring/reconciliation", "Reconciliation");
  await expect(page.getByText("US$412,004.04")).toBeVisible();
  await expect(page.getByText("27 loans", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "View 27 loans" }).click();
  const dialog = page.getByRole("dialog", { name: "27 loans missing from the May tape" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("April balance US$422,417.20")).toBeVisible();
  await expect(dialog.locator("tbody tr")).toHaveCount(27);
  await page.keyboard.press("Escape");

  const link = page.locator("div").filter({ has: page.getByText("Identifier change linked", { exact: true }) }).last();
  await expect(link).toContainText("Langdale Education: LoanX LX301245 → LX318806");
  await expect(link).toContainText("51475HAB7 → 51475HAD3");
  await expect(link).toContainText("No trade · matched on issuer, facility, maturity, spread · history carried over · logged");
  await expect(page.getByText(/unexplained 0$/)).toBeVisible();
});

test("covenants: Larkspur's CCC excess and haircut, Ravenglass obligor leverage, Wharfedale's investor exclusion", async ({ page }) => {
  await monitoring(page, "/monitoring/covenants", "Covenants");

  await facilityTab(page, LARKSPUR).click();
  const ccc = page.locator("main");
  await expect(ccc.getByText("CCC bucket and its excess", { exact: true })).toBeVisible();
  await expect(ccc.getByText("Over limit")).toBeVisible();
  await expect(ccc.getByText("8.41%", { exact: true }).first()).toBeVisible();
  await expect(ccc.getByText("April 6.89%").first()).toBeVisible();
  await expect(ccc.getByText("US$4.17m", { exact: true }).first()).toBeVisible();
  await expect(ccc.getByText("US$1,198,515.63", { exact: true }).first()).toBeVisible();
  await expect(ccc.getByText("US$319.59m", { exact: true }).first()).toBeVisible();
  await expect(ccc.getByText(/Rating basis: lower of Moody's and S&P \(client override\)/)).toBeVisible();

  await facilityTab(page, "Ravenglass Direct Lending Fund I").click();
  const hexby = page.locator("tbody tr").filter({ hasText: "Hexby Precision Engineering" });
  await expect(hexby).toContainText("6.43x");
  await expect(hexby).toContainText("6.00x");
  await expect(hexby).toContainText("Over covenant");
  await expect(page.getByRole("button", { name: "All obligors (40)" })).toBeVisible();
  await page.getByRole("button", { name: "All obligors (40)" }).click();
  await expect(page.locator("tbody tr").filter({ hasText: /RVG-\d{3}/ })).toHaveCount(40);

  await facilityTab(page, "Wharfedale Infrastructure Partners III").click();
  await expect(page.getByText("1 exclusion event")).toBeVisible();
  // The exclusion-event card under "Investor eligibility": the one holding the register note.
  const brackley = page
    .getByText("Register still shows Included; excluded by the agreement.", { exact: true })
    .locator("xpath=..");
  await expect(brackley.getByText("Brackley Mutual Insurance", { exact: true })).toBeVisible();
  await expect(brackley).toContainText("A- to BB+");
  await expect(brackley).toContainText("Register still shows Included; excluded by the agreement.");
  await expect(page.getByText("Prepayment due")).toBeVisible();
  await expect(page.getByText("US$13,254,000.00").first()).toBeVisible();
});

test("validation: warnings are logged, Bramble's pool change is explained by a verified quote, Northmoor's load is held", async ({ page }) => {
  await monitoring(page, "/monitoring/validation", "Validation");

  // Northmoor opens first: the blocking duplicate holds the load.
  await expect(facilityTab(page, NORTHMOOR)).toHaveAttribute("aria-selected", "true");
  await expect(facilityTab(page, NORTHMOOR).getByLabel("Load held")).toBeVisible();
  const held = page.getByRole("status");
  await expect(held).toContainText("Load held: blocking rule V04 failed");
  await expect(held).toContainText("Rows in file 3,186 · to load 3,185 · reports provisional");
  const v04 = page.locator("tr").filter({ hasText: "Each loan number appears once" });
  await expect(v04).toContainText("Blocking");
  await expect(v04).toContainText("Blocked(2)");
  await expect(page.locator("tr").filter({ hasText: "Each VIN appears once among loans in the pool" })).toContainText("Warning, logged(2)");

  // Bramble: four warning rules, 13 rows between them, logged without holding the load.
  await facilityTab(page, BRAMBLE).click();
  await expect(page.getByRole("status")).toHaveCount(0);
  const warnings = page.locator("tr").filter({ hasText: "Warning, logged" });
  await expect(warnings).toHaveCount(4);
  let total = 0;
  for (const row of await warnings.all()) {
    total += Number((await row.locator("td").last().innerText()).match(/\((\d+)\)/)?.[1] ?? 0);
  }
  expect(total).toBe(13);

  // The pool rose 12.03%: the cause is drafted from the servicer report and its quote was found.
  await expect(page.locator("tr").filter({ hasText: "+12.03%" })).toBeVisible();
  const cause = page.locator("div").filter({ has: page.getByText("Cause of change", { exact: true }) }).last();
  await expect(cause.getByText("Quote verified")).toBeVisible();
  await expect(cause).toContainText("Pool balance (12.03%) and loan count (9.61%) rose because the April transfer of new receivables was deferred");
  await expect(cause).toContainText("The 300 receivables purchased in this period, totalling US$9,857,582.58");
});

test("reports cannot be approved while findings are open, nor by the analyst who prepared them", async ({ page }) => {
  await packFor(page, "Priya Raman", BRAMBLE);
  await expect(page.getByText("Provisional", { exact: true })).toBeVisible();
  await expect(blocked(page)).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
  // The preparer cannot sign level 2 even by going round the screen.
  expect(await approveDirectly(page, "bramble")).toEqual({ status: 409, detail: "Level 2 is for the second analyst" });

  await packFor(page, "Marcus Hale", BRAMBLE);
  await expect(blocked(page).getByText(/^\d+ open exceptions?$/)).toBeVisible();
  await expect(blocked(page).getByText("QC variance unresolved")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
  const refused = await approveDirectly(page, "bramble");
  expect(refused.status).toBe(409);
  expect(refused.detail).toMatch(/^Every finding needs a decision first/);
});

test("exceptions: every finding is decided, noise stays logged, and expert judgement goes to Ruth and back", async ({ page }) => {
  await monitoring(page, "/monitoring/triage", "Exceptions");
  await expect(page.getByText("May 2026 · 33 raised")).toBeVisible();
  await expect(kpi(page, "Open")).toHaveText("19");
  await expect(kpi(page, "Logged by rule")).toHaveText("14");

  // Logged by rule: noise and items within tolerance, each with its reason, none to decide.
  await page.getByRole("tab", { name: "Logged", exact: true }).click();
  await expect(records(page)).toHaveText("14 records");
  await page.locator("tbody tr").filter({ hasText: "Certificate eligible pool US$3.20 above the recomputed figure" }).click();
  const logged = page.getByRole("region", { name: "Exception EXC-2026-05-0146" });
  await expect(logged).toContainText("Logged by rule");
  await expect(logged.getByRole("button", { name: /^Accept:/ })).toHaveCount(0);
  await page.getByRole("tab", { name: "open", exact: true }).click();
  await expect(records(page)).toHaveText("19 records");
  await page.locator("tbody tr").first().click();

  // Decide each open finding on its suggestion, one after another.
  for (let open = 19; open > 0; open--) {
    const accept = page.getByRole("button", { name: /^Accept: / });
    await expect(accept).toBeEnabled();
    await accept.click();
    await expect(kpi(page, "Open")).toHaveText(String(open - 1));
  }
  await expect(kpi(page, "Decided")).toHaveText("19");
  await expect(kpi(page, "Expert review")).toHaveText("3");
  await expect(kpi(page, "Confirmed")).toHaveText("7");
  await expect(kpi(page, "Queries to sender")).toHaveText("8");
  await expect(page.getByText("No exceptions in this view.")).toBeVisible();

  // The Bramble leverage question went to expert review, recorded against Priya in its history.
  await page.goto("/monitoring/triage?ref=EXC-2026-05-0151");
  const leverage = page.getByRole("region", { name: "Exception EXC-2026-05-0151" });
  await expect(leverage).toContainText("Expert review");
  await expect(leverage.locator("ol li").first()).toContainText("Priya Raman");
  await expect(leverage.locator("ol li").first()).toContainText("Leverage 6.20x if the guarantee counts, against 6.00x: Expert review");

  // Ruth finds it in My work, records her decision, and it comes back to Priya.
  const ruth = await myWork(page, "Ruth Adeyemi");
  const item = ruth.locator("li").filter({ hasText: "Expert judgement: Leverage 6.20x if the guarantee counts, against 6.00x" });
  await expect(item).toBeVisible();
  await expect(item).toContainText("From Priya Raman");
  await expect(ruth.locator("li").filter({ hasText: "Expert judgement: Loan-to-value 30.3%" })).toBeVisible();
  await expect(ruth.locator("li").filter({ hasText: "Expert judgement: Calloway Veterinary Partners" })).toBeVisible();
  await item.getByRole("button", { name: "Record decision" }).click();
  await expect(item.getByText("Record the decision and its reasoning")).toBeVisible();
  await item.getByLabel("Decision and reasoning").fill("The guarantee is contingent, so it stays out of Total Liabilities; covenant passes at 5.88x.");
  await item.getByRole("button", { name: "Record decision" }).click();
  await expect(ruth.locator("li").filter({ hasText: "Expert judgement: Leverage 6.20x" })).toHaveCount(0);

  const priya = await myWork(page, "Priya Raman");
  const back = priya.locator("li").filter({ hasText: "Expert decision: Leverage 6.20x if the guarantee counts, against 6.00x" });
  await expect(back).toBeVisible();
  await expect(back).toContainText("From Ruth Adeyemi");
  await expect(back).toContainText("The guarantee is contingent");
});

test("validation: the held Northmoor load blocks its report until the analyst resolves it", async ({ page }) => {
  await packFor(page, "Marcus Hale", NORTHMOOR);
  await expect(blocked(page).getByText("Load held by blocking check")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
  expect(await approveDirectly(page, "northmoor")).toEqual({ status: 409, detail: "The load is held by a blocking check. Resolve it first" });

  await monitoring(page, "/monitoring/validation", "Validation");
  await expect(page.getByRole("button", { name: "Keep one row and release" })).toBeDisabled();
  await page.getByLabel("Resolution note").fill("Rows identical in every field; servicer confirmed a repeated line.");
  await page.getByRole("button", { name: "Keep one row and release" }).click();
  const status = page.getByRole("status");
  await expect(status).toContainText("Load released by Priya Raman");
  await expect(status).toContainText("Resolution: Rows identical in every field");
  await expect(status).toContainText("3,185 of 3,186 rows loaded");
  await expect(facilityTab(page, NORTHMOOR).getByLabel("Load held")).toHaveCount(0);

  // Calderwood needs two levels: the preparer and a second analyst. Marcus's approval releases it.
  await packFor(page, "Marcus Hale", NORTHMOOR);
  await expect(page.getByText("Load held by blocking check")).toHaveCount(0);
  await expect(blocked(page)).toHaveCount(0);
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("Released", { exact: true })).toBeVisible();
  await expect(page.getByText(/^Released \d/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
});

test("reports: Bramble's QC variance blocks release until Tom resolves it; the workbook goes from provisional to released with live formulas", async ({ page }) => {
  // Provisional workbook first, downloaded from the report.
  await packFor(page, "Priya Raman", BRAMBLE);
  await expect(page.getByText("4 agree · 4 presentation · 1 genuine")).toBeVisible();
  await expect(page.getByText("Gross charge-offs: genuine variance, unresolved")).toBeVisible();
  let download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download .xlsx" }).click();
  let saved = await download;
  expect(saved.suggestedFilename()).toBe("bramble-m-2026-05-provisional.xlsx");
  let book = readWorkbook(await readDownload(saved));
  expect([...book.keys()]).toEqual(expect.arrayContaining(["Summary", "Inputs", "Calculation", "QC comparison"]));
  expect(book.get("Summary")!.cells.get("A2")!.value).toContain("PROVISIONAL");
  const calc = book.get("Calculation")!;
  const formulas = [...calc.cells.values()].filter((c) => c.ref.startsWith("B") && c.formula);
  expect(formulas.length).toBeGreaterThan(5);
  expect(formulas.some((c) => /Inputs!\$B\$\d+/.test(c.formula!))).toBe(true);
  const comparison = book.get("QC comparison")!;
  const charge = comparison.rows.find((r) => r[0]?.value === "Gross charge-offs")!;
  expect(charge).toBeTruthy();
  expect(charge.find((c) => c.ref.startsWith("D"))?.formula).toMatch(/^B\d+-C\d+$/);

  // Marcus cannot approve while the variance is open.
  await packFor(page, "Marcus Hale", BRAMBLE);
  await expect(blocked(page).getByText("QC variance unresolved")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
  expect(await approveDirectly(page, "bramble")).toEqual({ status: 409, detail: "Resolve the genuine QC variance first: Gross charge-offs" });

  // The variance waits on Tom, the QC analyst; he records the resolution.
  const tom = await myWork(page, "Tom Fairley");
  await expect(tom.locator("li").filter({ hasText: `Independent QC variance: ${BRAMBLE}` })).toBeVisible();
  await packFor(page, "Tom Fairley", BRAMBLE);
  await page.getByLabel("QC resolution").fill("Charge-offs in the servicer schedule are on the tape as live loans; QC workbook corrected.");
  await page.getByRole("button", { name: "Record resolution" }).click();
  await expect(page.getByText("Gross charge-offs: Charge-offs in the servicer schedule")).toBeVisible();
  const tomAfter = await myWork(page, "Tom Fairley");
  await expect(tomAfter.locator("li").filter({ hasText: `Independent QC variance: ${BRAMBLE}` })).toHaveCount(0);

  // Now Marcus releases it, and the client contact is told.
  await packFor(page, "Marcus Hale", BRAMBLE);
  await expect(page.getByText("QC variance unresolved")).toHaveCount(0);
  await expect(blocked(page)).toHaveCount(0);
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("Released", { exact: true })).toBeVisible();
  download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download .xlsx" }).click();
  saved = await download;
  expect(saved.suggestedFilename()).toBe("bramble-m-2026-05-released.xlsx");
  book = readWorkbook(await readDownload(saved));
  expect(book.get("Summary")!.cells.get("A2")!.value).not.toContain("PROVISIONAL");

  const queue = page.getByRole("tab", { name: "All reports" });
  await queue.click();
  const bramble = page.locator("tbody tr").filter({ hasText: BRAMBLE });
  await expect(bramble).toContainText("Released");
  await expect(bramble).toContainText("2/2");

  await openAs(page, "James Whitcombe", "/portal");
  await expect(page.getByRole("heading", { level: 1, name: "Calderwood Bank plc" })).toBeVisible();
  const reports = page.locator("section").filter({ has: page.getByRole("heading", { name: "Released reports" }) });
  await expect(reports.locator("li").filter({ hasText: BRAMBLE })).toBeVisible();
});

test("reports: Thornbury needs three levels; Marcus approves level 2 and Elena releases at level 3", async ({ page }) => {
  await packFor(page, "Marcus Hale", LARKSPUR);
  await expect(page.getByText("Sign-off · Thornbury Bank N.A.")).toBeVisible();
  const signoff = page.locator("ol").filter({ hasText: "Level 3" });
  await expect(signoff.locator("li")).toHaveCount(3);
  await expect(signoff.locator("li").filter({ hasText: "Level 3" })).toContainText("Elena Varga");
  await expect(signoff.locator("li").filter({ hasText: "Level 3" })).toContainText("Level 3 · Head of monitoring");
  await expect(signoff.locator("li").filter({ hasText: "Level 2" })).toContainText("Marcus Hale");
  await expect(signoff.locator("li").filter({ hasText: "Level 2" })).toContainText("Level 2 · Second analyst");
  // Marcus signs next: his level is marked as the next to sign.
  await expect(signoff.locator("li").filter({ hasText: "Level 2" })).toContainText("Next");
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("Provisional", { exact: true })).toBeVisible();
  await expect(signoff.locator("li").filter({ hasText: "Level 2" })).toContainText(/\d{4}/);
  // The same reviewer cannot sign the next level.
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Level 3 is for the head of monitoring" })).toBeVisible();

  const elena = await myWork(page, "Elena Varga");
  const item = elena.locator("li").filter({ hasText: `Approve ${LARKSPUR} report, level 3` });
  await expect(item).toBeVisible();
  await expect(item).toContainText("From Marcus Hale");
  await expect(page.locator("section").filter({ has: page.getByRole("heading", { name: "Team workload" }) })).toBeVisible();

  await packFor(page, "Elena Varga", LARKSPUR);
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("Released", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "All reports" }).click();
  await expect(page.locator("tbody tr").filter({ hasText: LARKSPUR })).toContainText("3/3");

  const after = await myWork(page, "Elena Varga");
  await expect(after.locator("li").filter({ hasText: `Approve ${LARKSPUR} report, level 3` })).toHaveCount(0);
});

test("alerts: headroom and early warnings, and a client's preset alert drafted, back-tested and approved", async ({ page }) => {
  await monitoring(page, "/monitoring/monitor", "Alerts");
  await expect(kpi(page, "Tests")).toHaveText("77");
  await expect(kpi(page, "Over limit")).toHaveText("5");
  await expect(kpi(page, "Early warning")).toHaveText("7");
  await expect(kpi(page, "Indicators")).toHaveText("7");
  await expect(kpi(page, "Live client alerts")).toHaveText("0");
  await page.getByRole("combobox", { name: "Status" }).selectOption("over");
  await expect(records(page)).toHaveText("5 records");
  const over = page.locator("table").first().locator("tbody tr");
  await expect(over.filter({ hasText: "CCC share" })).toContainText("8.41%");
  for (const row of await over.all()) {
    await expect(row.getByText("Over limit")).toBeVisible();
  }
  const indicators = page.locator("section").filter({ has: page.getByRole("heading", { name: "Early-warning indicators" }) });
  await expect(indicators.locator("tr")).toHaveCount(7);
  await expect(indicators.locator("tr").filter({ hasText: "Brackley Mutual Insurance" })).toContainText("Rating downgrade");
  await expect(indicators.locator("tr").filter({ hasText: "Denholme Chemicals" })).toContainText("Price move");

  // Thornbury does not permit AI, so its alerts are kept by its named contact.
  const requests = page.locator("section").filter({ has: page.getByRole("heading", { name: "Client alert requests" }) });
  await requests.getByRole("tab", { name: "Thornbury" }).click();
  await expect(requests.getByText("No AI")).toBeVisible();
  await expect(requests.getByText("Daniel Okafor")).toBeVisible();
  await requests.getByRole("tab", { name: "Calderwood" }).click();

  // Calderwood's preset request: drafted into a rule, checked and back-tested.
  await requests.getByRole("button", { name: "Tell me if Northmoor's 60+ day delinquency goes above 5.5%." }).click();
  await expect(requests.getByText("Alert the client when Northmoor's 60+ day delinquency rises above 5.5%.")).toBeVisible();
  await expect(requests.getByText(/delinquency_60_plus > 5\.5/)).toBeVisible();
  await expect(requests.getByText("Rule checks passed")).toBeVisible();
  await expect(requests.getByText(/^Fired in 2 of \d+ periods$/)).toBeVisible();
  await requests.getByRole("button", { name: "Submit request" }).click();
  const list = page.locator("section").filter({ has: page.getByRole("heading", { name: "Requests" }) });
  const request = list.locator("li").filter({ hasText: "ALR-0001" });
  await expect(request).toContainText("back-test fired 2×");

  // The request waits on the analyst in My work, then goes live when she approves it.
  const priya = await myWork(page, "Priya Raman");
  await expect(priya.locator("li").filter({ hasText: "Client alert request: Alert the client when Northmoor's 60+ day delinquency rises above 5.5%." })).toBeVisible();
  await monitoring(page, "/monitoring/monitor", "Alerts");
  await list.locator("li").filter({ hasText: "ALR-0001" }).getByRole("button", { name: "Approve" }).click();
  await expect(list.locator("li").filter({ hasText: "ALR-0001" })).toContainText("Live");
  await expect(list.locator("li").filter({ hasText: "ALR-0001" })).toContainText("approved by Priya Raman");
  await expect(kpi(page, "Live client alerts")).toHaveText("1");

  await openAs(page, "James Whitcombe", "/portal");
  const alerts = page.locator("section").filter({ has: page.getByRole("heading", { name: "Your alert requests" }) });
  await expect(alerts.locator("li").filter({ hasText: "Northmoor's 60+ day delinquency rises above 5.5%" })).toContainText("Live");
});

test("status calls: a brief per client, with its attendees and every figure checked", async ({ page }) => {
  await monitoring(page, "/monitoring/status-call", "Status calls");
  await expect(page.getByRole("heading", { level: 2, name: "Calderwood Bank plc" })).toBeVisible();
  await expect(page.getByText("Status call · Tuesdays 10:00, 20 minutes")).toBeVisible();
  await expect(page.getByText("Drafted", { exact: true })).toBeVisible();
  for (const heading of ["Missing data", "Open questions", "Exclusions", "Identifier changes", "Missing financials", "Waiting on an expert", "Ravenglass Direct Lending Fund I"]) {
    await expect(page.getByRole("heading", { level: 3, name: heading })).toBeVisible();
  }
  await expect(page.getByText(/^For this week's call with Calderwood Bank plc/)).toBeVisible();
  await expect(page.getByText("Number check").locator("..")).toContainText("Passed");
  await expect(page.getByText("Priya Raman · Named contact")).toBeVisible();
  await expect(page.getByText("James Whitcombe · Director")).toBeVisible();

  await page.getByRole("tab", { name: /^Thornbury Bank N\.A\./ }).click();
  await expect(page.getByRole("tab", { name: /^Thornbury Bank N\.A\./ })).toContainText("No AI");
  await expect(page.getByText("Status call · Thursdays 15:00, 15 minutes")).toBeVisible();
  await expect(page.getByText("Template", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { level: 3, name: "Early warnings" })).toBeVisible();
  await expect(page.getByText(/^Larkspur's May cycle ran on code checks only, as Thornbury Bank N\.A\. requires\. Borrowing base US\$/)).toBeVisible();
  await expect(page.getByText("Number check").locator("..")).toContainText("Passed");
  await expect(page.getByText("Daniel Okafor · Named contact")).toBeVisible();
  await expect(page.getByText("Laura Haskett · Head of leveraged finance portfolio")).toBeVisible();
});

test("metrics: 20 of 20 planted issues found, 0 of 8 noise items raised, 49 of 49 values right", async ({ page }) => {
  await monitoring(page, "/monitoring/results", "Metrics");
  await expect(page.getByText("20/20 detected with expected outcome")).toBeVisible();
  await expect(page.getByText("0/8 raised as alerts")).toBeVisible();
  const issues = page.locator("section").filter({ has: page.getByRole("heading", { name: "Control test set: planted issues" }) });
  await expect(issues.getByText("Detected", { exact: true })).toHaveCount(20);
  await expect(issues.getByText("Missed", { exact: true })).toHaveCount(0);
  const noise = page.locator("section").filter({ has: page.getByRole("heading", { name: "Control test set: noise" }) });
  await expect(noise.getByText("Logged", { exact: true })).toHaveCount(8);
  await expect(noise.getByText("Raised", { exact: true })).toHaveCount(0);

  const metric = (name: string) => page.locator("tbody tr").filter({ hasText: name }).filter({ has: page.getByText("Measured", { exact: true }) });
  await expect(metric("Accuracy and completeness of loaded updates and reconciliations")).toContainText("49 of 49 values");
  await expect(metric("Accuracy and completeness of loaded updates and reconciliations").getByLabel("Target met")).toBeVisible();
  await expect(metric("Material issues missed")).toContainText("0");
  await expect(metric("False alerts per cycle")).toContainText("0");
  await expect(metric("Turnaround time per cycle")).toContainText("3 of 6 packs released");
  await page.getByRole("combobox", { name: "Type" }).selectOption("Assumed");
  // Only the Type cell counts: an assumed row's description may itself mention what was measured.
  await expect(page.locator("tbody tr").filter({ has: page.getByText("Measured", { exact: true }) })).toHaveCount(0);
});

test("client portal: each client sees its released reports and brief, nothing internal and nothing of the other client's", async ({ page }) => {
  await openAs(page, "James Whitcombe", "/portal");
  await expect(page.getByRole("heading", { level: 1, name: "Calderwood Bank plc" })).toBeVisible();
  await expect(page.getByText(/· 2 released reports$/)).toBeVisible();
  const reports = page.locator("section").filter({ has: page.getByRole("heading", { name: "Released reports" }) });
  await expect(reports.locator("li")).toHaveCount(2);
  await expect(reports.locator("li").filter({ hasText: BRAMBLE })).toContainText("M-2026-05");
  await expect(reports.locator("li").filter({ hasText: NORTHMOOR })).toBeVisible();
  await expect(reports.getByRole("link", { name: "Workbook" })).toHaveCount(2);
  // Oxane's internal status-call brief never reaches the portal; the client sees only a summary
  // written to them, and only after the analyst releases it (not released in this run).
  await expect(page.getByRole("heading", { name: "Weekly status call" })).toHaveCount(0);
  await expect(page.getByText(/For this week's call with/)).toHaveCount(0);

  const body = await page.locator("main").innerText();
  // Unreleased packs (Kestrel, Ravenglass) and Thornbury's facilities are not shown...
  for (const hidden of ["Kestrel Credit Fund III", "Ravenglass Direct Lending Fund I", LARKSPUR, "Wharfedale Infrastructure Partners III", "Thornbury"]) {
    expect(reports.getByText(hidden)).toHaveCount(0);
  }
  expect(body).not.toMatch(/Larkspur|Wharfedale|Thornbury/);
  // ...nor internal references, provisional drafts, work-queue items or placeholders.
  expect(body).not.toMatch(/EXC-2026|WI-\d|PROVISIONAL|Provisional|\{\{|Expert judgement|Independent QC|cost_usd/);

  // The API refuses the internal cycle and the other client's workbook, whatever the client asks for.
  const refused = await page.evaluate(async () => {
    const cycle = await fetch("/api/monitoring/cycle");
    const larkspur = await fetch("/api/monitoring/workbook/larkspur.xlsx");
    const kestrel = await fetch("/api/monitoring/workbook/kestrel.xlsx");
    const bramble = await fetch("/api/monitoring/workbook/bramble.xlsx");
    return { cycle: cycle.status, larkspur: larkspur.status, kestrel: kestrel.status, bramble: bramble.status };
  });
  expect(refused).toEqual({ cycle: 403, larkspur: 404, kestrel: 404, bramble: 200 });
  await page.goto("/monitoring");
  await expect(page).toHaveURL(/\/portal$/);

  // Laura sees Thornbury's released Larkspur report only.
  await switchTo(page, "Laura Haskett");
  await page.goto("/portal");
  await expect(page.getByRole("heading", { level: 1, name: "Thornbury Bank N.A." })).toBeVisible();
  const hers = page.locator("section").filter({ has: page.getByRole("heading", { name: "Released reports" }) });
  await expect(hers.locator("li")).toHaveCount(1);
  await expect(hers.locator("li").filter({ hasText: LARKSPUR })).toBeVisible();
  expect(await page.locator("main").innerText()).not.toMatch(/Bramble|Northmoor|Kestrel|Ravenglass|Calderwood|EXC-2026/);
  const hersRefused = await page.evaluate(async () => (await fetch("/api/monitoring/workbook/bramble.xlsx")).status);
  expect(hersRefused).toBe(404);
});

test.afterAll(async ({ request, baseURL }) => {
  if (!isHosted(baseURL)) {
    await resetCycle(request);
  }
});
