import { describe, expect, it } from "vitest";
import { sceneNumber, scenes, stepOf, steps } from "./scenes";

describe("scenes", () => {
  it("keeps the nine steps in the stepper", () => {
    expect(steps.map((scene) => scene.label)).toEqual([
      "Deal", "Intake", "Terms", "Rules", "Mapping", "Validation", "Exceptions", "Approve",
      "Scorecard",
    ]);
  });

  it("places each worked scenario under its step", () => {
    expect(stepOf("/definitions")).toBe("/terms");
    expect(stepOf("/qc")).toBe("/approve");
    expect(stepOf("/rules")).toBe("/rules");
  });

  it("numbers sub-steps after their step", () => {
    const number = (path: string) => sceneNumber(scenes.find((scene) => scene.path === path)!);
    expect(number("/terms")).toBe("3");
    expect(number("/client-model")).toBe("7a");
    expect(number("/queries")).toBe("7b");
  });
});

describe("sections", () => {
  it("places every walkthrough screen in one sidebar section", async () => {
    const { sectionOf } = await import("./scenes");
    for (const scene of scenes) {
      expect(sectionOf(scene.path), scene.path).not.toBeNull();
    }
    expect(sectionOf("/queries")?.section.label).toBe("Exceptions & Queries");
    expect(sectionOf("/qc")?.child?.label).toBe("Independent QC");
  });
});
