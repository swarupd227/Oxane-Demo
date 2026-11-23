import { useQuery } from "@tanstack/react-query";
import { useSession } from "./session";
import { CASE_HOME } from "./scenes";

export type Stage = "Intake" | "Interpretation" | "Clarification" | "QC" | "Live";

export interface CaseSummary {
  number: string;
  client: string;
  facility: string;
  deal_type: string;
  stage: Stage;
  limit_usd: number | null;
  owner: string;
  opened: string;
  stage_entered: string | null;
  went_live: string | null;
  target_go_live: string | null;
  business_days_open: number;
  business_days_in_stage: number | null;
  records: number;
  pool_balance: number | null;
  documents: { expected: number; received: number };
  terms: { total: number; extracted: number; approved: number };
  rules: number;
  exceptions: { total: number; open: number };
  queries: { total: number; with_client: number };
  qc_variances_open: number;
  last_activity: string | null;
  active: boolean;
  parent: string | null;
  backbook?: string;
  file?: string;
  columns?: { matched: number; total: number };
}

export interface Pipeline {
  as_of: string;
  stages: Stage[];
  team: { initials: string; name: string }[];
  cases: CaseSummary[];
  summary: {
    cases: number;
    by_stage: Record<Stage, number>;
    clients: number;
    open_exceptions: number;
    queries_with_client: number;
    qc_variances_open: number;
    pool_balance: number;
  };
}

export function useCases() {
  // The active case's stage moves with each recorded action.
  const { state } = useSession();
  return useQuery({
    queryKey: ["cases", state.audit.length, state.chainHead],
    queryFn: async (): Promise<Pipeline> => {
      const response = await fetch("/api/cases", { signal: AbortSignal.timeout(20_000) });
      if (!response.ok) {
        throw new Error(`Cases request failed with ${response.status}`);
      }
      return response.json();
    },
    placeholderData: (previous) => previous,
  });
}

export function casePath(item: CaseSummary): string {
  return item.active ? CASE_HOME : `/cases/${item.number}`;
}

export const STAGE_TONES: Record<Stage, string> = {
  Intake: "bg-sand text-muted",
  Interpretation: "bg-info-tint text-info",
  Clarification: "bg-warn-tint text-warn",
  QC: "bg-[#ece4f5] text-[#5a3d84]",
  Live: "bg-ok-tint text-ok",
};

export function ownerName(pipeline: Pipeline | undefined, initials: string): string {
  return pipeline?.team.find((member) => member.initials === initials)?.name ?? initials;
}
