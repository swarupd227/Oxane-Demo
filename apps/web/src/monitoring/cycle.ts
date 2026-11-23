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
export type FacilityId = "bramble" | "northmoor" | "kestrel" | "larkspur" | "ravenglass" | "wharfedale";
export type ClientId = "calderwood" | "thornbury";

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
  client: ClientId;
  client_name: string;
  ai_permitted: boolean;
}

export interface Person {
  name: string;
  role: string;
}

export interface Override {
  field: string;
  default: string;
  override: string;
  reason: string;
}

export interface Client {
  id: ClientId;
  name: string;
  ai_permitted: boolean;
  ai_note?: string;
  contact: Person;
  client_contact: Person;
  status_call: string;
  approval_levels: { level: number; actor: CycleActor; title: string }[];
  master_field_overrides?: Override[];
}

export interface Chase {
  at: string;
  action: string;
  to: string;
  text: string;
}

export interface Submission {
  ref: string;
  facility: string;
  label: string;
  file: string | null;
  due: string;
  received: string | null;
  status: "received" | "late" | "received_late" | "awaited" | "reused";
  sender?: string;
  chase: Chase[];
  channel: "Email" | "SFTP" | "API" | "Data room" | "Upload";
  internal_deadline: string;
  deadline_status: "met" | "missed" | "at_risk";
  client: ClientId;
  reused: { from: string; note: string; consent: string } | null;
}

export interface RuleRow {
  id: string;
  family: string;
  family_name: string;
  severity: "blocking" | "warning";
  text: string;
  field: string;
  checked: number;
  failed: number;
  status: "passed" | "warning" | "blocking" | "n/a";
  examples: { key: string; value: string; row: number }[];
}

export interface ChangeRow {
  id: string;
  metric: string;
  label: string;
  text: string;
  prior: number;
  current: number;
  change: number;
  basis: "pct" | "abs";
  limit: number;
  flagged: boolean;
}

export interface Explanation {
  explained: boolean;
  cause: string;
  quote: string;
  document: string;
  source: Source | null;
  figures: Record<string, string>;
  verified: boolean;
  by: "AI";
}

export interface Feed {
  facility: FacilityId;
  file: string;
  kind: string;
  sha256: string;
  rows_in_file: number;
  rows_loaded: number;
  rules: RuleRow[];
  prior_period: ChangeRow[];
  held: boolean;
  resolution: { rule: string; proposed: string; collapsible: boolean; collapsed: string[] } | null;
  explanation: Explanation | null;
  month?: string;
  price_file?: string;
}

export interface MappingFeed {
  facility: FacilityId;
  client: ClientId;
  file: string;
  sha256: string;
  rows: number;
  columns_total: number;
  from_memory: number;
  layout: "changed" | "unchanged";
  stored: string;
  ai_used: boolean;
  fields: { column: string; master_field: string; entity: string; new?: boolean }[];
  entities: Record<string, number>;
  overrides: Override[];
}

export interface QcLine {
  line: string;
  unit: string;
  platform: number | string | null;
  qc: number | string | null;
  class: "agrees" | "blank" | "rounding" | "sign" | "percent" | "genuine";
  label: string;
  cell: string;
}

export interface HeadroomRow {
  facility: string;
  test: string;
  clause: string;
  value: number;
  limit: number;
  direction: "max" | "min";
  unit: string;
  headroom: number;
  used_pct: number;
  passed: boolean;
  early_warning: boolean;
  trend: "towards" | "away" | "flat";
  series: { period: string; value: number }[];
  note: string;
  source: Source | null;
}

export interface AlertRule {
  facility: FacilityId;
  metric: string;
  operator: string;
  threshold: number;
  unit: string;
  label: string;
}

export interface AlertDraft {
  request: string;
  client: ClientId;
  drafted: { understood: boolean; metric: string; operator: string; threshold: string; summary: string; concepts: string[]; question: string };
  rule: AlertRule | null;
  valid: boolean;
  problems: string[];
  back_test: { period: string; value: number; fires: boolean }[];
  fires: number;
  by: "AI";
}

export interface Brief {
  client: ClientId;
  ai: boolean;
  opening: string;
  sections: { heading: string; points: string[]; by?: "AI" | "Template" | "Code"; pending_recording?: boolean }[];
  figures: Record<string, PackFigure>;
  unknown_placeholders: string[];
  numbers_in_text: string[];
}

/** The status-call summary written to the client, by code; it reaches the portal once released. */
export interface ClientSummary {
  client: ClientId;
  title: string;
  greeting: string;
  opening: string;
  sections: { heading: string; points: string[] }[];
  figures: Record<string, PackFigure>;
  week_of: string;
}

export interface Position {
  loanx: string;
  cusip: string;
  issuer: string;
  facility: string;
  par: number;
  spread_bps: number;
  maturity: string;
  moodys: string;
  sp: string;
  industry: string;
  ccc: boolean;
  in_excess: boolean;
  bid: number;
  prior_bid: number | null;
  prior_rating: string[] | null;
}

export interface Larkspur {
  basis: string;
  override: Override | null;
  determination_date: string;
  positions_file: string;
  prices_file: string;
  positions: Position[];
  borrowing_base: {
    total_par: number;
    ccc_par: number;
    ccc_pct: number;
    ccc_limit_pct: number;
    ccc_limit: number;
    ccc_excess: number;
    excess: { loanx: string; issuer: string; par_in_excess: number; bid: number; haircut: number }[];
    haircut: number;
    adjusted: number;
    advance_rate_pct: number;
    borrowing_base: number;
    commitment: number;
    drawn: number;
    availability: number;
    passed: boolean;
  };
  april: { ccc_pct: number; haircut: number; borrowing_base: number; availability: number; total_par: number };
  moodys_only: { ccc_pct: number; passed: boolean; haircut: number };
  changes: {
    sold: string[];
    bought: string[];
    relinked: { old_loanx: string; new_loanx: string; old_cusip: string; new_cusip: string; issuer: string; matched_on: string[] }[];
    unexplained_gone: string[];
    unexplained_new: string[];
  };
  trades: { trade_date: string; direction: string; loanx: string; issuer: string; par: number; price: number }[];
  par_roll: { opening: number; sold: number; bought: number; expected: number; closing: number; gap: number };
  downgrades: { loanx: string; issuer: string; before: string[]; after: string[]; notches: number; into_ccc: boolean }[];
  price_moves: { loanx: string; issuer: string; before: number; after: number; change: number }[];
  price_move_limit: number;
  clauses: Source[];
  ccc_source: Source | null;
  warning_source: Source | null;
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
  ref: string;
  raised: string;
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
  blocking?: boolean;
  explanation?: Explanation;
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
  ai?: boolean;
  pending_recording?: boolean;
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

/** One obligor of the middle-market facility, as code tested it. */
export interface Obligor {
  id: string;
  name: string;
  sector: string;
  sponsor: string;
  facility: string;
  outstanding: number;
  advance_rate: number;
  received: boolean;
  received_on: string | null;
  financials_file: string | null;
  certificate_file: string | null;
  layout: string | null;
  certificate_layout: string | null;
  basis: "extracted" | "portfolio_report";
  stale: boolean;
  financials_as_of: string;
  ebitda_k: number;
  addbacks_k: number;
  covenant_ebitda_k: number;
  net_debt_k: number;
  interest_k: number;
  leverage: number;
  reported_leverage: number | null;
  leverage_difference: number | null;
  within_tolerance: boolean | null;
  max_leverage: number;
  max_leverage_basis: string;
  original_max_leverage: number;
  reported_max_leverage: number;
  icr: number;
  min_icr: number;
  leverage_passed: boolean;
  icr_passed: boolean;
  headroom: number;
  eligible: boolean;
  reason: string;
  addback_pct: number;
  addbacks_flagged: boolean;
  addback_items: { description: string; amount_k: number; kind: string; reason: string; source: Source | null }[];
  readings: { name: string; covenant_ebitda_k: number; leverage: number; passed: boolean }[];
  sources: Record<string, Source | null>;
}

export interface Ravenglass {
  quarter_end: string;
  determination_date: string;
  portfolio_file: string;
  certificate_file: string;
  obligors: Obligor[];
  received: number;
  covenant_changes: { obligor: string; covenant: string; old_value: string; new_value: string; test_dates: string[]; effective_from: string; document: string; source: Source | null; verified: boolean; by: string }[];
  extraction: { status: "recorded" | "pending" | "partial"; batches: number; batches_read: number; obligors_read: number; verified: number };
  borrowing_base: {
    aggregate: number;
    eligible: number;
    excluded: { obligor: string; name: string; reason: string; outstanding: number; value: number }[];
    single_limit: number;
    sector_limit: number;
    excess_reduction: number;
    largest: { obligor: string; name: string; pct: number };
    largest_sector: { sector: string; pct: number };
    single_limit_pct: number;
    sector_limit_pct: number;
    borrowing_base: number;
    commitment: number;
    drawn: number;
    availability: number;
    certificate: { aggregate: number; eligible: number; borrowing_base: number; availability: number };
    difference: number;
    bridged: number;
    sensitivity: { obligor: string; name: string; if_excluded: number }[];
    passed: boolean;
  };
  layouts: Record<string, number>;
  clauses: Source[];
  cap_pct: number;
  tolerance_x: number;
}

export interface InvestorRow {
  id: string;
  name: string;
  type: string;
  commitment: number;
  called: number;
  register_uncalled: number;
  prior_uncalled: number;
  call: number;
  recallable: number;
  expected_uncalled: number;
  difference: number;
  uncalled: number;
  rating: string;
  prior_rating: string;
  rating_date: string;
  register_designation: string;
  class: "Included" | "Designated" | "Excluded";
  prior_class: string;
  reason: string;
  exclusion_event: boolean;
  counted: number;
  excess: number;
  share_pct: number;
}

export interface SubBase {
  aggregate_eligible_uncalled: number;
  single_limit: number;
  concentration_excess: Record<string, number>;
  concentration_reduction: number;
  designated: number;
  designated_limit: number;
  designated_excess: number;
  designated_pct: number;
  borrowing_base: number;
  availability: number;
  prepayment: number;
}

export interface NoticeView {
  file: string;
  number: number;
  date: string;
  total: number;
  pct: number;
  recallable?: number;
  sum_difference: number;
  reconciles: boolean;
  lines: { investor: string; name: string; amount: number; expected: number; difference: number }[];
}

export interface Wharfedale {
  determination_date: string;
  register_file: string;
  investors: InvestorRow[];
  classes: Record<string, number>;
  commitments: number;
  uncalled: number;
  exclusions: InvestorRow[];
  unapplied: string[];
  borrowing_base: SubBase & { commitment: number; drawn: number; advance_rates: Record<string, number>; single_limit_pct: number; designated_limit_pct: number; passed: boolean };
  before_exclusion: SubBase;
  largest: { id: string; name: string; share_pct: number; excess: number };
  notices: { capital_call: NoticeView & { due: string }; distribution: NoticeView & { recallable_pct: number } };
  register_breaks: InvestorRow[];
  clauses: Source[];
}

export interface DailyFeed {
  feed: "positions" | "prices" | "ratings";
  document: string;
  channel: string;
  format: string;
  due: string;
  days: { as_of: string; deadline: string; received_at: string | null; status: "on_time" | "late" | "missing"; minutes_late: number; rows: number; file: string | null }[];
  expected: number;
  received: number;
  late: string[];
  missing: string[];
}

export interface DailyFeeds {
  facility: string;
  folder: string;
  business_days: number;
  feeds: DailyFeed[];
  coverage: { as_of: string; positions: number; priced: number; unpriced: number; price_file: boolean }[];
  rating_changes: { as_of: string; loanx: string; issuer: string; agency: string; previous: string; current: string; file: string }[];
  expected: number;
  received: number;
}

export interface ScheduleLine {
  document: string;
  format: string;
  frequency: string;
  channel: string;
  due: string;
  internal: string;
  status: "complete" | "late" | "missing" | "not_due" | "not_applicable" | "summary_only";
  expected: number;
  received: number;
  late: number;
  missing?: number;
  note: string;
}

export interface LibraryEntry {
  id: string;
  document: string;
  sender: string;
  format: string;
  client: ClientId;
  facilities: string[];
  facility_names: string[];
  columns: number | null;
  signature: string | null;
  count: number;
  unit: string;
  obligors: string[];
  version: number;
  last_changed: string;
  changed_by: string;
  versions: { version: number; date: string; by: string; change: string }[];
}

export interface PendingStep {
  task: string;
  facility: string;
  subject: string;
}

/** A facility in the rest of the book: summary figures only, every test worked out by code. */
export interface BookFacility {
  id: string;
  name: string;
  borrower: string;
  client: ClientId;
  client_name: string;
  ai_permitted: boolean;
  type: string;
  asset_class: string;
  role: string;
  size: string;
  commitment: number;
  drawn: number;
  reporting: string;
  period: string;
  analyst: string;
  documents: { received: number; total: number; late: number };
  tests: Pick<HeadroomRow, "test" | "clause" | "value" | "limit" | "unit" | "direction" | "headroom" | "passed" | "early_warning" | "trend">[];
  trend: { label: string; unit: string; limit: number; direction: "max" | "min"; series: { period: string; value: number }[] };
  report: {
    status: "released" | "in_review" | "preparing";
    levels: number;
    done: number;
    prepared: { by: string; at: string } | null;
    approvals: { level: number; by: string; at: string }[];
    released_at: string | null;
  };
}

export interface Cycle {
  team: Record<CycleActor, { name: string; title: string }>;
  book: { facilities: BookFacility[]; submissions: Submission[]; headroom: HeadroomRow[] };
  cycle: { id: string; label: string; period_end: string; as_of: string };
  lender: string;
  desk: string;
  tolerances: { certificate_usd: number; roll_forward_usd: number; trigger_warning_pts: number };
  clients: Client[];
  facilities: Facility[];
  validation: { feeds: Feed[] };
  mapping: {
    feeds: MappingFeed[];
    memories: { client: ClientId; name: string; layouts: { facility: FacilityId; columns: number; kind: string }[] }[];
    entities: Record<string, string>;
    library: LibraryEntry[];
  };
  qc: Record<FacilityId, { file: string; lines: QcLine[]; agrees: number; presentation: number; genuine: string[] }>;
  headroom: HeadroomRow[];
  early_warnings: { facility: FacilityId; kind: string; subject: string; detail: string; source: Source | null }[];
  alerts: Record<
    ClientId,
    { ai_permitted: boolean; catalogue: Record<string, { label: string; unit: string }>; history: Record<string, [string, number][]>; presets: AlertDraft[] }
  >;
  briefs: Brief[];
  client_summaries?: ClientSummary[];
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
        system: {
          eligible_pool: number;
          excess: number;
          borrowing_base: number;
          availability: number;
          advance_rate_pct: number;
          provisional: boolean;
          gross_pool: number;
          ineligible: number;
          ineligible_loans: number;
        };
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
    larkspur: Larkspur;
    ravenglass: Ravenglass;
    wharfedale: Wharfedale;
  };
  daily_feeds: DailyFeeds;
  schedules: { facility: string; template: string; lines: ScheduleLine[] }[];
  pending_recording: PendingStep[];
  collateral: {
    checked: Record<FacilityId, number>;
    within: { vin: string; holdings: Holding[] }[];
    across: { vin: string; holdings: Holding[] }[];
    scope: string;
  };
  findings: Finding[];
  packs: LenderPack[];
  unverified: string[];
  usage: {
    model: string;
    calls: number;
    cost_usd: number;
    model_seconds: number;
    by_client: { client: ClientId; ai_permitted: boolean; calls: number; tokens: number; cost_usd: number }[];
  };
  llm_mode: LlmMode;
}

export interface CycleAudit {
  at: string;
  actor: string;
  role?: CycleActor;
  action: string;
  reason: string | null;
  type?: string;
  subject?: string | null;
  hash?: string;
}

export interface CycleSession {
  openedAt: string | null;
  layoutConfirmed: boolean;
  triage: Record<string, { outcome: Outcome; note: string | null; at: string; overrode: boolean }>;
  packs: Partial<Record<FacilityId, { at: string; by: string }>>;
  summaries?: Partial<Record<ClientId, { at: string; by: string }>>;
  blocks: Partial<Record<FacilityId, { note: string; at: string; by: string }>>;
  qcResolved: Partial<Record<FacilityId, Record<string, { note: string; at: string; by: string }>>>;
  approvals: Partial<Record<FacilityId, { level: number; title: string; by: string; actor: CycleActor; at: string }[]>>;
  alerts: {
    id: number;
    client: ClientId;
    request: string;
    rule: AlertRule | null;
    summary: string | null;
    fires: number | null;
    status: "requested" | "live";
    requestedAt: string;
    approvedAt?: string;
    approvedBy?: string;
  }[];
  levels: Record<FacilityId, { level: number; actor: CycleActor; title: string }[]>;
  held: Record<FacilityId, boolean>;
  qcOpen: Record<FacilityId, string[]>;
  provisional: Record<FacilityId, boolean>;
  events: number;
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

const TIMEOUT_MS = 15000;

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

export type CycleActor = "analyst" | "approver" | "senior" | "client";
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
  measures: {
    name: string;
    measured: { value: string; details: string[] };
    assumed: { value: string; details: string[] } | null;
    target: string;
    passed: boolean | null;
  }[];
  issues: { id: string; summary: string; expected: Outcome; found: boolean; facility: string }[];
  noise: { id: string; summary: string; raised: boolean }[];
  pending_recording?: PendingStep[];
  not_scored?: string[];
  assumptions: string;
  caveat: string;
}

export class DraftRefusal extends Error {}

export function useAlertDraft() {
  return useMutation({
    mutationFn: async ({ client, request }: { client: ClientId; request: string }) => {
      const response = await fetch("/api/monitoring/alerts/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client, request }),
      });
      const body = await response.json();
      if (!response.ok) {
        throw new DraftRefusal(body.detail ?? "The request could not be drafted.");
      }
      return body as AlertDraft;
    },
  });
}

export function workbookUrl(facility: FacilityId): string {
  return `/api/monitoring/workbook/${facility}.xlsx`;
}

/** Replace each {{placeholder}} with code's figure, for plain text. */
export function fillText(text: string, figures: Record<string, { value: string }>): string {
  return text.replace(/\{\{(\w+)\}\}/g, (match, key: string) => figures[key]?.value ?? match);
}

export function clientOf(cycle: Cycle, facility: string): Client | undefined {
  const owner = cycle.facilities.find((f) => f.id === facility)?.client;
  return cycle.clients.find((c) => c.id === owner);
}

export const FACILITY_ORDER: FacilityId[] = ["bramble", "northmoor", "kestrel", "larkspur", "ravenglass", "wharfedale"];

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
