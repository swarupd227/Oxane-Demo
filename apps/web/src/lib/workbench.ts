import { useMutation, useQuery } from "@tanstack/react-query";
import { useSession } from "./session";

export interface Rect {
  x0: number;
  x1: number;
  top: number;
  bottom: number;
}

export interface Citation {
  document: string;
  page: number;
  rects: Rect[];
  label?: string;
  note?: string;
}

export interface DocumentInfo {
  id: string;
  file: string;
  title: string;
  kind: string;
  dated: string | null;
  version: string;
  effective: string | null;
  size: string;
  note?: string;
  links_to?: string;
}

export type Confidence = "high" | "medium" | "low" | "none";
export type TermStatus = "approved" | "review" | "missing";

export interface Term {
  name: string;
  tier: 1 | 2 | 3;
  value: string;
  confidence: Confidence;
  status: TermStatus;
  clause: string;
  document: string;
  source: Citation | null;
  also_cited: Citation[];
  original_value?: string;
  amended_value?: string;
  effective_from?: string;
  grounding?: Grounding;
}

/** The ontology concept a value belongs to, and the concepts the model said it relied on. */
export interface Grounding {
  concept: {
    id: string;
    label: string;
    meaning: string;
    layer?: string;
    relations: { type: string; target: string }[];
  };
  cited: string[];
}

export interface Rule {
  id: string;
  group: "eligibility" | "concentration";
  plain_english: string;
  clause_ref: string;
  clause_text: string;
  logic: string;
  threshold: number | null;
  status: "ready" | "not_evaluated";
  effective_from?: string | null;
  concepts?: string[];
}

export interface MappingRow {
  column: string;
  field: string;
  confidence: "high" | "medium" | "low";
  sample: string;
  note: string | null;
  concept?: string | null;
}

export interface Requirement {
  name: string;
  status: "met" | "calculated" | "derived";
  detail: string;
}

export interface ExceptionItem {
  id: string;
  term?: string;
  type: "missing" | "conflicting" | "ambiguous";
  label: string;
  title: string;
  owner: string;
  where: string;
  evidence: string[];
  suggestion: string;
  actions: ("accept" | "query" | "escalate")[];
  tier1?: boolean;
  blocking?: boolean;
  recalculates?: boolean;
  drill?: string;
  source?: Citation | null;
}

export interface Workbench {
  seed: boolean;
  usage?: { model: string; calls: number; cost_usd: number };
  period_end: string;
  documents: DocumentInfo[];
  missing_documents: { name: string; reason: string }[];
  terms: Term[];
  rules: Rule[];
  mapping: {
    rows: MappingRow[];
    requirements: Requirement[];
    dates: { mixed_rows: number; uncertain: number; method: string };
  };
  exceptions: ExceptionItem[];
}

export interface LoanRow {
  loan_id: string;
  balance: number;
  days_past_due: number;
  status: string;
  fico: number;
  state: string;
  dealer: string;
  vin: string;
  vehicle: string;
  rules_failed: string[];
}

export interface BridgeLine {
  rule_id: string;
  label: string;
  loans: number;
  amount: number;
  rows: LoanRow[];
}

export interface Figures {
  gross_pool: number;
  eligible_pool: number;
  excess: number;
  advance_rate_pct: number;
  reserve: number;
  borrowing_base: number;
  outstanding: number;
  availability: number;
}

export interface CovenantTest {
  name: string;
  clause: string;
  value: number;
  limit: number;
  passed: boolean;
  formula: string;
}

export interface RunResult {
  digest: string;
  provisional: boolean;
  not_evaluated: string[];
  dealer_match: boolean;
  system: Figures;
  borrower: Figures;
  pool_bridge: {
    borrower: number;
    system: number;
    gap: number;
    unexplained: number;
    reproduces_certificate: boolean;
    lines: BridgeLine[];
  };
  base_bridge: {
    borrower: number;
    system: number;
    lines: { label: string; amount: number }[];
  };
  rules: { id: string; label: string; status: string; failed: number; failed_amount: number }[];
  concentrations: {
    id: string;
    label: string;
    largest: string;
    share_pct: number;
    limit_pct: number;
    excess: number;
    active: boolean;
  }[];
  covenants: {
    tests: CovenantTest[];
    leverage_without_carve_out: number;
    delinquency: {
      monthly_pct: number[];
      average_pct: number;
      trigger_pct: number;
      tripped: boolean;
    };
  };
  weighted_average_apr: number;
}

export interface RulePreview {
  newly_ineligible: number;
  newly_eligible: number;
  eligible_pool_change: number;
  borrowing_base_change: number;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }
  return response.json();
}

export function useWorkbench() {
  return useQuery({
    queryKey: ["workbench"],
    queryFn: async (): Promise<Workbench> => {
      // Long enough for a cold API, short enough never to leave a skeleton on stage.
      const response = await fetch("/api/workbench", { signal: AbortSignal.timeout(20_000) });
      if (!response.ok) {
        throw new Error(`Workbench request failed with ${response.status}`);
      }
      return response.json();
    },
    staleTime: Infinity,
  });
}

export function useValidationRun(dealerMatch: boolean, enabled: boolean) {
  // An approved rule change alters every run, so it has to be part of the cache key.
  const { state } = useSession();
  const rule = state.ruleEdit?.status === "approved" ? state.ruleEdit.to : null;
  return useQuery({
    queryKey: ["run", dealerMatch, rule],
    queryFn: () => post<RunResult>("/api/run", { dealer_match: dealerMatch }),
    enabled,
    staleTime: Infinity,
    placeholderData: (previous) => previous,
  });
}

export function useRulePreview() {
  return useMutation({
    mutationFn: (input: { rule_id: string; value: number }) =>
      post<RulePreview>("/api/rules/preview", input),
  });
}

export function packUrl(file: string): string {
  return `/api/pack/${encodeURIComponent(file)}`;
}
