import { describe, expect, it } from "vitest";
import { visibleNav } from "../components/shell/WorkspaceShell";
import { cycleActor, MONITORING_ROLES, onboardingActor, ONBOARDING_ROLES, personaFor, type Persona } from "./persona";

const people: Persona[] = [
  { id: "marcus", name: "Marcus Hale", role: "reviewer", title: "", client: null, role_label: "Second analyst" },
  { id: "james", name: "James Whitcombe", role: "client", title: "", client: "calderwood", role_label: "Client user" },
  { id: "laura", name: "Laura Haskett", role: "client", title: "", client: "thornbury", role_label: "Client user" },
];

describe("persona model", () => {
  it("maps each role onto the scripted sessions' actors", () => {
    expect(onboardingActor("reviewer")).toBe("approver");
    expect(onboardingActor("qc")).toBe("analyst");
    expect(cycleActor("head")).toBe("senior");
    expect(cycleActor("client")).toBe("client");
    expect(cycleActor("monitoring_analyst")).toBe("analyst");
  });

  it("finds the persona to hand over to, scoped to a client", () => {
    expect(personaFor(people, "reviewer")?.name).toBe("Marcus Hale");
    expect(personaFor(people, "client", "thornbury")?.name).toBe("Laura Haskett");
  });

  it("shows each role only the areas it uses", () => {
    expect(visibleNav("client")).toEqual([]);
    expect(visibleNav("admin").map((n) => n.label)).toContain("Clients");
    expect(visibleNav("monitoring_analyst").map((n) => n.label)).not.toContain("Onboarding cases");
    expect(ONBOARDING_ROLES).not.toContain("client");
    expect(MONITORING_ROLES).not.toContain("client");
  });
});
