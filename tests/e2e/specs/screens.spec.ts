import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { prepare, resetCase } from "./helpers";

const SCREENS = [
  { path: "/", name: "deal", stage: "loaded", heading: /Calderwood Bank/ },
  { path: "/intake", name: "intake", stage: "loaded", heading: "Document intake" },
  { path: "/terms", name: "terms", stage: "loaded", heading: "Facility terms" },
  { path: "/rules", name: "rules", stage: "loaded", heading: "Eligibility and concentration rules" },
  { path: "/mapping", name: "mapping", stage: "loaded", heading: "Data mapping" },
  { path: "/validation", name: "validation", stage: "run", heading: "First validation run" },
  { path: "/exceptions", name: "exceptions", stage: "run", heading: "Exception queue" },
  { path: "/approve", name: "approve", stage: "worked", heading: "Approve and load" },
  { path: "/results", name: "scorecard", stage: "approved", heading: "Scorecard" },
] as const;

const FORBIDDEN = /\b(demo|mock-?up|prototype|seed data|answer key|planted|presenter|rehears\w*|scene \d|phase \d)\b/i;

for (const screen of SCREENS) {
  test.describe(screen.name, () => {
    test.beforeEach(async ({ page, request }) => {
      await prepare(request, screen.stage);
      await page.goto(screen.path);
      await expect(page.getByRole("heading", { level: 1 })).toContainText(screen.heading);
    });

    test("has no WCAG A or AA violations", async ({ page }) => {
      const { violations } = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(violations.map((item) => item.id)).toEqual([]);
    });

    test("reads like a working product", async ({ page }) => {
      expect(await page.locator("body").innerText()).not.toMatch(FORBIDDEN);
    });

    for (const width of [1920, 1440]) {
      test(`does not scroll sideways at ${width}`, async ({ page }) => {
        await page.setViewportSize({ width, height: width === 1920 ? 1080 : 900 });
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - window.innerWidth,
        );
        expect(overflow).toBeLessThanOrEqual(0);
      });
    }
  });
}

test.afterAll(async ({ request }) => {
  await resetCase(request);
});
