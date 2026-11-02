import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const TIER_2_AND_3 = /Approve high-confidence Tier 2 and 3/;

export async function resetCase(request: APIRequestContext) {
  await request.post("/api/session/reset");
}

async function act(request: APIRequestContext, type: string, payload: object = {}, actor = "analyst") {
  const response = await request.post("/api/session/events", { data: { type, actor, payload } });
  expect(response.status(), `${type} should be accepted`).toBe(200);
}

/** Bring the case to a screen through the API, so one screen's test does not depend on another. */
export async function prepare(
  request: APIRequestContext,
  stage: "loaded" | "terms" | "run" | "worked" | "approved",
) {
  await resetCase(request);
  await act(request, "intake-done");
  if (stage === "loaded") return;
  const { terms } = await (await request.get("/api/workbench")).json();
  const names = terms
    .filter((term: { tier: number; confidence: string }) => term.tier > 1 && term.confidence === "high")
    .map((term: { name: string }) => term.name);
  await act(request, "bulk-approve", { names });
  await act(request, "approve-term", { name: "Facility limit" });
  await act(request, "approve-term", { name: "Advance rate" });
  if (stage === "terms") return;
  await act(request, "accept-mapping");
  await act(request, "run");
  if (stage === "run") return;
  await act(request, "work-exception", { id: "X4", outcome: "queried", note: "Certificate query" });
  await act(request, "work-exception", { id: "X5", outcome: "escalated", note: "Credit review" });
  await act(request, "work-exception", { id: "X6", outcome: "accepted", note: "Same dealer" });
  if (stage === "worked") return;
  await act(request, "approve-load", { carry_forward: true }, "approver");
}

export async function step(page: Page, name: string) {
  await page.getByRole("navigation", { name: "Onboarding steps" }).getByRole("link", { name }).click();
}

export async function term(page: Page, name: string) {
  await page.locator("tbody").getByRole("button", { name, exact: true }).click();
}

export const approveButton = (page: Page) => page.getByRole("button", { name: "Approve", exact: true });
