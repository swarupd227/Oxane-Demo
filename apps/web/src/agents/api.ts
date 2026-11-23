import { useQuery } from "@tanstack/react-query";

export type AgentKind = "model" | "code";
export type TriggerKind = "event" | "schedule" | "request";
export type Outcome = "accepted" | "edited" | "rejected" | "quote_check_failed" | "refused" | "awaiting_review" | "pending_recording";

export interface Link {
  agent: string;
  hands_off: string;
}

export interface RunStats {
  runs: number;
  refused: number;
  outcomes: Record<Outcome, number>;
  tokens: number;
  cost_usd: number;
  duration_ms: number;
  decided: number;
  acceptance: number | null;
  last_at: string | null;
}

export interface Agent {
  id: string;
  name: string;
  kind: AgentKind;
  stage: string;
  purpose: string;
  tasks: string[];
  triggers: { kind: TriggerKind; label: string }[];
  inputs: string[];
  outputs: string[];
  upstream: Link[];
  downstream: Link[];
  constraints: string[];
  use_cases: Record<string, number[]>;
  pain_points: string[];
  asset_classes: { now: string[]; after_pilot: string[] };
  gateway_tasks: Record<string, string>;
  source: string[];
  prompt_version: { id: string; recordings: number } | null;
  stats: RunStats | null;
}

export interface Run {
  id: string;
  at: string;
  agent: string | null;
  task: string;
  client: string;
  workflow: string;
  ref: string;
  facility: string;
  subject: string;
  outcome: Outcome;
  note: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  duration_ms: number;
  model: string | null;
  source: "recorded" | "live";
}

export interface Registry {
  version: number;
  model: { name: string; effort: string };
  llm_mode: string;
  stages: { id: string; label: string }[];
  use_cases: Record<string, { label: string; steps: Record<string, string> }>;
  pain_points: { id: string; label: string; short: string }[];
  asset_classes: { id: string; label: string }[];
  constraints: Record<string, string>;
  outcomes: Record<Outcome, string>;
  clients: Record<string, { id: string; name: string; ai_permitted: boolean }>;
  agents: Agent[];
  totals: RunStats;
  by_client: Record<string, RunStats>;
  runs: Run[];
}

const TIMEOUT_MS = 30_000;

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!response.ok) {
    throw new Error(`${url} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function useAgents() {
  return useQuery({ queryKey: ["agents"], queryFn: () => getJson<Registry>("/api/agents") });
}

export function usd(value: number): string {
  if (value === 0) {
    return "US$0";
  }
  return `US$${value < 1 ? value.toFixed(4) : value.toFixed(2)}`;
}

export function pct(value: number | null): string {
  return value === null ? "–" : `${Math.round(value * 100)}%`;
}

export function seconds(ms: number): string {
  if (!ms) {
    return "–";
  }
  return ms >= 60_000 ? `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s` : `${(ms / 1000).toFixed(1)}s`;
}

export function tokens(value: number): string {
  return value >= 10_000 ? `${(value / 1000).toFixed(1)}k` : value.toLocaleString("en-US");
}
