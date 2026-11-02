import { expect, test } from "@playwright/test";
import { TIER_2_AND_3, approveButton, resetCase, step, term } from "./helpers";

test("a complete onboarding, through the screen, from pack to scorecard", async ({ page, request }) => {
  await resetCase(request);

  await test.step("Deal", async () => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Calderwood Bank");
    await expect(page.getByText("Sandbox environment.")).toBeVisible();
    await page.getByRole("button", { name: "Start onboarding" }).click();
  });

  await test.step("Intake", async () => {
    await page.getByRole("button", { name: "Load sandbox pack" }).click();
    await expect(page.getByText("Expected but not received")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("tbody tr")).toHaveCount(8);
    await expect(page.getByText("Schedule 4")).toBeVisible();
    await page.getByRole("button", { name: "Review facility terms" }).click();
  });

  await test.step("Terms", async () => {
    await expect(page.locator("[data-highlight]").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Amendment No. 1, 2(a)").first()).toBeVisible();

    const slider = page.getByRole("slider");
    await slider.fill(String(Date.UTC(2026, 1, 10)));
    await expect(page.getByRole("img", { name: /Credit Agreement.*page 16/i })).toBeVisible();

    await term(page, "Facility limit");
    await expect(page.getByRole("img", { name: /page 61/ })).toBeVisible();
    await expect(page.locator("[data-highlight]").first()).toBeVisible({ timeout: 10_000 });
    await approveButton(page).click();

    await term(page, "Advance rate");
    await approveButton(page).click();
    await page.getByRole("button", { name: TIER_2_AND_3 }).click();
    await expect(page.getByText(/2[0-9] of 26 approved/)).toBeVisible();
  });

  await test.step("Rules", async () => {
    await step(page, "Rules");
    await page.getByRole("button", { name: "Edit E5" }).click();
    await page.getByRole("spinbutton").fill("70000");
    await expect(page.getByText("Loans becoming ineligible")).toBeVisible();
    await page.getByRole("dialog").getByRole("textbox").fill("Stress test for the April tape");
    await page.getByRole("button", { name: "Save as pending" }).click();
    await expect(page.getByText("Pending rule set v2:")).toBeVisible();
  });

  await test.step("Mapping", async () => {
    await step(page, "Mapping");
    await expect(page.getByText("38 tape columns mapped")).toBeVisible();
    await page.getByRole("button", { name: "Accept LoanNumber" }).click();
    await expect(page.getByText("1 accepted.")).toBeVisible();
    await page.getByRole("button", { name: /Accept remaining/ }).click();
    await page.getByRole("button", { name: "View validation" }).click();
  });

  await test.step("Validation", async () => {
    await page.getByRole("button", { name: "Run the April tape" }).click();
    await expect(page.getByText("Eligible pool bridge")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Provisional: E7 not run.")).toBeVisible();
    await expect(page.getByText("Unexplained: US$0")).toBeVisible();
    await page.getByRole("button", { name: /Duplicate VINs/ }).click();
    await expect(page.getByText("Possible double pledging.")).toBeVisible();
    await page.getByRole("button", { name: "View exception queue" }).click();
  });

  await test.step("Exceptions", async () => {
    await expect(page.getByText("3 open of 10")).toBeVisible();
    await page.getByRole("button", { name: /41 loans over 30 days/ }).click();
    await page.getByRole("button", { name: "Draft query" }).click();
    await page.getByRole("button", { name: "Log query" }).click();
    await page.getByRole("button", { name: /6 loans share 3 VINs/ }).click();
    await page.getByRole("button", { name: "Escalate to credit" }).click();
    await page.getByRole("button", { name: /Sunrise Motors/ }).click();
    await page.getByRole("button", { name: "Accept", exact: true }).click();
    await expect(page.getByText("Borrowing base recalculated")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("US$193,347")).toBeVisible();
    await page.getByRole("button", { name: "View approval" }).click();
  });

  await test.step("Approve", async () => {
    await expect(page.getByText("You prepared this case")).toBeVisible();
    await expect(page.getByRole("button", { name: /Approve with \d open items/ })).toBeDisabled();
    await page.getByRole("button", { name: "Second analyst" }).click();
    await expect(page.getByRole("heading", { name: "Change summary" })).toBeVisible();
    await expect(page.getByText("38 of 38 columns accepted")).toBeVisible();
    await page.getByLabel("Decision reason").fill("The agreement's threshold stands");
    await page.getByRole("button", { name: "Decline" }).click();
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: /Approve with \d open items/ }).click();
    await expect(page.getByText("Approved with open items").first()).toBeVisible();

    const download = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download load file" }).click();
    const saved = await download;
    expect(saved.suggestedFilename()).toBe("case-0412-load-file.json");
    const content = await saved.createReadStream();
    let body = "";
    for await (const chunk of content) body += chunk;
    expect(JSON.parse(body).loans).toHaveLength(2400);
    await page.getByRole("button", { name: "View scorecard" }).click();
  });

  await test.step("Scorecard", async () => {
    await expect(page.getByText("Exceptions found", { exact: true })).toBeVisible();
    await expect(page.getByText("Extraction was tuned on this synthetic pack.")).toBeVisible();
    await page.getByText("Field-level accuracy, Tier 1, before review").click();
    await expect(page.getByText("How it is calculated:").first()).toBeVisible();
  });
});
