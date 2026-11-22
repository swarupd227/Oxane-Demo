import { useQuery } from "@tanstack/react-query";
import { useSession } from "./session";
import type { Citation } from "./workbench";

export interface DefinitionRef {
  target: string;
  key: string;
  role: "input" | "context";
  status: "traced" | "not_in_pack" | "mentioned" | "untraced";
}

export interface Resolved {
  value: string;
  rule?: string;
  worked?: string;
  check?: boolean;
  alternative?: string;
}

export interface DefinitionNode {
  key: string;
  term: string;
  document: string;
  clause: string;
  quote: string;
  source: Citation | null;
  amended_by: string | null;
  amendment_quote: string | null;
  amendment_source: Citation | null;
  refers_to: DefinitionRef[];
  depth: number | null;
  resolved: Resolved | null;
}

export interface Definitions {
  roots: string[];
  nodes: DefinitionNode[];
  not_in_pack: string[];
  borrowing_base_reproduced: boolean;
  delinquency: { literal: number; without_repossessed: number };
  checks: {
    quotes: number;
    quotes_found: number;
    unverified: string[];
    amendment_quotes_unverified: string[];
    unresolved_references: string[];
    mentioned_only: string[];
    input_cycles: string[][];
    mutual_references: string[][];
  };
}

export interface ModelRow {
  topic: string;
  label: string;
  cell: string;
  quote: string;
  reading: string;
  agreement: string | null;
  clause: string | null;
  source: Citation | null;
  kind: "parameter" | "reporting";
  status: "agrees" | "differs" | "silent" | "adopted" | "not_compared";
  borrowing_base_change?: number;
  bucket_change?: number;
  availability_with_model?: number;
  impact?: string;
}

export interface TrackedQuery {
  id: string;
  source: string;
  topic: string | null;
  to: string;
  subject: string;
  text: string;
  figures: Record<string, { value: string; means: string }> | null;
  raised: string;
  sent: string | null;
  answered: string | null;
  closed: string | null;
  answer: string | null;
  answer_waiting: boolean;
  resolution: string | null;
  status: "drafted" | "with client" | "answered" | "closed";
  blocking: boolean;
  earlier: boolean;
  analyst_hours: number;
  waiting_hours: number;
}

export interface QcLine {
  line: string;
  unit: string;
  platform: number | null;
  qc: number | string | null;
  class: "agrees" | "blank" | "rounding" | "sign" | "percent" | "genuine";
  label: string;
  cell: string;
  difference?: number;
  explained_by?: { loans: number; label: string; amount: number; loan_ids: string[] } | null;
  resolution: { resolution: string; reason: string; at: string; by: string } | null;
}

export interface Threshold {
  id: string;
  rule: string | null;
  area: string;
  parameter: string;
  term?: string;
  value: string;
  engine: string;
  clause: string;
  quote: string | null;
  source: Citation | null;
  in_source: boolean;
  validated: boolean;
  change?: string;
  effective_from?: string | null;
}

export interface BackbookDifference {
  deal: string;
  column: string;
  kind: "unknown_column" | "blank_values" | "code_values";
  samples?: string[];
  absent_stored_columns?: string[];
  rows?: number;
  codes?: string[];
  suggestion: {
    kind: string;
    field: string | null;
    treat_blank_as: string | null;
    code_map: string[][];
    reason: string;
  } | null;
  check: { ok: boolean; evidence: string };
}

export interface BackbookDeal {
  id: string;
  name: string;
  deal_type: string;
  file: string;
  rows: number;
  columns: number;
  matched: number;
  stored: number;
  pool_balance: number;
  differences: BackbookDifference[];
  exceptions: number;
  clean: boolean;
  loaded: boolean;
  can_accept: boolean;
}

export interface Casework {
  usage: { model: string; calls: number; cost_usd: number };
  definitions: Definitions;
  client_model: {
    file: string;
    template_version: string;
    rows: ModelRow[];
    rejected: { cell: string; topic: string; reason: string }[];
  };
  tracker: {
    clock: string;
    pack_received: string;
    queries: TrackedQuery[];
    elapsed_hours: number;
    client_waiting_hours: number;
    analyst_hours: number;
    open_with_client: number;
    drafted: number;
  };
  qc: {
    file: string;
    lines: QcLine[];
    agrees: number;
    presentation: number;
    genuine: string[];
    open: string[];
    passed: boolean;
    status: "provisional" | "released";
    released_at: string | null;
    released_by: string | null;
    can_release: boolean;
    resolutions: string[];
  };
  config: {
    status: {
      label: string;
      final: boolean;
      prepared_by: string;
      approved_by: string | null;
      released: string | null;
      qc_passed: boolean;
    };
    thresholds: Threshold[];
    fields: {
      source: string;
      file: string;
      sample: string;
      field: string;
      meaning: string;
      transform: string;
      expected: string;
    }[];
    report: { line: string; value: number | null; unit: string; client_format: string }[];
    conventions: (ModelRow & { treatment: string })[];
    ruleset_digest: string;
  };
  backbook: BackbookDeal[];
}

export function useCasework() {
  // Every recorded action can change the tracker, QC status or backbook, so refetch on each.
  const { state } = useSession();
  return useQuery({
    queryKey: ["casework", state.audit.length, state.chainHead],
    queryFn: async (): Promise<Casework> => {
      const response = await fetch("/api/casework", { signal: AbortSignal.timeout(20_000) });
      if (!response.ok) {
        throw new Error(`Casework request failed with ${response.status}`);
      }
      return response.json();
    },
    placeholderData: (previous) => previous,
  });
}

export function caseworkFileUrl(name: string): string {
  return `/api/casework/files/${encodeURIComponent(name)}`;
}

const stamp = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

/** Sandbox clock times are naive local times; show them as written. */
export function formatStamp(iso: string | null): string {
  return iso ? stamp.format(new Date(`${iso.slice(0, 19)}Z`)) : "";
}

export const usd2 = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
