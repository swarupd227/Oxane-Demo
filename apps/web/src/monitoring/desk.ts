/* The desk as one list: the four facilities worked in full and the rest of the book, each
 * reduced to the same row. Every figure here comes from the API; this only arranges it. */
import { createContext, useContext } from "react";
import type { BookFacility, ClientId, Cycle, CycleActor, CycleSession, HeadroomRow, Submission } from "./cycle";
import { fmtUnit, when } from "./ui";

export type ClientScope = "all" | ClientId;
export const ScopeContext = createContext<{ client: ClientScope; setClient: (c: ClientScope) => void }>({ client: "all", setClient: () => undefined });
export function useScope() {
  return useContext(ScopeContext);
}

export type TestRow = BookFacility["tests"][number] & { note?: string };
export type ReportStatus = "released" | "in_review" | "preparing" | "provisional" | "held";

export interface DeskRow {
  id: string;
  name: string;
  client: ClientId;
  client_name: string;
  ai_permitted: boolean;
  type: string;
  asset_class: string;
  role: string;
  size: string;
  analyst: string;
  reporting: string;
  period: string;
  worked: boolean;
  documents: { received: number; total: number; late: number };
  tests: TestRow[];
  breaches: number;
  warnings: number;
  open: number;
  exceptions: number;
  status: "breach" | "watch" | "ok";
  report: { status: ReportStatus; done: number; levels: number; at: string | null; by: string | null };
  trend: { label: string; unit: string; limit: number; direction: "max" | "min"; series: { period: string; value: number }[] } | null;
}

export const REPORT_LABEL: Record<ReportStatus, string> = {
  released: "Released",
  in_review: "In review",
  preparing: "Preparing",
  provisional: "Provisional",
  held: "Load held",
};

function statusOf(tests: TestRow[], open: number): DeskRow["status"] {
  if (tests.some((t) => !t.passed)) {
    return "breach";
  }
  return tests.some((t) => t.early_warning) || open ? "watch" : "ok";
}

export function allSubmissions(cycle: Cycle): Submission[] {
  return [...cycle.submissions, ...(cycle.book?.submissions ?? [])];
}

export function allHeadroom(cycle: Cycle): HeadroomRow[] {
  return [...cycle.headroom, ...(cycle.book?.headroom ?? [])];
}

export function deskRows(cycle: Cycle, session: CycleSession | undefined): DeskRow[] {
  const worked = cycle.facilities.map((f): DeskRow => {
    const client = cycle.clients.find((c) => c.id === f.client)!;
    const subs = cycle.submissions.filter((s) => s.facility === f.id);
    const tests = cycle.headroom.filter((r) => r.facility === f.id);
    const findings = cycle.findings.filter((x) => x.facility.split(",").includes(f.id));
    const open = findings.filter((x) => !x.rule_outcome && !session?.decisions[x.id]).length;
    const approvals = session?.approvals[f.id] ?? [];
    const released = session?.packs[f.id];
    const status: ReportStatus = released ? "released" : session?.held[f.id] ? "held" : approvals.length ? "in_review" : "provisional";
    const first = tests[0];
    return {
      id: f.id,
      name: f.name,
      client: f.client,
      client_name: f.client_name,
      ai_permitted: f.ai_permitted,
      type: f.type,
      asset_class: f.asset_class,
      role: f.role,
      size: f.size,
      analyst: client.contact.name,
      reporting: f.reporting.startsWith("Quarterly") ? "Quarterly" : "Monthly",
      period: f.id === "kestrel" ? "Q1 2026" : cycle.cycle.label,
      worked: true,
      documents: {
        received: subs.filter((s) => s.received || s.reused).length,
        total: subs.length,
        late: subs.filter((s) => s.status === "late").length,
      },
      tests,
      breaches: tests.filter((t) => !t.passed).length,
      warnings: tests.filter((t) => t.early_warning).length,
      open,
      exceptions: findings.filter((x) => !x.rule_outcome).length,
      status: statusOf(tests, open),
      report: {
        status,
        done: approvals.length + (released || approvals.length ? 1 : 0),
        levels: client.approval_levels.length,
        at: released?.at ?? approvals.at(-1)?.at ?? null,
        by: released?.by ?? approvals.at(-1)?.by ?? null,
      },
      trend: first ? { label: first.test, unit: first.unit, limit: first.limit, direction: first.direction, series: first.series } : null,
    };
  });
  const book = (cycle.book?.facilities ?? []).map(
    (f): DeskRow => ({
      ...f,
      worked: false,
      breaches: f.tests.filter((t) => !t.passed).length,
      warnings: f.tests.filter((t) => t.early_warning).length,
      open: 0,
      exceptions: 0,
      status: statusOf(f.tests, 0),
      report: {
        status: f.report.status,
        done: f.report.done,
        levels: f.report.levels,
        at: f.report.released_at ?? f.report.approvals.at(-1)?.at ?? f.report.prepared?.at ?? null,
        by: f.report.approvals.at(-1)?.by ?? f.report.prepared?.by ?? null,
      },
    }),
  );
  return [...worked, ...book];
}

export interface Notice {
  id: string;
  tone: "danger" | "warn" | "info";
  title: string;
  detail: string;
  to: string;
  at?: string;
}

export function notices(cycle: Cycle, session: CycleSession | undefined, actor: CycleActor): Notice[] {
  const name = (id: string) => cycle.facilities.find((f) => f.id === id)?.name ?? id;
  const items: Notice[] = [];
  for (const s of cycle.submissions.filter((x) => x.status === "late")) {
    items.push({
      id: `late-${s.ref}`,
      tone: "danger",
      title: `${s.label} overdue`,
      detail: `${name(s.facility)} · due ${when(s.due)}${s.chase.length ? ` · escalated ${when(s.chase.at(-1)!.at)}` : ""}`,
      to: "/monitoring/submissions",
      at: s.chase.at(-1)?.at,
    });
  }
  for (const f of cycle.facilities) {
    if (session?.held[f.id]) {
      const feed = cycle.validation.feeds.find((x) => x.facility === f.id && x.held);
      items.push({ id: `held-${f.id}`, tone: "danger", title: "Load held", detail: `${name(f.id)} · blocking rule ${feed?.resolution?.rule ?? ""}`, to: "/monitoring/validation" });
    }
    if (session?.qcOpen[f.id]?.length) {
      items.push({ id: `qc-${f.id}`, tone: "warn", title: "QC variance open", detail: `${name(f.id)} · ${session.qcOpen[f.id].join(", ")}`, to: "/monitoring/pack" });
    }
  }
  for (const r of cycle.headroom.filter((x) => !x.passed)) {
    items.push({ id: `breach-${r.facility}-${r.test}`, tone: "danger", title: `${r.test} over limit`, detail: `${name(r.facility)} · ${fmtUnit(r.value, r.unit)} against ${r.direction === "max" ? "≤" : "≥"} ${fmtUnit(r.limit, r.unit)}`, to: "/monitoring/covenants" });
  }
  for (const w of cycle.early_warnings) {
    items.push({ id: `ew-${w.facility}-${w.subject}`, tone: "warn", title: `${w.kind}: ${w.subject}`, detail: `${name(w.facility)} · ${w.detail}`, to: "/monitoring/monitor" });
  }
  for (const a of session?.alerts ?? []) {
    if (a.status === "requested") {
      items.push({ id: `alert-${a.id}`, tone: "info", title: "Alert request awaiting approval", detail: a.summary ?? a.request, to: "/monitoring/monitor", at: a.requestedAt });
    }
  }
  if (actor === "analyst") {
    const open = cycle.findings.filter((f) => !f.rule_outcome && !session?.decisions[f.id]).length;
    if (open) {
      items.push({ id: "triage", tone: "info", title: `${open} exception${open === 1 ? "" : "s"} to decide`, detail: "Assigned to you", to: "/monitoring/triage" });
    }
  } else {
    for (const f of cycle.facilities) {
      const next = session?.levels[f.id]?.[(session.approvals[f.id] ?? []).length];
      if (next?.actor === actor && !session?.packs[f.id] && !session?.pending[f.id]?.length) {
        items.push({ id: `approve-${f.id}`, tone: "info", title: "Report awaiting your approval", detail: `${name(f.id)} · level ${next.level}`, to: "/monitoring/pack" });
      }
    }
  }
  return items;
}
