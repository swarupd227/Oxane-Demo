/* The agents console: the eleven model agents and five code engines by name, an agent's definition,
 * the dependency graph, the pain-point coverage matrix and the run log, where Thornbury's calls
 * are refused because it does not permit AI. Read-only: nothing here changes the session. */
import { expect as baseExpect, test, type Page } from "@playwright/test";
import { kpi, openAs, waitForScreen } from "./personas";

// The shared local stack can be slow while other suites run; wait on state, for longer.
const expect = baseExpect.configure({ timeout: 30_000 });
test.describe.configure({ timeout: 240_000 });

const MODEL_AGENTS = [
  "Intake and classification",
  "Extraction",
  "Definitions",
  "Client-model comparison",
  "Rule drafting",
  "Mapping",
  "Change explanation",
  "Triage",
  "Drafting (packs, queries)",
  "Alerts (self-service rule drafting)",
  "Status-call brief",
];
const CODE_ENGINES = ["Quote check", "Validation", "Reconciliation", "Calculation and covenants", "QC comparison"];

async function console_(page: Page, path = "/monitoring/agents") {
  await openAs(page, "Priya Raman", path);
  await waitForScreen(page, "Agents");
}

function names(page: Page) {
  return page.locator("tbody tr td:first-child");
}

test("the list shows 11 model agents and 5 code engines by name", async ({ page }) => {
  await console_(page);
  await expect(kpi(page, "Model agents")).toHaveText("11");
  await expect(kpi(page, "Code engines")).toHaveText("5");
  await expect(page.getByText("16 records")).toBeVisible();
  expect((await names(page).allInnerTexts()).sort()).toEqual([...MODEL_AGENTS, ...CODE_ENGINES].sort());

  const type = page.getByRole("combobox", { name: "Type" });
  await type.selectOption("model");
  await expect(page.getByText("11 records")).toBeVisible();
  expect((await names(page).allInnerTexts()).sort()).toEqual([...MODEL_AGENTS].sort());
  for (const row of await page.locator("tbody tr").all()) {
    await expect(row.getByText("Model", { exact: true })).toBeVisible();
  }
  await type.selectOption("code");
  await expect(page.getByText("5 records")).toBeVisible();
  expect((await names(page).allInnerTexts()).sort()).toEqual([...CODE_ENGINES].sort());
  for (const row of await page.locator("tbody tr").all()) {
    await expect(row.getByText("No model", { exact: true })).toBeVisible();
    await expect(row.getByText("Always on")).toBeVisible();
  }

  // Ordered by pipeline stage, from receiving documents to communicating with the client.
  await type.selectOption("all");
  const stages = await page.locator("tbody tr td:nth-child(3)").allInnerTexts();
  const order = stages.map((s) => Number(s.split(".")[0]));
  expect(order).toEqual([...order].sort((a, b) => a - b));
  expect(stages[0]).toBe("1. Receive");
  expect(stages.at(-1)).toBe("7. Communicate");

  // The same console is reachable from the onboarding workbench.
  await openAs(page, "Hannah Cole", "/agents");
  await expect(page.getByRole("heading", { level: 1, name: "Agents" })).toBeVisible();
  await expect(kpi(page, "Model agents")).toHaveText("11");
});

test("an agent's page: purpose, tasks, trigger, inputs, outputs, constraints and dependencies", async ({ page }) => {
  await console_(page);
  await page.locator("tbody tr").filter({ has: page.getByText("Triage", { exact: true }) }).click();
  await expect(page).toHaveURL(/\/monitoring\/agents\/triage$/);
  await expect(page.getByRole("heading", { level: 2, name: "Triage" })).toBeVisible();
  await expect(page.getByText("5. Resolve").first()).toBeVisible();

  const definition = page.locator("section").filter({ has: page.getByRole("heading", { name: "Definition" }) });
  const field = (label: string) => definition.locator("dl > div").filter({ has: page.locator("dt", { hasText: new RegExp(`^${label}$`) }) }).locator("dd");
  await expect(field("Purpose")).toContainText("Suggests an outcome for each finding (confirmed, query, expert, logged) with a reason");
  await expect(field("Tasks").locator("li")).toHaveCount(3);
  await expect(field("Tasks")).toContainText("Route judgement items to an expert");
  await expect(field("Trigger")).toContainText("Findings raised");
  await expect(field("Trigger").getByLabel("Event")).toBeVisible();
  await expect(field("Inputs").locator("li")).toHaveText(["Findings with evidence", "Terms version"]);
  await expect(field("Outputs")).toHaveText("Suggested outcome and reason per finding");
  await expect(field("Use case steps")).toContainText("UC2 · 4. Review and resolve");
  await expect(field("Pain points")).toContainText("Confirmed issues kept apart from expert judgement");

  const constraints = page.locator("section").filter({ has: page.getByRole("heading", { name: "Constraints" }) });
  await expect(constraints.locator("li")).toHaveCount(5);
  await expect(constraints).toContainText("Disabled for clients that don't permit AI; the guarded gateway refuses the call and the code path runs");
  await expect(constraints).toContainText("Output is a suggestion; a person decides and a change needs a reason");

  const deps = page.locator("section").filter({ has: page.getByRole("heading", { name: "Dependencies" }) });
  await expect(deps.getByRole("link")).toHaveText(["Validation", "Reconciliation", "Calculation and covenants", "Change explanation", "Drafting (packs, queries)", "Status-call brief"]);
  await expect(deps).toContainText("Rule failures");

  const model = page.locator("section").filter({ has: page.getByRole("heading", { name: "Model", exact: true }) });
  await expect(model.locator("code").filter({ hasText: "suggest_triage" })).toBeVisible();
  await expect(model).toContainText("rec-22f6e9b5");
  await expect(model).toContainText("app/monitoring/steps.py");

  // A code engine has no model.
  await deps.getByRole("link", { name: "Validation" }).click();
  await expect(page).toHaveURL(/\/monitoring\/agents\/validation$/);
  await expect(page.getByRole("heading", { level: 2, name: "Validation" })).toBeVisible();
  const implementation = page.locator("section").filter({ has: page.getByRole("heading", { name: "Implementation" }) });
  await expect(implementation).toContainText("None. Deterministic code.");
  await expect(page.getByRole("heading", { name: "Recent runs" })).toHaveCount(0);
});

test("the dependency graph shows every agent and opens the one clicked", async ({ page }) => {
  await console_(page, "/monitoring/agents/graph");
  await expect(page.getByText("16 agents · 27 hand-offs")).toBeVisible();
  const graph = page.getByRole("group", { name: "Agent dependencies by pipeline stage" });
  await expect(graph.getByRole("link")).toHaveCount(16);
  for (const name of MODEL_AGENTS) {
    await expect(graph.getByRole("link", { name: `${name}, model agent` })).toBeVisible();
  }
  for (const name of CODE_ENGINES) {
    await expect(graph.getByRole("link", { name: `${name}, code engine, no model` })).toBeVisible();
  }
  await graph.getByRole("link", { name: "Alerts (self-service rule drafting), model agent" }).click();
  await expect(page).toHaveURL(/\/monitoring\/agents\/alerts$/);
  await expect(page.getByRole("heading", { level: 2, name: "Alerts (self-service rule drafting)" })).toBeVisible();
  // Its own page highlights it in the pipeline.
  const position = page.locator("section").filter({ has: page.getByRole("heading", { name: "Position in the pipeline" }) });
  await expect(position.getByRole("link", { name: "Alerts (self-service rule drafting), model agent" })).toBeVisible();

  // Keyboard: Enter on a focused node opens it too.
  await page.goto("/monitoring/agents/graph");
  const node = page.getByRole("link", { name: "Quote check, code engine, no model" });
  await node.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/monitoring\/agents\/quote_check$/);
});

test("the coverage matrix ties each agent to the brief's pain points", async ({ page }) => {
  await console_(page, "/monitoring/agents/coverage");
  const pains = page.locator("section").filter({ has: page.getByRole("heading", { name: "Pain points" }) });
  await expect(pains).toContainText("14 from the pitch brief and RFP review");
  await expect(pains.locator("tbody tr")).toHaveCount(17);
  await expect(pains.getByLabel("Alerts (self-service rule drafting): Client self-service alerts")).toBeVisible();
  await expect(pains.getByLabel("Status-call brief: Weekly client-call summary")).toBeVisible();
  await expect(pains.getByLabel("Triage: Confirmed issues kept apart from expert judgement")).toBeVisible();
  await expect(pains.getByLabel("Quote check: Client self-service alerts")).toHaveCount(0);
  // The totals row: agents per pain point, e.g. five on calculations and one on self-service alerts.
  const totals = pains.locator("tbody tr").last();
  await expect(totals).toContainText("Agents per pain point");
  const heads = await pains.locator("thead th").allInnerTexts();
  const counts = await totals.locator("td").allInnerTexts();
  const per = Object.fromEntries(heads.slice(1).map((h, i) => [h.trim(), counts[i]]));
  expect(per["Calculations"]).toBe("5");
  expect(per["Self-service alerts"]).toBe("1");
  expect(per["No-AI clients"]).toBe("3");
  await pains.getByRole("link", { name: "Status-call brief" }).click();
  await expect(page).toHaveURL(/\/monitoring\/agents\/status_brief$/);
});

test("the run log filters by agent, client and outcome; Thornbury's calls are refused", async ({ page }) => {
  await console_(page, "/monitoring/agents/runs");
  const thornbury = page.locator("div").filter({ has: page.getByText("Thornbury Bank N.A.", { exact: true }) }).filter({ hasText: "Existing process — outside AI scope" }).last();
  await expect(thornbury).toBeVisible();
  const stat = (card: typeof thornbury, label: string) => card.locator("span.shrink-0").filter({ has: page.getByText(label, { exact: true }) }).locator("span").last();
  await expect(stat(thornbury, "Refused")).toHaveText("6");
  await expect(stat(thornbury, "Cost")).toHaveText("US$0");

  await page.getByRole("main").getByRole("combobox", { name: "Client" }).selectOption({ label: "Thornbury Bank N.A." });
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(6);
  for (const row of await rows.all()) {
    await expect(row).toContainText("Refused: AI not permitted");
    await expect(row).toContainText("0 / 0");
    await expect(row).toContainText("US$0");
  }
  await page.getByRole("combobox", { name: "Outcome" }).selectOption("accepted");
  await expect(page.getByText("No records match.")).toBeVisible();

  await page.getByRole("main").getByRole("combobox", { name: "Client" }).selectOption({ label: "Calderwood Bank plc" });
  await expect(rows.first()).toContainText("Accepted");
  for (const row of await rows.all()) {
    await expect(row).toContainText("Accepted");
    await expect(row).toContainText("Calderwood");
  }
  await page.getByRole("combobox", { name: "Outcome" }).selectOption("refused");
  await expect(page.getByText("No records match.")).toBeVisible();

  await page.getByRole("combobox", { name: "Outcome" }).selectOption("all");
  await page.getByRole("combobox", { name: "Agent" }).selectOption({ label: "Triage" });
  await expect(rows.first()).toBeVisible();
  for (const row of await rows.all()) {
    await expect(row.locator("td").nth(1)).toHaveText("Triage");
  }
  await rows.first().click();
  await expect(page).toHaveURL(/\/monitoring\/agents\/triage$/);
});
