/* Context checks: the shell shows only what belongs to the acting persona and the page in view.
 * A case's or facility's own sections appear only inside that case; list pages, My work, clients
 * and settings belong to no case. Each persona sees its role's navigation and no more, client
 * users never see internal pages (and the API refuses them), switching persona updates the menu
 * and My work in place, and presenter mode starts off.
 *
 * Reads the scripted case's number and names from the API rather than assuming them. Changes no
 * shared state except one throwaway client and case, archived at the end, so it also runs against
 * the hosted app (project "azure"). */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

interface Persona {
  id: string;
  name: string;
  role: string;
  role_label: string;
  client: string | null;
}

/** The global navigation each role should get on My work (the workspace shell). */
const WORKSPACE_NAV: Record<string, string[]> = {
  onboarding_analyst: ["My work", "Onboarding cases", "Clients"],
  expert: ["My work", "Onboarding cases", "Facilities"],
  qc: ["My work", "Onboarding cases", "Facilities"],
  reviewer: ["My work", "Onboarding cases", "Facilities", "Clients"],
  monitoring_analyst: ["My work", "Facilities"],
  head: ["My work", "Facilities", "Clients"],
  admin: ["My work", "Onboarding cases", "Facilities", "Clients", "Settings"],
};
const ONBOARDING_ROLES = ["onboarding_analyst", "expert", "qc", "reviewer", "admin"];
const MONITORING_ROLES = ["monitoring_analyst", "head", "reviewer", "expert", "qc", "admin"];

const as = (id: string) => ({ headers: { "X-Acting-User": id } });

async function personas(request: APIRequestContext): Promise<Persona[]> {
  const body = await (await request.get("/api/personas")).json();
  return body.personas;
}

async function scriptedCase(request: APIRequestContext) {
  const view = await (await request.get("/api/case", as("hannah"))).json();
  return {
    number: view.number as string,
    borrower: view.deal.borrower.name as string,
    short: view.deal.borrower.short_name as string,
    lender: view.deal.lender.name as string,
  };
}

const personaButton = (page: Page) => page.getByRole("button", { name: /^Acting as/ });

async function switchTo(page: Page, person: Persona) {
  const item = page.getByRole("menuitemradio", { name: new RegExp(`^${person.name}`) });
  // Open the menu only once the people have loaded. A redirect still settling can close it as it
  // opens, so close and reopen it until the item shows. (While it is open the trigger is hidden
  // from the accessibility tree, so it must be closed with Escape, not clicked again.)
  await expect(personaButton(page)).toHaveAccessibleName(/^Acting as (?!Loading)/, { timeout: 30_000 });
  await expect(async () => {
    if (await page.getByRole("menu").isVisible()) {
      await page.keyboard.press("Escape");
    }
    await personaButton(page).click({ timeout: 5_000 });
    await expect(item).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 45_000 });
  await item.click();
  await expect(page.getByRole("button", { name: new RegExp(`^Acting as ${person.name}`) })).toBeVisible();
}

/** The link names in a navigation landmark, without their counts. */
async function navItems(page: Page, label: string): Promise<string[]> {
  const nav = page.getByRole("navigation", { name: label, exact: true });
  const texts = await nav.getByRole("link").allInnerTexts();
  return texts.map((t) => t.replace(/\s*\d+$/, "").trim());
}

async function crumbs(page: Page): Promise<string[]> {
  const nav = page.getByRole("navigation", { name: "Breadcrumb" });
  const parts = await nav.locator(":scope > a, :scope > span:not([aria-hidden])").allInnerTexts();
  return parts.map((t) => t.trim()).filter(Boolean);
}

/** No case or facility of its own: no case sections, no case heading, no scripted names. */
async function expectNoCaseContext(page: Page, names: string[]) {
  await expect(page.getByRole("navigation", { name: "Case sections" })).toHaveCount(0);
  // The onboarding header's case switcher names no case outside one.
  const switcher = page.getByRole("button", { name: "Switch case" });
  if (await switcher.count()) {
    await expect(switcher).toHaveText(/Choose a case/);
  }
  const side = page.getByRole("complementary").first();
  if (await side.count()) {
    const text = await side.innerText();
    expect(text).not.toMatch(/\bCase \d{3,}/);
    for (const name of names) {
      expect(text, `sidebar should not name ${name}`).not.toContain(name);
    }
  }
}

for (const role of Object.keys(WORKSPACE_NAV)) {
  test(`the ${role} persona lands on My work and sees only its role's navigation`, async ({ page, request }) => {
    test.setTimeout(120_000);
    const person = (await personas(request)).find((p) => p.role === role)!;
    expect(person, `a persona with role ${role}`).toBeDefined();
    // Start away from My work, on a page every internal role may open.
    await page.goto("/clients");
    await switchTo(page, person);
    await expect(page).toHaveURL(/\/work$/);
    await expect(page.getByRole("heading", { level: 1, name: "My work" })).toBeVisible();
    await expect(page.getByText(`${person.name} · ${person.role_label}`)).toBeVisible();
    await expect.poll(() => navItems(page, "Workspace")).toEqual(WORKSPACE_NAV[role]);
    await expect.poll(() => page.getByRole("navigation", { name: "Workbench" }).getByRole("link").allInnerTexts()).toEqual([
      ...(ONBOARDING_ROLES.includes(role) ? ["Onboarding"] : []),
      ...(MONITORING_ROLES.includes(role) ? ["Monitoring"] : []),
    ]);
    // The persona menu offers Settings to the administrator only.
    await personaButton(page).click();
    await expect(page.getByRole("menu")).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Settings" })).toHaveCount(role === "admin" ? 1 : 0);
    await page.keyboard.press("Escape");

    await page.goto("/cases");
    if (ONBOARDING_ROLES.includes(role)) {
      // The onboarding shell's global items follow the same role rules.
      const expected = WORKSPACE_NAV[role].filter((item) => ["My work", "Clients", "Onboarding cases"].includes(item));
      await expect.poll(async () => (await navItems(page, "Onboarding")).sort()).toEqual(expected.sort());
      await expect.poll(() => navItems(page, "Platform")).toEqual(role === "admin" ? ["Agents", "Settings"] : ["Agents"]);
    } else {
      await expect(page).toHaveURL(/\/work$/);
    }
  });
}

test("list pages carry no case or facility section", async ({ page, request }) => {
  test.setTimeout(120_000);
  const scripted = await scriptedCase(request);
  const cycle = await (await request.get("/api/monitoring/cycle", as("priya"))).json();
  const names = [scripted.borrower, scripted.short, ...cycle.facilities.map((f: { name: string }) => f.name)];
  const people = await personas(request);
  const admin = people.find((p) => p.role === "admin")!;
  await page.goto("/work");
  await switchTo(page, admin);
  const pages: { path: string; heading: RegExp | string; crumbs?: string[] }[] = [
    { path: "/work", heading: "My work" },
    { path: "/cases", heading: "Onboarding cases", crumbs: ["Onboarding", "Cases"] },
    { path: "/clients", heading: "Clients" },
    { path: "/facilities", heading: /Facilities/ },
    { path: "/agents", heading: /Agents/, crumbs: ["Agents"] },
    { path: "/settings/ai-provider", heading: /AI provider/ },
    { path: "/monitoring", heading: /Portfolio/, crumbs: ["Monitoring"] },
    { path: "/monitoring/submissions", heading: /Submissions/, crumbs: ["Monitoring", "Submissions"] },
    { path: "/monitoring/agents", heading: /Agents/ },
  ];
  for (const item of pages) {
    await test.step(item.path, async () => {
      await page.goto(item.path);
      await expect(page.getByRole("heading", { level: 1 }).first()).toContainText(item.heading);
      await expectNoCaseContext(page, names);
      if (item.crumbs) {
        await expect.poll(() => crumbs(page)).toEqual(item.crumbs);
      }
    });
  }
});

test("inside the scripted case the sidebar names that case, and the breadcrumbs follow the page", async ({ page, request }) => {
  const scripted = await scriptedCase(request);
  expect(scripted.number).toBe("0412");
  await page.goto("/work");
  await expect(personaButton(page)).toHaveAccessibleName(/^Acting as Hannah Cole/);
  const side = page.getByRole("complementary").first();

  for (const path of ["/overview", "/terms", "/definitions", `/cases/${scripted.number}`]) {
    await test.step(path, async () => {
      await page.goto(path);
      await expect(page.getByRole("navigation", { name: "Case sections" })).toBeVisible();
      await expect(side.getByText(`Case ${scripted.number}`, { exact: true })).toBeVisible();
      await expect(side.getByText(scripted.borrower, { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Switch case" })).toContainText(scripted.number);
    });
  }
  await page.goto("/overview");
  await expect.poll(() => crumbs(page)).toEqual(["Onboarding", scripted.lender, `${scripted.number} ${scripted.short}`]);
  await page.goto("/terms");
  await expect.poll(() => crumbs(page)).toEqual(["Onboarding", scripted.lender, `${scripted.number} ${scripted.short}`, "Terms & Definitions"]);
  await page.goto("/definitions");
  await expect.poll(() => crumbs(page)).toEqual(["Onboarding", scripted.lender, `${scripted.number} ${scripted.short}`, "Terms & Definitions", "Definitions"]);
  await page.goto(`/cases/${scripted.number}`);
  const pipeline = await (await request.get("/api/cases", as("hannah"))).json();
  const item = pipeline.cases.find((c: { number: string }) => c.number === scripted.number);
  await expect.poll(() => crumbs(page)).toEqual(["Onboarding", item.client, `${item.number} ${item.facility}`]);

  // Leaving the case for a list drops its sections again.
  await page.getByRole("navigation", { name: "Onboarding" }).getByRole("link", { name: /^Onboarding cases/ }).click();
  await expect(page).toHaveURL(/\/cases$/);
  await expectNoCaseContext(page, [scripted.borrower]);
});

test("the app root and the Onboarding tab open no case", async ({ page, request }) => {
  test.setTimeout(150_000);
  const scripted = await scriptedCase(request);
  const people = await personas(request);
  const homes: [string, RegExp][] = [["hannah", /\/work$/], ["priya", /\/work$/], ["alex", /\/work$/], ["james", /\/portal$/]];
  await page.goto("/work");
  for (const [id, home] of homes) {
    await test.step(id, async () => {
      await page.evaluate((who) => window.localStorage.setItem("oxane.persona", who), id);
      await page.goto("/");
      await expect(page).toHaveURL(home, { timeout: 30_000 });
      const person = people.find((p) => p.id === id)!;
      await expect(page.getByRole("button", { name: new RegExp(`^Acting as ${person.name}`) })).toBeVisible();
      await expectNoCaseContext(page, [scripted.borrower, scripted.short]);
    });
  }
  // The Onboarding tab of the workbench switch opens the case list, not a case.
  await page.evaluate(() => window.localStorage.setItem("oxane.persona", "alex"));
  await page.goto("/monitoring");
  await page.getByRole("navigation", { name: "Workbench" }).getByRole("link", { name: "Onboarding" }).click();
  await expect(page).toHaveURL(/\/cases$/);
  await expect(page.getByRole("heading", { level: 1, name: "Onboarding cases" })).toBeVisible();
  await expectNoCaseContext(page, [scripted.borrower, scripted.short]);
  // The header switcher names a case only inside one.
  await expect(page.getByRole("button", { name: "Switch case" })).toHaveText(/Choose a case/);
  await page.goto("/overview");
  await expect(page.getByRole("button", { name: "Switch case" })).toContainText(scripted.number);
});

test("a new-deal case page shows that case, not the scripted one", async ({ page, request }) => {
  const scripted = await scriptedCase(request);
  const run = Math.random().toString(36).slice(2, 7);
  const clientRes = await request.post("/api/deals/clients", {
    ...as("alex"),
    data: { name: `Context Check Client ${run}`, contact_name: `Context Contact ${run}`, ai_permitted: false, approval_levels: 2 },
  });
  expect(clientRes.status(), await clientRes.text()).toBe(200);
  const client = await clientRes.json();
  let caseId: number | undefined;
  try {
    const caseRes = await request.post("/api/deals/cases", {
      ...as("hannah"),
      data: { client_id: client.id, facility_name: `Context Check Facility ${run}`, deal_type: "SME loans", commitment: 1_000_000 },
    });
    expect(caseRes.status(), await caseRes.text()).toBe(200);
    const view = await caseRes.json();
    caseId = view.id;

    await page.goto(`/deals/cases/${caseId}`);
    await expect(personaButton(page)).toHaveAccessibleName(/^Acting as Hannah Cole/);
    await expect(page.getByRole("heading", { level: 1, name: view.facility_name })).toBeVisible();
    await expect(page.getByText(view.ref, { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: client.name }).first()).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Sections" })).toBeVisible();
    // The scripted case's sections and names stay out of it.
    await expectNoCaseContext(page, [scripted.borrower, scripted.short]);
    await expect(page.locator("main")).not.toContainText(`Case ${scripted.number}`);
  } finally {
    if (caseId !== undefined) {
      await request.post(`/api/deals/cases/${caseId}/archive`, { ...as("hannah"), data: { note: "Context check case" } });
    }
    await request.post(`/api/deals/clients/${client.id}/archive`, { ...as("alex"), data: { note: "Context check client" } });
  }
});

test("client users never see internal navigation, and the API refuses them", async ({ page, request }) => {
  test.setTimeout(240_000);
  const people = await personas(request);
  const clients = people.filter((p) => p.role === "client" && !p.id.startsWith("client-"));
  expect(clients.length).toBeGreaterThan(1);
  await page.goto("/work");
  for (const person of clients) {
    await test.step(person.name, async () => {
      await switchTo(page, person);
      await expect(page).toHaveURL(/\/portal$/);
      await expect(page.getByRole("navigation", { name: "Workspace" })).toHaveCount(0);
      await expect(page.getByRole("navigation", { name: "Workbench" })).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Agents" })).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Settings" })).toHaveCount(0);
      await personaButton(page).click();
      await expect(page.getByRole("menu")).toBeVisible();
      await expect(page.getByRole("menuitem", { name: "Settings" })).toHaveCount(0);
      await expect(page.getByRole("menuitem", { name: "Access code" })).toHaveCount(0);
      await page.keyboard.press("Escape");
      // Other clients' names never reach this client's portal.
      const others = clients.filter((p) => p.client !== person.client).map((p) => p.client!);
      const body = await page.locator("main").innerText();
      for (const other of others) {
        expect(body.toLowerCase(), `${person.name} should not see ${other}`).not.toContain(other.toLowerCase());
      }
      for (const path of ["/agents", "/settings/ai-provider", "/clients", "/cases", "/monitoring", "/work"]) {
        await page.goto(path);
        // Redirected once the acting persona has loaded.
        await expect(page, `${person.name} at ${path}`).toHaveURL(/\/portal$/, { timeout: 30_000 });
      }
      for (const path of ["/api/agents", "/api/admin/ai-provider", "/api/deals/clients", "/api/deals/cases", "/api/cases", "/api/monitoring/cycle", "/api/case"]) {
        const res = await request.get(path, as(person.id));
        expect(res.status(), `${person.name} GET ${path}`).toBe(403);
      }
    });
  }
});

test("switching persona updates the menu and My work in place", async ({ page, request }) => {
  const people = await personas(request);
  const from = people.find((p) => p.role === "onboarding_analyst")!;
  const to = people.find((p) => p.role === "monitoring_analyst")!;
  await page.goto("/work");
  await switchTo(page, from);
  await expect(page.getByText(`${from.name} · ${from.role_label}`)).toBeVisible();
  // Marks this page load: a full reload would drop it.
  await page.evaluate(() => ((window as unknown as { contextMark: number }).contextMark = 1));
  await switchTo(page, to);
  await expect(page.getByText(`${to.name} · ${to.role_label}`)).toBeVisible();
  await expect(page.getByText(`${from.name} · ${from.role_label}`)).toHaveCount(0);
  await expect.poll(() => navItems(page, "Workspace")).toEqual(WORKSPACE_NAV[to.role]);
  expect(await page.evaluate(() => (window as unknown as { contextMark?: number }).contextMark)).toBe(1);
  // The checked item in the menu moved too.
  await personaButton(page).click();
  await expect(page.getByRole("menuitemradio", { name: new RegExp(`^${to.name}`) })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("menuitemradio", { name: new RegExp(`^${from.name}`) })).toHaveAttribute("aria-checked", "false");
  await page.keyboard.press("Escape");
  // And it survives a reload.
  await page.reload();
  await expect(page.getByRole("button", { name: new RegExp(`^Acting as ${to.name}`) })).toBeVisible();
});

test("presenter mode is off by default", async ({ page }) => {
  for (const path of ["/cases", "/work", "/monitoring"]) {
    await page.goto(path);
    const toggle = page.getByRole("button", { name: "Presenter mode" });
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await expect(page.getByRole("list", { name: "Walkthrough" })).toHaveCount(0);
  }
});

test("a fresh browser keeps the persona it started as when it moves to another area", async ({ page }) => {
  // Nobody chosen: opening monitoring starts as Priya, the monitoring analyst.
  await page.goto("/monitoring");
  await expect(page.getByRole("button", { name: /^Acting as Priya Raman,/ })).toBeVisible({ timeout: 90_000 });
  // Moving to My work, the cases list or back must not fall back to the onboarding default.
  await page.goto("/work");
  await expect(page.getByRole("button", { name: /^Acting as Priya Raman,/ })).toBeVisible({ timeout: 90_000 });
  await page.goto("/monitoring");
  await expect(page.getByRole("button", { name: /^Acting as Priya Raman,/ })).toBeVisible({ timeout: 90_000 });
});
