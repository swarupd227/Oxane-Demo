/* Persona switching and the My work queue, shared by the monitoring, brief and agents specs. */
import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** True when the run targets a hosted app. Specs that reset the scripted sessions must not run
 * there: everyone using it shares one database. */
export function isHosted(url: string | undefined): boolean {
  return !!url && /^https:\/\//.test(url) && !/localhost|127\.0\.0\.1/.test(url);
}

/** Switch the acting user from the header menu, as a presenter would. The app then opens that
 * persona's home (My work, or the portal for a client user). */
export async function switchTo(page: Page, name: string) {
  // The menu reads "Acting as Loading" until the personas have loaded.
  const current = page.getByRole("button", { name: /^Acting as (?!Loading)/ });
  await expect(current).toBeVisible({ timeout: 90_000 });
  if (((await current.getAttribute("aria-label")) ?? "").startsWith(`Acting as ${name},`)) {
    return;
  }
  await current.click();
  await page.getByRole("menuitemradio", { name: new RegExp(`^${name}`) }).click();
  await expect(page.getByRole("button", { name: new RegExp(`^Acting as ${name},`) })).toBeVisible({ timeout: 30_000 });
}

/** Navigate, retrying once when the browser reports a network-level failure (the shared local
 * stack's Docker network occasionally changes under it); any other error is the test's to see. */
export async function go(page: Page, path: string) {
  try {
    await page.goto(path);
  } catch (error) {
    if (!/net::ERR_/.test(String(error))) {
      throw error;
    }
    await page.goto(path);
  }
}

/** Open a screen as a persona: load any page, switch, then go to the screen. */
export async function openAs(page: Page, name: string, path: string) {
  if (page.url() === "about:blank") {
    await go(page, path);
  }
  await switchTo(page, name);
  await go(page, path);
  await expect(page.getByRole("button", { name: new RegExp(`^Acting as ${name},`) })).toBeVisible({ timeout: 90_000 });
}

/** The "Waiting on you" panel of My work. */
export function waiting(page: Page) {
  return page.locator("section").filter({ has: page.getByRole("heading", { name: "Waiting on you" }) });
}

/** My work's title greets the acting person by first name ("Good morning, Priya"). */
export function myWorkTitle(page: Page, name?: string) {
  const who = name ? name.split(" ")[0] : "\\S+";
  return page.getByRole("heading", { level: 1, name: new RegExp(`^Good (morning|afternoon|evening), ${who}$`) });
}

export async function myWork(page: Page, name: string) {
  await openAs(page, name, "/work");
  await expect(myWorkTitle(page, name)).toBeVisible();
  return waiting(page);
}

export async function resetCycle(request: APIRequestContext) {
  const response = await request.post("/api/monitoring/session/reset");
  expect(response.status()).toBe(200);
}

/** Text of a KPI tile by its label. */
export function kpi(page: Page, label: string) {
  // Each KPI is its own card in a grid: a label paragraph, then the value paragraph.
  return page.locator(
    `xpath=//div[contains(concat(' ', @class, ' '), ' grid ')]/*[p[1][normalize-space(.)='${label}']]/p[2]`,
  );
}

/** Wait for a screen's heading. The workbench gives up on a slow API after 15 s and offers a
 * retry; on a busy shared stack that can happen, so retry (or reload) up to twice. */
export async function waitForScreen(page: Page, heading: string | RegExp) {
  const title = page.getByRole("heading", { level: 1, name: heading });
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      await title.waitFor({ state: "visible", timeout: 45_000 });
      return;
    } catch {
      const retry = page.getByRole("button", { name: /^(Retry|Try again)$/ });
      if (await retry.first().isVisible()) {
        await retry.first().click();
      } else {
        await page.reload();
      }
    }
  }
  await expect(title).toBeVisible({ timeout: 45_000 });
}
