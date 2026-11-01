/* Screen recordings to fall back on if a step fails live. Run with `npm run fallback`. */
import { copyFile, mkdir } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { TIER_2_AND_3, approveButton, prepare, resetCase, term } from "./helpers";

async function pause(page: Page, seconds: number) {
  await page.waitForTimeout(seconds * 1000);
}

test.afterEach(async ({ page }, info) => {
  const video = page.video();
  await page.close();
  if (video) {
    await mkdir("fallback-recordings", { recursive: true });
    await copyFile(await video.path(), `fallback-recordings/${info.title}.webm`);
  }
});

test("1-deal", async ({ page, request }) => {
  await resetCase(request);
  await page.goto("/");
  await pause(page, 5);
});

test("2-intake", async ({ page, request }) => {
  await resetCase(request);
  await page.goto("/intake");
  await page.getByRole("button", { name: /Sandbox document pack/ }).click();
  await expect(page.getByText("Expected but not received")).toBeVisible({ timeout: 10_000 });
  await pause(page, 4);
});

test("3-terms", async ({ page, request }) => {
  await prepare(request, "loaded");
  await page.goto("/terms");
  await expect(page.locator("[data-highlight]").first()).toBeVisible({ timeout: 10_000 });
  await pause(page, 3);
  await page.getByRole("slider").fill(String(Date.UTC(2026, 1, 10)));
  await pause(page, 3);
  await page.getByRole("slider").fill(String(Date.UTC(2026, 3, 30)));
  await pause(page, 2);
  await term(page, "Facility limit");
  await pause(page, 3);
  await approveButton(page).click();
  await page.getByRole("button", { name: TIER_2_AND_3 }).click();
  await pause(page, 2);
});

test("4-rules", async ({ page, request }) => {
  await prepare(request, "terms");
  await page.goto("/rules");
  await pause(page, 3);
  await page.getByRole("button", { name: "Edit E5" }).click();
  await page.getByRole("spinbutton").fill("70000");
  await pause(page, 3);
  await page.getByRole("dialog").getByRole("textbox").fill("Stress test for the April tape");
  await page.getByRole("button", { name: "Save as pending" }).click();
  await pause(page, 2);
});

test("5-mapping", async ({ page, request }) => {
  await prepare(request, "terms");
  await page.goto("/mapping");
  await pause(page, 4);
  await page.getByRole("button", { name: "Accept mapping" }).click();
  await pause(page, 2);
});

test("6-validation", async ({ page, request }) => {
  await prepare(request, "terms");
  await request.post("/api/session/events", { data: { type: "accept-mapping", actor: "analyst", payload: {} } });
  await page.goto("/validation");
  await page.getByRole("button", { name: "Run the April tape" }).click();
  await expect(page.getByText("Eligible pool bridge")).toBeVisible({ timeout: 10_000 });
  await pause(page, 4);
  await page.getByRole("button", { name: /Duplicate VINs/ }).click();
  await pause(page, 4);
});

test("7-exceptions", async ({ page, request }) => {
  await prepare(request, "run");
  await page.goto("/exceptions");
  await pause(page, 2);
  await page.getByRole("button", { name: /41 loans over 30 days/ }).click();
  await page.getByRole("button", { name: "Draft query" }).click();
  await pause(page, 2);
  await page.getByRole("button", { name: "Log query" }).click();
  await page.getByRole("button", { name: /6 loans share 3 VINs/ }).click();
  await page.getByRole("button", { name: "Escalate to credit" }).click();
  await pause(page, 2);
  await page.getByRole("button", { name: /Sunrise Motors/ }).click();
  await page.getByRole("button", { name: "Accept", exact: true }).click();
  await expect(page.getByText("Borrowing base recalculated")).toBeVisible({ timeout: 10_000 });
  await pause(page, 4);
});

test("8-approve", async ({ page, request }) => {
  await prepare(request, "worked");
  await page.goto("/approve");
  await pause(page, 3);
  await page.getByRole("button", { name: "Second analyst" }).click();
  await page.getByRole("checkbox").check();
  await pause(page, 1);
  await page.getByRole("button", { name: /Approve with \d open items/ }).click();
  await pause(page, 3);
});

test("9-scorecard", async ({ page, request }) => {
  await prepare(request, "approved");
  await page.goto("/results");
  await expect(page.getByText("Exceptions found", { exact: true })).toBeVisible();
  await pause(page, 3);
  await page.getByText("Exceptions found", { exact: true }).click();
  await pause(page, 3);
  await resetCase(request);
});
