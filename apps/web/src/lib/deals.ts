/* New deals, hand-offs and the client portal. Every figure comes from the API. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export class ApiError extends Error {
  status: number;
  fields: Record<string, string>;
  constructor(status: number, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return response.json() as Promise<T>;
  }
  let detail: unknown = response.statusText;
  try {
    detail = (await response.json()).detail;
  } catch {
    /* not JSON */
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const d = detail as { message: string; fields?: Record<string, string> };
    throw new ApiError(response.status, d.message, d.fields ?? {});
  }
  throw new ApiError(response.status, typeof detail === "string" ? detail : `Request failed (${response.status})`);
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  return parse<T>(await fetch(path, init));
}

export function post<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  return api<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function upload<T>(path: string, file: File, params: Record<string, string>): Promise<T> {
  const query = new URLSearchParams({ name: file.name, ...params });
  return api<T>(`${path}?${query}`, { method: "POST", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
}

export interface WorkItem {
  id: number;
  ref: string;
  kind: string;
  title: string;
  detail: string;
  role: string;
  role_label: string;
  assignee: string | null;
  assignee_name: string;
  from: string | null;
  from_name: string;
  link: string;
  status: string;
  subject: string;
  created_at: string;
  due_at: string;
  overdue: boolean;
  age_hours: number;
  done_at: string | null;
  done_by_name: string;
  note: string | null;
}

export interface MyWork {
  waiting: WorkItem[];
  handed_off: WorkItem[];
  done: WorkItem[];
  team: { persona: string; name: string; open: number }[] | null;
}

export function useWork(enabled = true) {
  return useQuery({
    queryKey: ["work"],
    queryFn: () => api<MyWork>("/api/work"),
    refetchInterval: 15_000,
    enabled,
  });
}

export interface DealsStatus {
  access_configured: boolean;
  live_available: boolean;
  mode: "live" | "replay" | "stub";
  spent_today_usd: number;
  cap_usd: number;
  cap_reached: boolean;
  /** The key in use passed (true) or failed (false) its last connection test; null if untested. */
  key_ok?: boolean | null;
  max_upload_mb: number;
  upload_types: string[];
}

export function useDealsStatus() {
  return useQuery({ queryKey: ["deals-status"], queryFn: () => api<DealsStatus>("/api/deals/status"), refetchInterval: 30_000 });
}

export interface AuditEntry {
  at: string;
  actor: string;
  type: string;
  action: string;
  reason?: string | null;
  hash: string;
  seq: number;
}
export interface History {
  entries: AuditEntry[];
  chain_intact: boolean;
}

export interface ClientRow {
  id: number;
  ref: string;
  name: string;
  short_name: string;
  contact_name: string;
  ai_permitted: boolean;
  approval_levels: number;
  master_field_overrides: Record<string, string>;
  created_at: string;
  archived_at: string | null;
  cases: boolean;
}

export interface ClientDetail extends ClientRow {
  case_list: CaseSummary[];
  facility_list: FacilitySummary[];
  mappings: { signature: string; headers: string[]; columns: Record<string, string | null>; updated_at: string }[];
  history: History;
}

export interface CaseSummary {
  id: number;
  ref: string;
  facility_name: string;
  client: { id: number; name: string; ai_permitted: boolean };
  deal_type: string;
  commitment_cents: number;
  stage: string;
  created_by: string;
  created_at: string;
  archived_at: string | null;
  documents: number;
  terms: { approved: number; total: number };
  exceptions_open: number;
  exceptions_total: number;
  queries_with_client: number;
  pool_cents: number | null;
  facility_id: number | null;
}

export interface DocumentRow {
  id: number;
  ref: string;
  name: string;
  kind: string;
  kind_source: string;
  version: number;
  effective_date: string | null;
  sha256: string;
  size: number;
  status: string;
  uploaded_by: string;
  uploaded_at: string;
}

export interface Term {
  key: string;
  label: string;
  tier: 1 | 2 | 3;
  unit: string;
  value: string | null;
  typed: unknown;
  status: "proposed" | "approved" | "missing" | "absent";
  source: "ai" | "analyst";
  doc_name?: string;
  page?: number | null;
  clause?: string | null;
  quote?: string | null;
  verified: boolean;
  problem: string | null;
  confidence: "high" | "medium" | "low" | "manual" | null;
  note?: string | null;
  effective_from?: string | null;
  original?: { value: string; doc_name: string; page: number | null; quote: string; verified: boolean } | null;
  basis_days?: number | null;
  window_months?: number | null;
  approved_by?: string;
  edited?: { from: string | null; reason: string; by: string };
  absent_reason?: string;
}

export interface TestSpec {
  kind: string;
  field: string;
  low?: number | null;
  high?: number | null;
  values?: string[];
}

export interface Rule {
  id: string;
  ref: string;
  plain_english: string;
  clause_text: string;
  document: string;
  page: number | null;
  verified: boolean;
  problem: string | null;
  describe: string;
  source: string;
  test?: TestSpec;
  where?: TestSpec | null;
  group_by?: string | null;
  limit_pct?: number;
  effective_from?: string | null;
  edited?: { reason: string; by: string };
}

export interface MappingCheck {
  column: string | null;
  field: string | null;
  problem: string | null;
  sample: string;
}

export interface Mapping {
  tape_doc: number;
  headers: string[];
  columns: Record<string, string | null>;
  status_map: Record<string, string>;
  source: "stored" | "ai" | "rules" | "facility";
  confirmed: boolean;
  confirmed_by?: string;
  checks: MappingCheck[];
  status_values?: string[];
  changed_columns?: string[];
}

export interface ValidationCheck {
  id: string;
  family: string;
  severity: "blocking" | "warning";
  text: string;
  checked: number;
  failed: number;
  examples: { key: string; value: string; row: number }[];
}

export interface EngineView {
  loans: number;
  gross_pool_cents: number;
  eligible_pool_cents: number;
  eligible_loans: number;
  excess_cents: number;
  advance_rate_pct: string;
  advance_rate_source: string;
  reserve_cents: number;
  borrowing_base_cents: number;
  availability_cents: number;
  facility_limit_cents: number;
  run_digest: string;
  rules: { id: string; status: string; failed: number; failed_cents: number; loans: string[] }[];
  concentrations: { id: string; active: boolean; limit_pct: string; largest: string; largest_cents: number; share_pct: string; excess_cents: number }[];
  delinquency_pct: string | null;
  metrics: Record<string, string>;
  independent_eligible_cents: number;
}

export interface Validation {
  as_of: string;
  rows: number;
  collapsed_duplicates: string[];
  checks: ValidationCheck[];
  unknown_statuses: string[];
  held: boolean;
  excluded: string[];
  engine?: EngineView;
}

export interface CaseException {
  key: string;
  ref: string;
  type: string;
  severity: "blocking" | "warning" | "info";
  title: string;
  detail: string;
  suggested: string;
  link: string;
  status: "open" | "accepted" | "resolved" | "with_client" | "answered" | "with_expert" | "decided";
  history: { at: string; by: string; action: string; note: string }[];
  query?: { text: string; sent_at: string; by: string };
  answer?: { text: string; at: string; by: string };
  escalation?: { text: string; at: string; by: string };
  decision?: { text: string; at: string; by: string };
  raised_at: string;
}

export interface CaseState {
  terms?: Record<string, Term>;
  rules?: { eligibility: Rule[]; concentration: Rule[]; not_codable: string[]; status: string; version: number; approved_by?: string };
  mapping?: Mapping;
  validation?: Validation;
  exceptions?: CaseException[];
  client_model?: { term: string; label: string; cell: string; model: string; agreed: string; differs: boolean; document: string }[];
  qc?: { status: "pending" | "passed" | "returned"; submitted_by: string; completed_by?: string; marks: Record<string, { result: string; note: string | null; by: string }> };
  approved_at?: string;
  approved_by?: string;
  live_at?: string;
  classified?: Record<string, { kind: string; title: string; dated: string | null }>;
  as_of?: string;
}

export interface CaseView extends Omit<CaseSummary, "client"> {
  client: ClientRow;
  state: CaseState;
  documents_list: DocumentRow[];
  readiness: Record<string, boolean>;
  qc_items: { id: string; label: string; value: string; source: string; quote: string | null; computed?: string }[];
  cost: { calls: number; live_calls: number; cost_usd: number; live_cost_usd: number; tokens: number };
  history: History;
  work: WorkItem[];
  can: Record<"prepare" | "ai" | "qc" | "review" | "expert" | "client", string | null>;
  stages: string[];
}

export interface FacilitySummary {
  id: number;
  ref: string;
  name: string;
  client: { id: number; name: string; ai_permitted: boolean; approval_levels: number };
  deal_type: string;
  commitment_cents: number;
  status: string;
  case_id: number | null;
  live_at: string | null;
  reporting_day: number | null;
  submissions: { id: number; ref: string; period: string; period_end: string; due_date: string; status: string }[];
  latest: { period: string; status: string; borrowing_base_cents: number | null; delinquency_average: string | null; delinquency_limit: string | null; breached: boolean; warning: boolean; open: number } | null;
}

export interface FacilityView extends FacilitySummary {
  config: { thresholds: { delinquency: { limit_pct: string; days: number; months: number; source: string } | null; loss: { limit_pct: string; source: string } | null }; rules: CaseState["rules"]; mapping: { headers: string[]; columns: Record<string, string | null> }; terms: Record<string, { value: string | null; source: string | null }> };
  case_ref: string | null;
  history: History;
  work: WorkItem[];
}

export interface Finding {
  key: string;
  ref: string;
  check: string;
  severity: "blocking" | "warning";
  title: string;
  detail: string;
  suggested: { outcome: string; reason: string; by: string };
  decision: { outcome: string; note: string | null; by: string; at: string; status: string; expert?: { text: string; by: string } } | null;
}

export interface SubmissionView {
  id: number;
  ref: string;
  period: string;
  period_label: string;
  period_end: string;
  due_date: string;
  status: string;
  state: {
    mapping?: Mapping;
    validation?: Validation;
    report_figures?: Record<string, { value: string; cents: number | null; page: number | null; quote: string | null; document: string; verified: boolean; source: string }>;
    reconciliation?: { prior_period: string; roll_forward: Record<string, number | string[] | null>; changes: { metric: string; prior: string; current: string; change: string; threshold: string; flagged: boolean }[] };
    tests?: Record<string, unknown> & { delinquency_months?: { period: string; value: string }[] };
    findings?: Finding[];
    report?: { text: string[]; drafted_by: string; approvals: { level: number; title: string; by: string; at: string }[]; released_at: string | null };
    excluded_rows?: string[];
  };
  facility: FacilitySummary;
  documents: DocumentRow[];
  levels: { level: number; role: string; title: string }[];
  next_level: { level: number; role: string; title: string } | null;
  cost: CaseView["cost"];
  history: History;
  work: WorkItem[];
  can: Record<"prepare" | "ai" | "approve" | "expert", string | null>;
}

export const useClients = () => useQuery({ queryKey: ["deals", "clients"], queryFn: () => api<ClientRow[]>("/api/deals/clients") });
export const useClient = (id: number) =>
  useQuery({ queryKey: ["deals", "client", id], queryFn: () => api<ClientDetail>(`/api/deals/clients/${id}`) });
export const useDealCases = (enabled = true) =>
  useQuery({ queryKey: ["deals", "cases"], queryFn: () => api<CaseSummary[]>("/api/deals/cases"), enabled });
export const useDealCase = (id: number) =>
  useQuery({ queryKey: ["deals", "case", id], queryFn: () => api<CaseView>(`/api/deals/cases/${id}`) });
export const useFacilities = (enabled = true) =>
  useQuery({ queryKey: ["deals", "facilities"], queryFn: () => api<FacilitySummary[]>("/api/deals/facilities"), enabled });
export const useFacility = (id: number) =>
  useQuery({ queryKey: ["deals", "facility", id], queryFn: () => api<FacilityView>(`/api/deals/facilities/${id}`) });
export const useSubmission = (id: number) =>
  useQuery({ queryKey: ["deals", "submission", id], queryFn: () => api<SubmissionView>(`/api/deals/submissions/${id}`) });

/** Run one action and refresh what it may have changed. */
export function useDealAction<T>() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (fn: () => Promise<T>) => fn(),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["deals"] });
      void client.invalidateQueries({ queryKey: ["work"] });
      void client.invalidateQueries({ queryKey: ["deals-status"] });
    },
  });
}

export const STAGE_LABEL: Record<string, string> = {
  documents: "Documents",
  terms: "Terms",
  rules: "Rules",
  mapping: "Mapping",
  validation: "Validation",
  exceptions: "Exceptions",
  qc: "Independent QC",
  review: "Awaiting approval",
  approved: "Approved",
  live: "Live",
};

export const KIND_LABEL: Record<string, string> = {
  auto: "Detect",
  agreement: "Agreement",
  amendment: "Amendment",
  loan_tape: "Loan tape",
  servicer_report: "Servicer report",
  client_model: "Client model",
  other: "Other",
};

export function usd(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) {
    return "–";
  }
  return `US$${(cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
