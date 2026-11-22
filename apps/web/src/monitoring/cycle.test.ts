import { describe, expect, it } from "vitest";
import { FACILITY_ORDER, clientOf, fillText, workbookUrl, type Cycle } from "./cycle";
import { STEPS } from "./MonitoringShell";

describe("fillText", () => {
  it("puts code's figures where the placeholders are", () => {
    expect(fillText("Gap of {{gap}} on {{loans}} loans", { gap: { value: "US$412,000.00" }, loans: { value: "27" } })).toBe("Gap of US$412,000.00 on 27 loans");
  });

  it("leaves an unknown placeholder visible rather than inventing a figure", () => {
    expect(fillText("Average {{missing}}", {})).toBe("Average {{missing}}");
  });
});

describe("clientOf", () => {
  const cycle = {
    facilities: [
      { id: "bramble", client: "calderwood" },
      { id: "larkspur", client: "thornbury" },
    ],
    clients: [
      { id: "calderwood", name: "Calderwood Bank plc", ai_permitted: true },
      { id: "thornbury", name: "Thornbury Bank N.A.", ai_permitted: false },
    ],
  } as unknown as Cycle;

  it("finds each facility's own client", () => {
    expect(clientOf(cycle, "larkspur")?.ai_permitted).toBe(false);
    expect(clientOf(cycle, "bramble")?.name).toBe("Calderwood Bank plc");
  });
});

describe("monitoring steps", () => {
  it("follow the order a cycle is worked", () => {
    const labels = STEPS.map((s) => s.label);
    const order = ["Submissions", "Mapping", "Validation", "Exceptions", "Reports", "Alerts", "Status calls", "Metrics"].map((l) => labels.indexOf(l));
    expect(order.every((index, i) => index > 0 && (i === 0 || index > order[i - 1]))).toBe(true);
  });

  it("cover all four facilities and serve each workbook", () => {
    expect(FACILITY_ORDER).toHaveLength(4);
    expect(workbookUrl("larkspur")).toBe("/api/monitoring/workbook/larkspur.xlsx");
  });
});
