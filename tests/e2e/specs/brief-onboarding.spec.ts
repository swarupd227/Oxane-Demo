/* The pitch brief's harder onboarding cases on case 0412, through the browser: the nested
 * definitions, the client's own model, the query tracker, the configuration workbook, the backbook
 * load and independent QC before the first report is released. Each test brings the case to its
 * stage through the session API (as screens.spec does) and then works the screen as the persona
 * whose job it is. */
import { expect as baseExpect, test, type Page } from "@playwright/test";
import { prepare, resetCase } from "./helpers";
import { isHosted, myWork, openAs, switchTo, waitForScreen } from "./personas";
import { readDownload, readWorkbook } from "./xlsx";

// The shared local stack can be slow while other suites run; wait on state, for longer.
const expect = baseExpect.configure({ timeout: 30_000 });
test.describe.configure({ timeout: 240_000 });

const usd = (value: number) => `US$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

async function screen(page: Page, path: string, heading: string, persona = "Hannah Cole") {
  await openAs(page, persona, path);
  await waitForScreen(page, heading);
}

// Each test resets case 0412 through the session API, so these run against a local stack only.
test.skip(({ baseURL }) => isHosted(baseURL), "Resets the shared onboarding session");

test.afterAll(async ({ request, baseURL }) => {
  if (!isHosted(baseURL)) {
    await resetCase(request);
  }
});

test("definitions: the borrowing base traced through 23 defined terms and reconciled to the cent", async ({ page, request }) => {
  await prepare(request, "loaded");
  await screen(page, "/definitions", "Nested definitions");
  await expect(page.getByText("Quotes verified 23/23")).toBeVisible();
  await expect(page.getByText("Borrowing base reconciles to engine")).toBeVisible();
  await expect(page.getByText("Circular inputs 0 · mutual references 6")).toBeVisible();
  await expect(page.getByText("Not in pack 4")).toBeVisible();

  // Two chains; a term shared between them is shown in full once, then "see above".
  const base = page.locator(".overflow-hidden").filter({ has: page.getByRole("heading", { level: 2, name: "Borrowing Base", exact: true }) });
  const ratio = page.locator(".overflow-hidden").filter({ has: page.getByRole("heading", { level: 2, name: "Delinquency Ratio", exact: true }) });
  // The chain cards, not the detail panel, which also has a "Borrowing Base" heading.
  await expect(base.getByText("36 terms", { exact: true })).toBeVisible();
  await expect(ratio.getByText("9 terms", { exact: true })).toBeVisible();
  const lines = page.locator(".overflow-hidden li button");
  const repeats = lines.filter({ hasText: "see above" });
  await expect(lines).toHaveCount(45);
  await expect(repeats).toHaveCount(22);
  const distinct = new Set<string>();
  for (const line of await lines.all()) {
    const text = await line.innerText();
    if (!text.includes("see above")) {
      distinct.add(text.split("\n")[0].trim());
    }
  }
  expect(distinct.size).toBe(23);
  await expect(base.locator("li").first()).toContainText("US$48,193,346.69");
  await expect(ratio.locator("li").first()).toContainText("0.79%");

  // The borrowing base worked out from its inputs; the arithmetic holds to the cent.
  const detail = page.locator("div.sticky.top-14");
  await expect(detail.getByRole("heading", { level: 2, name: "Borrowing Base" })).toBeVisible();
  await expect(detail.getByText("Quote found, page", { exact: false })).toBeVisible();
  await expect(detail.getByText("(Eligible Pool Balance - Excess Concentration Amount) x Advance Rate - Reserve Amount")).toBeVisible();
  await expect(detail.getByText("(US$59,592,950.65 - US$454,434.05) x 82.5% - US$595,929.51")).toBeVisible();
  await expect(detail.getByText("Reconciles to engine")).toBeVisible();
  const worked = Math.round((5959295065 - 45443405) * 0.825 - 59592951) / 100;
  expect(usd(worked)).toBe("US$48,193,346.69");
  await expect(detail.getByText("US$48,193,346.69")).toBeVisible();

  // The advance rate: amended from 85% to 82.5% by Amendment No. 1, both sources shown.
  await base.locator("li button").filter({ hasText: "Advance Rate" }).first().click();
  await expect(detail.getByRole("heading", { level: 2, name: "Advance Rate" })).toBeVisible();
  await expect(detail.getByText("Amendment No. 1, Section 2(a)", { exact: false })).toBeVisible();
  await expect(detail.getByText(/"85%" is deleted and replaced with "82.5%"/)).toBeVisible();
  await expect(detail.getByText("82.5%", { exact: true })).toBeVisible();
  // The chosen source takes the selected style the agreement had, whatever that style is.
  const agreement = detail.getByRole("button", { name: "Agreement", exact: true });
  const amendment = detail.getByRole("button", { name: "Amendment", exact: true });
  const chosen = (await agreement.getAttribute("class"))!;
  await expect(amendment).not.toHaveAttribute("class", chosen);
  await amendment.click();
  await expect(amendment).toHaveAttribute("class", chosen);
  await expect(agreement).not.toHaveAttribute("class", chosen);

  await expect(page.getByText(/Credit and Collection Policy \(the written policies/)).toBeVisible();
  await expect(page.getByText("Delinquency Ratio, April: 0.79% with repossessed receivables (per definition) · 0.80% without")).toBeVisible();
});

test("client model: each difference from the agreement and what it costs the borrowing base", async ({ page, request }) => {
  await prepare(request, "loaded");
  await screen(page, "/client-model", "Agreement against the client's model");
  await expect(page.getByText("Calderwood_BB_Model_Template_v3.2.xlsx · template v3.2 · against rule set v1")).toBeVisible();
  await expect(page.getByText("6 queries raised")).toBeVisible();

  const row = (label: string) => page.locator("tbody tr").filter({ hasText: label }).first();
  const effects: [string, number][] = [
    ["Advance rate", 1_478_462.91],
    ["Concentration basis", 157_256.8],
    ["Dealer grouping", 374_908.09],
  ];
  for (const [label, amount] of effects) {
    await expect(row(label).locator("td").nth(3)).toHaveText(`+${usd(amount)}`);
    await expect(row(label)).toContainText("Differs: query");
  }
  for (const label of ["Past-due exclusion", "Sub-600 FICO bucket"]) {
    await expect(row(label).locator("td").nth(3)).toHaveText("None this month");
  }
  await expect(row("Obligors with no score")).toContainText("Agreement silent: query");
  await expect(row("Reserve")).toContainText("Agrees");

  // The total is the sum of the rows, to the cent.
  const total = effects.reduce((sum, [, amount]) => sum + Math.round(amount * 100), 0) / 100;
  expect(usd(total)).toBe("US$2,010,627.80");
  await expect(page.getByText("US$2,010,627.80", { exact: true })).toBeVisible();
  await expect(page.getByText("Availability per agreement US$193,346.69")).toBeVisible();

  // The advance rate: stale in the model, and the borrowing base it would overstate.
  await row("Advance rate").click();
  const detail = page.locator("div.sticky.top-14");
  await expect(detail).toContainText("Agreement, Amendment No. 1, 2(a):");
  await expect(detail).toContainText("an April 2026 borrowing base US$1,478,462.91 higher than under the agreement");
  await row("Dealer grouping").click();
  await expect(detail).toContainText("US$374,908.09");
});

test("query tracker: send the drafted queries, the client answers one, the analyst records the rest; analyst time kept apart from client waiting", async ({ page, request }) => {
  await prepare(request, "loaded");
  await screen(page, "/queries", "Query tracker");
  await expect(page.getByText("Case 0412 · 9 queries · 1 with client · 6 drafted")).toBeVisible();
  const figure = (label: string) => page.locator("dl div").filter({ has: page.getByText(label, { exact: true }) }).locator("dd");
  await expect(page.getByText(/^83\.5 h business hours$/)).toBeVisible();
  await expect(figure("Analyst time")).toHaveText("9.5 h");
  await expect(figure("Client waiting time")).toHaveText("74.0 h");

  const card = (id: string) => page.locator(`#${id}`);
  await expect(card("Q-04")).toContainText("Drafted");
  await page.getByRole("button", { name: "Send 6 drafted" }).click();
  await expect(page.getByText("Case 0412 · 9 queries · 7 with client · 0 drafted")).toBeVisible();
  await expect(card("Q-04")).toContainText("With the client");
  await expect(card("Q-04")).toContainText(/Sent \d/);

  // The client contact finds the queries in the portal and answers Q-04 there.
  await openAs(page, "James Whitcombe", "/portal");
  const queries = page.locator("section").filter({ has: page.getByRole("heading", { name: "Queries from Oxane" }) });
  for (const id of ["Q-04", "Q-05", "Q-06", "Q-07", "Q-08", "Q-09"]) {
    await expect(queries.locator("li").filter({ hasText: id })).toContainText("Waiting on you");
  }
  await queries.locator("li").filter({ hasText: "Q-04" }).getByRole("button", { name: "Send our answer" }).click();
  await expect(queries.locator("li").filter({ hasText: "Q-04" })).toContainText("Answered");

  // Back with the analyst: the answer is in, and the other four are recorded from the tracker.
  const hannah = await myWork(page, "Hannah Cole");
  await expect(hannah.locator("li").filter({ hasText: "Client answered Q-04" })).toBeVisible();
  await screen(page, "/queries", "Query tracker");
  await expect(card("Q-04")).toContainText("Answered");
  await expect(card("Q-04")).toContainText(/Answer, \d/);
  await page.getByRole("button", { name: "Record 4 answers" }).click();
  for (const id of ["Q-05", "Q-06", "Q-07", "Q-08"]) {
    await expect(card(id)).toContainText("Answered");
  }
  await expect(card("Q-09")).toContainText("With the client");
  await expect(page.getByText("Case 0412 · 9 queries · 2 with client · 0 drafted")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Record \d+ answers$/ })).toHaveCount(0);

  // The split: analyst plus client waiting makes the elapsed time. Client waiting is the union of
  // the waits, and Q-01 (blocking, sent 5 May) is still open, so sending more queries in
  // parallel adds waiting to each query but not to the case.
  const tracker = (await (await request.get("/api/casework")).json()).tracker;
  expect(tracker.elapsed_hours).toBe(83.5);
  expect(tracker.client_waiting_hours).toBe(74);
  const waited = tracker.queries.filter((q: { sent: string | null; earlier: boolean }) => q.sent && !q.earlier);
  expect(waited.every((q: { waiting_hours: number }) => q.waiting_hours > 0)).toBe(true);
  expect(Math.round((tracker.analyst_hours + tracker.client_waiting_hours) * 100) / 100).toBe(83.5);
  await expect(figure("Analyst time")).toHaveText(`${tracker.analyst_hours.toFixed(1)} h`);
  await expect(figure("Client waiting time")).toHaveText(`${tracker.client_waiting_hours.toFixed(1)} h`);
  const handling = tracker.queries.reduce((sum: number, q: { analyst_hours: number }) => sum + q.analyst_hours, 0);
  await expect(figure("Analyst handling, sum of queries")).toHaveText(`${handling.toFixed(1)} h`);
  await expect(card("Q-05")).toContainText(/Configuration: /);
});

test("configuration: 24 thresholds, each matching its source, and the workbook export", async ({ page, request }) => {
  await prepare(request, "terms");
  await screen(page, "/configuration", "Configuration workbook");
  await expect(page.getByText(/^Case 0412 · 24 thresholds · 38 fields · 13 report lines · rule set [0-9a-f]{12}$/)).toBeVisible();
  await expect(page.getByText("Thresholds matching source 24/24")).toBeVisible();
  await expect(page.getByText("Approved: Pending")).toBeVisible();
  await expect(page.getByText("QC: Open variances")).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(24);
  await expect(page.locator("tbody tr").filter({ hasText: "Matches source" })).toHaveCount(24);

  await page.getByRole("tab", { name: "Field map" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(38);
  await page.getByRole("tab", { name: "Report lines" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(13);
  await page.getByRole("tab", { name: "Client conventions" }).click();
  await expect(page.locator("tbody tr").filter({ hasText: "Agreement applied; query open" }).first()).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export .xlsx" }).click();
  const saved = await download;
  expect(saved.suggestedFilename()).toBe("case-0412-configuration-provisional.xlsx");
  const book = readWorkbook(await readDownload(saved));
  expect([...book.keys()]).toEqual(["Status", "Field map", "Rules and thresholds", "Report lines", "Client conventions"]);
  expect(book.get("Status")!.cells.get("A2")!.value).toMatch(/^PROVISIONAL/);
  const rules = book.get("Rules and thresholds")!.rows.slice(1).filter((r) => r.length);
  expect(rules).toHaveLength(24);
  expect(rules.every((r) => r.find((c) => c.ref.startsWith("F"))?.value === "Yes")).toBe(true);
  expect(book.get("Field map")!.rows.slice(1).filter((r) => r.length)).toHaveLength(38);
  expect(book.get("Report lines")!.rows.slice(1).filter((r) => r.length)).toHaveLength(13);
});

test("backbook: four deals on Bramble's stored mapping; accepting one loads it", async ({ page, request }) => {
  await prepare(request, "loaded");
  await screen(page, "/backbook", "Backbook load");
  await expect(page.getByText(/4 deals · 780 loans · 4 exceptions · 1\/4 loaded$/)).toBeVisible();
  const deal = (name: string) => page.locator(".rounded-xl").filter({ has: page.getByRole("heading", { level: 2, name }) });
  await expect(deal("Ashdown Auto Funding II LLC")).toContainText("Loaded");
  const kingsbury = deal("Kingsbury Motor Credit Warehouse LLC");
  await expect(kingsbury).toContainText("1 exception");
  await expect(kingsbury.getByRole("button", { name: "Accept and load" })).toBeEnabled();
  await kingsbury.getByRole("button", { name: "Accept and load" }).click();
  await expect(kingsbury).toContainText("Loaded");
  await expect(kingsbury.getByRole("button", { name: "Accept and load" })).toHaveCount(0);
  await expect(page.getByText(/4 deals · 780 loans · 4 exceptions · 2\/4 loaded$/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/2\/4 loaded$/)).toBeVisible();
});

test("QC and release: 13 lines, two genuine variances hold the report until QC resolves them, then the reviewer releases it", async ({ page, request }) => {
  await prepare(request, "approved");
  await screen(page, "/qc", "Independent QC");
  await expect(page.getByText(/· 13 lines · 5 agree · 6 presentation · 2 genuine$/)).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(13);
  await expect(page.getByText("Genuine variances open: 2")).toBeVisible();
  await expect(page.getByRole("button", { name: "Release report" })).toBeDisabled();
  const variance = (line: string) => page.locator(".rounded-xl").filter({ has: page.getByRole("heading", { level: 3, name: line }) });
  await expect(variance("Aggregate outstanding balance of pool receivables")).toContainText("Difference US$221,624.40");
  await expect(variance("Sub-600 FICO bucket balance")).toContainText("Difference -US$563,838.32");

  // The reviewer cannot release while the variances are open.
  await screen(page, "/qc", "Independent QC", "Marcus Hale");
  await expect(page.getByRole("button", { name: "Release report" })).toBeDisabled();

  // The QC analyst has it in My work and records a resolution for each.
  const tom = await myWork(page, "Tom Fairley");
  await expect(tom.locator("li").filter({ hasText: "Independent QC: 2 genuine variances, case 0412" })).toBeVisible();
  await screen(page, "/qc", "Independent QC", "Tom Fairley");
  const first = variance("Aggregate outstanding balance of pool receivables");
  await first.getByRole("combobox").selectOption("QC calculation corrected");
  await first.getByLabel("Reason for Aggregate outstanding balance of pool receivables").fill("QC workbook omitted the 7 repossessed receivables still on the tape.");
  await first.getByRole("button", { name: "Record" }).click();
  await expect(first).toContainText("QC calculation corrected · Tom Fairley");
  await expect(page.getByText("Genuine variances open: 1")).toBeVisible();
  const second = variance("Sub-600 FICO bucket balance");
  await second.getByRole("combobox").selectOption("Explained, no effect on the borrowing base");
  await second.getByLabel("Reason for Sub-600 FICO bucket balance").fill("QC banded 600 into sub-600; the agreement's band is below 600.");
  await second.getByRole("button", { name: "Record" }).click();
  await expect(second).toContainText("Explained, no effect on the borrowing base · Tom Fairley");
  await expect(page.getByText("Genuine variances open: 0")).toBeVisible();
  const tomAfter = await myWork(page, "Tom Fairley");
  await expect(tomAfter.locator("li").filter({ hasText: "Independent QC: 2 genuine variances, case 0412" })).toHaveCount(0);

  // The release waits on the reviewer, who releases the first report.
  const marcus = await myWork(page, "Marcus Hale");
  await expect(marcus.locator("li").filter({ hasText: "Release first report, case 0412" })).toBeVisible();
  await screen(page, "/qc", "Independent QC", "Marcus Hale");
  await page.getByRole("button", { name: "Release report" }).click();
  await expect(page.getByText(/^Released \d.* by Marcus Hale$/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Release report" })).toBeDisabled();

  // The configuration is final, and the live facility is handed to monitoring.
  await screen(page, "/configuration", "Configuration workbook", "Marcus Hale");
  await expect(page.getByText("Final", { exact: true })).toBeVisible();
  await expect(page.getByText("QC: Passed")).toBeVisible();
  const priya = await myWork(page, "Priya Raman");
  await expect(priya.locator("li").filter({ hasText: "Bramble is live: first monthly cycle is yours" })).toBeVisible();
  await switchTo(page, "Hannah Cole");
});
