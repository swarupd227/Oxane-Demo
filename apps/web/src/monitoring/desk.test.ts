import { describe, expect, it } from "vitest";
import type { Cycle, CycleSession } from "./cycle";
import { deskRows, notices } from "./desk";

const test = (passed: boolean, early = false) => ({
  test: "CCC share",
  clause: "Section 1.1",
  value: passed ? 4 : 8.41,
  limit: 7.5,
  unit: "%",
  direction: "max" as const,
  headroom: 1,
  used_pct: 50,
  passed,
  early_warning: early,
  trend: "flat" as const,
  series: [{ period: "May 2026", value: 4 }],
  note: "",
  source: null,
});

const cycle = {
  cycle: { id: "M-2026-05", label: "May 2026", period_end: "2026-05-31", as_of: "2026-06-24" },
  clients: [{ id: "thornbury", name: "Thornbury Bank N.A.", ai_permitted: false, contact: { name: "Daniel Okafor", role: "" }, approval_levels: [{}, {}, {}] }],
  facilities: [{ id: "larkspur", name: "Larkspur CLO", client: "thornbury", client_name: "Thornbury Bank N.A.", ai_permitted: false, type: "", asset_class: "CLO / BSL", role: "", size: "US$400m", reporting: "Monthly" }],
  submissions: [{ ref: "SUB-1", facility: "larkspur", label: "Collateral report, May", status: "late", due: "2026-06-12", received: null, reused: null, chase: [], client: "thornbury" }],
  headroom: [{ ...test(false), facility: "larkspur" }],
  findings: [{ id: "F-larkspur-ccc", facility: "larkspur", rule_outcome: null }],
  validation: { feeds: [] },
  early_warnings: [],
  book: {
    facilities: [
      {
        id: "ambleside",
        name: "Ambleside CLO",
        client: "thornbury",
        client_name: "Thornbury Bank N.A.",
        ai_permitted: false,
        tests: [test(true)],
        documents: { received: 2, total: 2, late: 0 },
        report: { status: "released", levels: 3, done: 3, prepared: { by: "Wei Chen", at: "2026-06-15T10:00:00" }, approvals: [], released_at: "2026-06-16T10:00:00" },
        trend: { label: "CCC share", unit: "%", limit: 7.5, direction: "max", series: [] },
      },
    ],
    submissions: [],
    headroom: [],
  },
} as unknown as Cycle;

describe("deskRows", () => {
  it("puts the worked facilities and the rest of the book in one list", () => {
    const rows = deskRows(cycle, undefined);
    expect(rows.map((r) => r.id)).toEqual(["larkspur", "ambleside"]);
    expect(rows[0]).toMatchObject({ status: "breach", open: 1, analyst: "Daniel Okafor", documents: { late: 1 } });
    expect(rows[1]).toMatchObject({ status: "ok", report: { status: "released", done: 3, levels: 3 } });
  });
});

describe("notices", () => {
  it("raises overdue files, breaches and open exceptions for the analyst", () => {
    const session = { decisions: {}, held: {}, qcOpen: {}, alerts: [] } as unknown as CycleSession;
    const titles = notices(cycle, session, "analyst").map((n) => n.title);
    expect(titles).toEqual(["Collateral report, May overdue", "CCC share over limit", "1 exception to decide"]);
  });
});
