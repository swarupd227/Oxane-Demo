/* The monitoring cycle, as the API serves it. Every number here was computed by the engine. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext } from "react";
import type { LlmMode } from "../lib/api";
import type { Rect } from "../lib/workbench";

export interface Source {
  document: string; // "pack/<file>" or "<facility>/<file>"
  page: number;
  rects: Rect[];
  label?: string;
}

export type Outcome = "logged" | "query" | "confirmed" | "expert";
export type FacilityId = "bramble" | "northmoor" | "kestrel";

export interface Facility {
  id: FacilityId;
  name: string;
  borrower: string;
  type: string;
  asset_class: string;
  role: string;
  size: string;
  size_note?: string;
  reporting: string;
}

export interface Chase {
  at: string;
  action: string;
  to: string;
  text: string;
}

export interface Submission {
  facility: FacilityId;
  label: string;
  file: string | null;
  due: string;
  received: string | null;
  status: "received" | "late" | "received_late" | "awaited";
  sender?: string;
  chase: Chase[];
}

export interface Trigger {
  monthly: { month: string; value: number }[];
  average: number;
  limit: number;
  direction: "max" | "min";
  breached: boolean;
  early_warning: boolean;
  headroom: number;
  next_month_breaches_beyond: number | null;
  clause: string;
  source: Source | null;
}

export interface Finding {
  id: string;
  facility: string; // one id, or two joined by a comma
  check: string;
  title: string;
  detail: string;
  owner?: string;
  amount?: number;
  loans?: string[];
  rule_outcome: "logged" | null;
  rule_reason?: string;
  suggested: { outcome: Outcome; reason: string; by: "AI" | "Rule" };
  sources: (Source | null)[];
  clauses: Source[];
}

export interface PackFigure {
  value: string;
  means: string;
  source: Source | null;
}

export interface LenderPack {
  facility: FacilityId;
  summary: string;
  sections: { heading: string; text: string }[];
  figures: Record<string, PackFigure>;
  unknown_placeholders: string[];
  numbers_in_text: string[];
}

export interface Holding {
  facility: FacilityId;
  loan_id: string;
  status: string;
  dealer_name: string;
  obligor_state: string;
  vehicle: string;
  origination_date: string;
  days_past_due: number;
  current_balance: number;
}

export interface TermRow {
  name: string;
  versions: {
    label: string;
    effective_from: string;
    value: string;
    clause?: string;
    source: Source | null;
  }[];
  in_force: string;
  value_in_force: string;
  next: string;
  next_value: string;
}

export interface Cycle {
  cycle: { id: string; label: string; period_end: string; as_of: string };
  lender: string;
  desk: string;
  tolerances: { certificate_usd: number; roll_forward_usd: number; trigger_warning_pts: number };
  facilities: Facility[];
  submissions: Submission[];
  layout: {
    facility: FacilityId;
    file: string;
    from_memory: number;
    columns_total: number;
    new_columns: { column: string; field: string | null; reason: string; values: string[]; outcome: string }[];
  };
  reconciliation: {
    roll_forward: {
      opening: number;
      additions: number;
      new_loans: number;
      collections: number;
      charge_offs: number;
      expected: number;
      actual: number;
      gap: number;
      within_tolerance: boolean;
      servicer_closing: number;
      sources: { collections: Source | null; opening: Source | null };
      missing: { loan_id: string; april_balance: number; dealer: string; state: string; vehicle: string }[];
      missing_april_balance: number;
    };
    charge_offs: {
      tape: number;
      report: number;
      difference: number;
      source: Source | null;
      schedule_source: Source | null;
      loans: { loan_id: string; report_amount: number; tape_status: string; tape_balance: number; days_past_due: number }[];
    };
    delinquency_trend: Record<string, { value: number; source: Source | null }>;
  };
  terms: {
    facility: FacilityId;
    period_end: string;
    periods_note: string;
    periods_source: Source | null;
    terms: TermRow[];
  };
  tests: {
    bramble: {
      borrowing_base: {
        system: { eligible_pool: number; excess: number; borrowing_base: number; availability: number; advance_rate_pct: number; provisional: boolean };
        certificate: { eligible_pool: number; borrowing_base: number; availability: number };
        differences: { eligible_pool: number; borrowing_base: number; availability: number };
        within_tolerance: boolean;
        tolerance: number;
        sunrise: { share_pct: number; excess: number };
      };
      delinquency: Trigger;
      leverage: {
        reported: number;
        recomputed: number;
        with_guarantees: number;
        maximum: number;
        tangible_net_worth_k: number;
        carve_out_k: number;
        total_liabilities_k: number;
        guarantees_k: number;
        guarantees: { description: string; amount: string; source: Source | null }[];
        reported_source: Source | null;
        clauses: Source[];
      };
      liquidity_k: number;
    };
    northmoor: {
      delinquency: Trigger;
      excess_spread: Trigger & { months_available: number; months_required: number; pending: string };
      excess_spread_months: { month: string; value: number; stated: string; source: Source | null }[];
      collections: { april: number; may: number; change: number; last_year_change: number; seasonal: boolean; history: { month: string; value_k: number }[] };
      borrowing_base: { status: string; reason: string };
      tapes: Record<string, number>;
    };
    kestrel: {
      nav: number;
      drawn: number;
      nav_source: Source | null;
      drawn_source: Source | null;
      ltv: {
        reported: number;
        with_markdown: number;
        limit: number;
        stated: string;
        markdown: number;
        headroom_pts: number;
        clause: string;
        clauses: Source[];
        events: { position: string; amount: number; date: string; source: Source | null }[];
      };
      valuations: {
        max_age_days: number;
        clause: string;
        calculation_date: string;
        positions: number;
        stale: { name: string; valued: string; age_days: number; value: number; source: Source | null }[];
      };
      concentration: { largest: string; largest_pct: number; top_five_pct: number; largest_limit: number; top_five_limit: number; passed: boolean; clause: string };
      positions: { name: string; value: number; valued: string }[];
    };
  };
  collateral: {
    checked: Record<FacilityId, number>;
    within: { vin: string; holdings: Holding[] }[];
    across: { vin: string; holdings: Holding[] }[];
    scope: string;
  };
  findings: Finding[];
  packs: LenderPack[];
  unverified: string[];
  usage: { model: string; calls: number; cost_usd: number; model_seconds: number };
  llm_mode: LlmMode;
}

export interface CycleAudit {
  at: string;
  actor: string;
  action: string;
  reason: string | null;
}

export interface CycleSession {
  openedAt: string | null;
  layoutConfirmed: boolean;
  triage: Record<string, { outcome: Outcome; note: string | null; at: string; overrode: boolean }>;
  packs: Partial<Record<FacilityId, { at: string; by: string }>>;
  audit: CycleAudit[];
  actions: number;
  decisions: Record<string, Outcome | null>;
  pending: Record<FacilityId, string[]>;
  chainIntact: boolean;
  chainHead: string;
}

export const OUTCOMES: Record<Outcome, { label: string; short: string; tone: string; who: string }> = {
  logged: { label: "Logged, no alert", short: "Logged", tone: "bg-sand text-muted", who: "Nobody; logged with its reason" },
  query: { label: "Query to sender", short: "Query", tone: "bg-info-tint text-info", who: "Borrower or servicer, chased by the system" },
  confirmed: { label: "Confirmed issue", short: "Confirmed", tone: "bg-danger-tint text-danger", who: "Analyst approves; lender is told" },
  expert: { label: "Expert review", short: "Expert", tone: "bg-warn-tint text-warn", who: "Credit or legal expert" },
};

const TIMEOUT_MS = 4000;

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!response.ok) {
    throw new Error(`${url} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function useCycle() {
  return useQuery({ queryKey: ["cycle"], queryFn: () => getJson<Cycle>("/api/monitoring/cycle"), staleTime: Infinity });
}

export function useCycleSession() {
  return useQuery({ queryKey: ["cycle-session"], queryFn: () => getJson<CycleSession>("/api/monitoring/session") });
}

export type CycleActor = "analyst" | "approver";
export const ActorContext = createContext<{ actor: CycleActor; setActor: (actor: CycleActor) => void }>({
  actor: "analyst",
  setActor: () => undefined,
});

export function useActor() {
  return useContext(ActorContext);
}

export class Refusal extends Error {}

export function useCycleAction() {
  const client = useQueryClient();
  const { actor } = useActor();
  return useMutation({
    mutationFn: async ({ type, payload = {}, as }: { type: string; payload?: Record<string, unknown>; as?: CycleActor }) => {
      const response = await fetch("/api/monitoring/session/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, actor: as ?? actor, payload }),
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Refusal(body.detail ?? "The server refused that action.");
      }
      return body as CycleSession;
    },
    onSuccess: (session) => client.setQueryData(["cycle-session"], session),
  });
}

export function useCycleReset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const response = await fetch("/api/monitoring/session/reset", { method: "POST" });
      return (await response.json()) as CycleSession;
    },
    onSuccess: (session) => {
      client.setQueryData(["cycle-session"], session);
      void client.invalidateQueries({ queryKey: ["cycle-scorecard"] });
    },
  });
}

export function useWhatIf() {
  return useMutation({
    mutationFn: async (value: number) => {
      const response = await fetch("/api/monitoring/what-if", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ facility: "northmoor", value }),
      });
      return (await response.json()) as { value: number; average: number; breached: boolean; limit: number; window: string[] };
    },
  });
}

export interface CycleScorecard {
  available: boolean;
  measures: { name: string; formula: string; target: string; value: string; details: string[]; passed: boolean | null }[];
  issues: { id: string; summary: string; expected: Outcome; found: boolean }[];
  caveat: string;
}

export function useCycleScorecard() {
  return useQuery({ queryKey: ["cycle-scorecard"], queryFn: () => getJson<CycleScorecard>("/api/monitoring/scorecard") });
}

export function fileUrl(document: string): string {
  return `/api/monitoring/files/${document.split("/").map(encodeURIComponent).join("/")}`;
}

/** A finding's outcome as it stands: the analyst's decision, or the rule's, or nothing yet. */
export function outcomeOf(finding: Finding, session: CycleSession | undefined): Outcome | null {
  return session?.decisions[finding.id] ?? null;
}

export function facilityName(cycle: Cycle, id: string): string {
  return id
    .split(",")
    .map((part) => cycle.facilities.find((f) => f.id === part)?.name.split(" ")[0] ?? part)
    .join(" and ");
}
