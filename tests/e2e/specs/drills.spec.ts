import { expect, test } from "@playwright/test";
import { prepare, resetCase, term } from "./helpers";

test.describe("when something goes wrong on stage", () => {
  test("a page reload keeps the case and its progress", async ({ page, request }) => {
    await prepare(request, "terms");
    await page.goto("/exceptions");
    await expect(page.getByText("3 open of 10")).toBeVisible();
    await page.reload();
    await expect(page.getByText("3 open of 10")).toBeVisible();
  });

  test("workbench data failing shows an error with a retry, and recovers", async ({ page, request }) => {
    await prepare(request, "loaded");
    let failing = true;
    await page.route("**/api/workbench", (route) => (failing ? route.abort() : route.continue()));
    await page.goto("/terms");
    await expect(page.getByText("The workbench data could not be loaded.")).toBeVisible({ timeout: 15_000 });
    failing = false;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByRole("heading", { name: "Facility terms" })).toBeVisible();
  });

  test("the session service failing is reported, not shown as an empty case", async ({ page }) => {
    await page.route("**/api/session", (route) => route.abort());
    await page.goto("/");
    await expect(page.getByText("The session service is not responding.")).toBeVisible({ timeout: 15_000 });
  });

  test("a failed run says so and can be retried", async ({ page, request }) => {
    await prepare(request, "run");
    let failing = true;
    await page.route("**/api/run", (route) => (failing ? route.abort() : route.continue()));
    await page.goto("/validation");
    await expect(page.getByText("The run could not be completed.")).toBeVisible({ timeout: 15_000 });
    failing = false;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByText("Eligible pool bridge")).toBeVisible();
  });

  test("the scorecard failing says so and can be retried", async ({ page, request }) => {
    await prepare(request, "approved");
    let failing = true;
    await page.route("**/api/scorecard", (route) => (failing ? route.abort() : route.continue()));
    await page.goto("/results");
    await expect(page.getByText("The scorecard could not be calculated.")).toBeVisible({ timeout: 15_000 });
    failing = false;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByText("Exceptions found", { exact: true })).toBeVisible();
  });

  test("a refused action is explained on screen", async ({ page, request }) => {
    await prepare(request, "loaded");
    await page.goto("/terms");
    await expect(page.getByRole("heading", { name: "Facility terms" })).toBeVisible();
    await page.route("**/api/session/events", (route) =>
      route.fulfill({ status: 409, json: { detail: "This case is approved and can no longer be changed" } }),
    );
    await term(page, "Margin");
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("no longer be changed");
    await page.getByRole("button", { name: "Dismiss" }).click();
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("moving quickly between terms never leaves a broken page", async ({ page, request }) => {
    await prepare(request, "loaded");
    await page.goto("/terms");
    await expect(page.locator("[data-highlight]").first()).toBeVisible({ timeout: 10_000 });
    for (let press = 0; press < 8; press += 1) {
      await page.keyboard.press("j");
    }
    await term(page, "Margin");
    await expect(page.locator("[data-highlight]").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("This page could not be opened.")).toHaveCount(0);
  });
});

test.describe("spec behaviour", () => {
  test("a term sent to the queue appears there and blocks approval until worked", async ({ page, request }) => {
    await prepare(request, "worked");
    await page.goto("/terms");
    await term(page, "Margin");
    await page.getByRole("button", { name: "Send to queue" }).click();
    await page.goto("/exceptions");
    await page.getByRole("button", { name: /Margin sent to the queue/ }).click();
    await expect(page.getByText("1 open of 11")).toBeVisible();
    await page.getByRole("button", { name: "Accept", exact: true }).click();
    await expect(page.getByText("0 open of 11")).toBeVisible();
  });

  test("the real pack is accepted when dropped, matched by content", async ({ page, request }) => {
    await resetCase(request);
    const { documents } = await (await request.get("/api/workbench")).json();
    const files = await Promise.all(
      documents.map(async (doc: { file: string }) => ({
        name: `copy-of-${doc.file}`,
        mimeType: "application/octet-stream",
        buffer: await (await request.get(`/api/pack/${doc.file}`)).body(),
      })),
    );
    await page.goto("/intake");
    await page.locator('input[type="file"]').setInputFiles(files);
    await expect(page.getByText("Expected but not received")).toBeVisible({ timeout: 15_000 });
  });

  test("a stray or missing file is named and the pack is not loaded", async ({ page, request }) => {
    await resetCase(request);
    await page.goto("/intake");
    await page.locator('input[type="file"]').setInputFiles({
      name: "holiday-photos.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("not a pack file"),
    });
    await expect(page.getByRole("alert")).toContainText("0 of 8 files matched");
    await expect(page.getByRole("alert")).toContainText("holiday-photos.zip");
    await expect(page.getByRole("button", { name: "Load sandbox pack" })).toBeVisible();
  });

  test("a second analyst can approve a rule change, and the bridge shows its effect", async ({ page, request }) => {
    await prepare(request, "worked");
    await request.post("/api/session/events", {
      data: {
        type: "propose-rule",
        actor: "analyst",
        payload: { rule_id: "E5", from: 75000, to: 70000, reason: "Tighter cap" },
      },
    });
    await page.goto("/approve");
    await page.getByRole("button", { name: "Second analyst" }).click();
    await page.getByLabel("Decision reason").fill("Agreed with credit");
    await page.getByRole("button", { name: "Approve change" }).click();
    await expect(page.getByText("E5: 75000 to 70000 (approved)")).toBeVisible();
    await page.goto("/validation");
    await expect(page.getByText(/loans failing E5/)).toBeVisible();
    await expect(page.getByText("Unexplained: US$0")).toBeVisible();
  });
});

test.describe("keyboard control", () => {
  test("Alt+R resets the case from any screen", async ({ page, request }) => {
    await prepare(request, "terms");
    await page.goto("/exceptions");
    await expect(page.getByText("3 open of 10")).toBeVisible();
    await page.keyboard.press("Alt+r");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText("Awaiting pack")).toBeVisible();
  });

  test("Alt+P turns large text on and off", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Alt+p");
    await expect(page.locator("html")).toHaveAttribute("data-presenter", "true");
    await page.keyboard.press("Alt+p");
    await expect(page.locator("html")).toHaveAttribute("data-presenter", "false");
  });

  test("square brackets move between steps", async ({ page }) => {
    await page.goto("/intake");
    await page.keyboard.press("]");
    await expect(page).toHaveURL(/terms/);
    await page.keyboard.press("[");
    await expect(page).toHaveURL(/intake/);
  });

  test("the command menu finds exactly what was typed", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Control+k");
    await page.getByPlaceholder("Go to a step or run a command").fill("reset");
    await expect(page.getByRole("option")).toHaveCount(1);
    await expect(page.getByRole("option")).toContainText("Reset sandbox case");
  });
});

test.afterAll(async ({ request }) => {
  await resetCase(request);
});
