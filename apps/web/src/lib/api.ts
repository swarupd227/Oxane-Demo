import { useQuery } from "@tanstack/react-query";

export type CaseStatus =
  | "awaiting_pack"
  | "in_review"
  | "approved"
  | "approved_with_open_items";

export type LlmMode = "replay" | "record" | "live";

export interface Deal {
  case: { number: string; target_go_live: string | null };
  lender: { name: string; short_name: string; desk: string };
  borrower: { name: string; short_name: string; parent: string; description: string };
  facility: {
    type: string;
    short_type: string;
    limit_usd: number;
    collateral: string;
    first_tape_loans: number;
  };
  pricing: { margin: string; unused_fee: string };
  dates: { label: string; date: string }[];
  oxane_role: { title: string; summary: string };
  analysts: { preparer: string; approver: string };
}

export interface CaseView {
  number: string;
  status: CaseStatus;
  llm_mode: LlmMode;
  deal: Deal;
}

// A stalled request must become a visible error, not an endless skeleton on stage.
const REQUEST_TIMEOUT_MS = 2500;

async function fetchCase(): Promise<CaseView> {
  const response = await fetch("/api/case", { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  if (!response.ok) {
    throw new Error(`Case request failed with ${response.status}`);
  }
  return response.json();
}

export function useCase() {
  return useQuery({ queryKey: ["case"], queryFn: fetchCase });
}
