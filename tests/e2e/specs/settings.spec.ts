/* Settings › AI provider: only the administrator sees it, and a dummy key typed there fails its
 * connection test with the provider's reason. Nothing is saved, so the API's key and the local
 * .env are left as they were. Needs DEMO_ACCESS_CODE. SHOTS_DIR, when set, keeps screenshots. */
import { expect, test, type Page } from "@playwright/test";

const CODE = process.env.DEMO_ACCESS_CODE ?? "";
const SHOTS = process.env.SHOTS_DIR;
const DUMMY = "sk-ant-api03-e2e-dummy-key-not-real-0000000000000000";

test.describe.configure({ mode: "serial", timeout: 240_000 });

async function switchTo(page: Page, name: string) {
  await page.getByRole("button", { name: /^Acting as/ }).click();
  await page.getByRole("menuitemradio", { name: new RegExp(name) }).click();
  await expect(page.getByRole("button", { name: new RegExp(`^Acting as ${name}`) })).toBeVisible();
}

async function enterCode(_page: Page) {
  // There is no access code any more: uploads, live AI and settings need only the right persona.
}

async function shot(page: Page, name: string) {
  if (SHOTS) {
    await page.screenshot({ path: `${SHOTS}/settings-${name}.png` });
  }
}

async function personaMenuHasSettings(page: Page): Promise<boolean> {
  // Wait for the persona to load: a menu opened while it reads "Loading" has no role items yet.
  await expect(page.getByRole("button", { name: /^Acting as (?!Loading)/ })).toBeVisible();
  await page.getByRole("button", { name: /^Acting as/ }).click();
  const has = await page.getByRole("menuitem", { name: "Settings" }).isVisible();
  await page.keyboard.press("Escape");
  return has;
}

test("other personas cannot see Settings, and the API refuses them", async ({ page, request }) => {
  await page.goto("/work");
  for (const name of ["Hannah Cole", "Priya Raman", "Elena Varga", "Marcus Hale"]) {
    await switchTo(page, name);
    await page.goto("/work");
    await expect(page.getByRole("button", { name: new RegExp(`^Acting as ${name}`) })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("navigation", { name: "Workspace" }).getByRole("link", { name: "My work" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Settings" })).toHaveCount(0);
    expect(await personaMenuHasSettings(page)).toBe(false);
  }
  await page.goto("/monitoring");
  await expect(page.getByRole("link", { name: "Settings" })).toHaveCount(0);
  expect(await personaMenuHasSettings(page)).toBe(false);
  await page.goto("/settings/ai-provider");
  await expect(page.getByText("Administrator only", { exact: true })).toBeVisible();
  await shot(page, "not-admin");
  const refused = await request.get("/api/admin/ai-provider", { headers: { "X-Acting-User": "hannah", "X-Demo-Access-Code": CODE } });
  expect(refused.status()).toBe(403);
  // No access code: the administrator persona alone opens the settings.
  const admin = await request.get("/api/admin/ai-provider", { headers: { "X-Acting-User": "alex" } });
  expect(admin.status()).toBe(200);
});

test("the administrator tests a dummy key and sees why it failed", async ({ page }) => {
  await page.goto("/work");
  await switchTo(page, "Alex Morgan");
  await page.evaluate(() => window.localStorage.removeItem("oxane.access-code"));
  await page.goto("/work");
  await page.getByRole("navigation", { name: "Workspace" }).getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(/\/settings\/ai-provider$/);
  await enterCode(page);
  const status = page.getByTestId("provider-status");
  await expect(status).toBeVisible();
  await expect(status.getByText("Source")).toBeVisible();
  await shot(page, "status");

  const key = page.locator("#ai-key");
  await key.fill(DUMMY);
  await expect(page.locator("#ai-key")).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show key" }).click();
  await expect(page.locator("#ai-key")).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Hide key" }).click();
  await expect(page.locator("#ai-key")).toHaveAttribute("type", "password");

  await page.getByRole("button", { name: "Test connection" }).click();
  const result = page.getByTestId("test-result");
  await expect(result).toContainText(/^Failed · (HTTP 4\d\d|No response)/);
  await expect(result).not.toContainText(DUMMY);
  await shot(page, "test-failed");

  // Settings is reachable from both workbenches.
  await page.goto("/cases");
  await expect(page.getByRole("navigation", { name: "Platform" }).getByRole("link", { name: "Settings" })).toBeVisible();
  await page.goto("/monitoring");
  expect(await personaMenuHasSettings(page)).toBe(true);
});
