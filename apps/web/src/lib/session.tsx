/* The analyst's session lives on the server. Controls are enforced there, not in this file. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Term, Workbench } from "./workbench";

export type Actor = "analyst" | "approver";
export type ExceptionOutcome = "accepted" | "queried" | "escalated";

export interface AuditEntry {
  at: string;
  actor: string;
  action: string;
  reason?: string | null;
  earlier?: boolean;
}

export interface RuleEdit {
  rule_id: string;
  from: number;
  to: number;
  reason: string;
  status: "pending" | "declined";
  decline_reason?: string;
}

export interface SessionState {
  startedAt: string | null;
  actor: Actor;
  intakeDone: boolean;
  termApprovals: Record<string, "approved" | "queued">;
  termEdits: Record<string, string>;
  mappingAccepted: boolean;
  ran: boolean;
  dealerMatched: boolean;
  exceptions: Record<string, ExceptionOutcome>;
  ruleEdit: RuleEdit | null;
  approvedAt: string | null;
  approvedBy: string | null;
  audit: AuditEntry[];
  readiness: {
    tier1_approved: boolean;
    exceptions_worked: boolean;
    run_complete: boolean;
    no_rule_pending: boolean;
  };
  openItems: string[];
  chainIntact: boolean;
  chainHead: string;
}

export const ANALYST = "Onboarding analyst";
export const APPROVER = "Second analyst";

const initial: SessionState = {
  startedAt: null,
  actor: "analyst",
  intakeDone: false,
  termApprovals: {},
  termEdits: {},
  mappingAccepted: false,
  ran: false,
  dealerMatched: false,
  exceptions: {},
  ruleEdit: null,
  approvedAt: null,
  approvedBy: null,
  audit: [],
  readiness: {
    tier1_approved: false,
    exceptions_worked: false,
    run_complete: false,
    no_rule_pending: true,
  },
  openItems: [],
  chainIntact: true,
  chainHead: "",
};

type Action =
  | { type: "intake-done"; workbench: Workbench }
  | { type: "approve-term"; name: string }
  | { type: "bulk-approve"; names: string[] }
  | { type: "queue-term"; name: string }
  | { type: "edit-term"; name: string; value: string; reason: string }
  | { type: "accept-mapping" }
  | { type: "run" }
  | { type: "work-exception"; id: string; outcome: ExceptionOutcome; note: string }
  | { type: "propose-rule"; edit: Omit<RuleEdit, "status"> }
  | { type: "decline-rule"; reason: string }
  | { type: "set-actor"; actor: Actor }
  | { type: "approve-load" }
  | { type: "reset" };

function payloadOf(action: Action): Record<string, unknown> {
  switch (action.type) {
    case "intake-done":
      return {};
    case "propose-rule":
      return action.edit;
    case "approve-load":
      return { carry_forward: true };
    default: {
      const payload: Record<string, unknown> = { ...action };
      delete payload.type;
      return payload;
    }
  }
}

async function send(path: string, body?: unknown): Promise<Omit<SessionState, "actor">> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const failure = await response.json().catch(() => null);
    throw new Error(failure?.detail ?? "The server could not record that action.");
  }
  return response.json();
}

interface SignedIn {
  signed_in: boolean;
  user: string | null;
  role: Actor | null;
}

interface SessionValue {
  state: SessionState;
  me: SignedIn | null;
  dispatch: (action: Action) => void;
  refusal: string | null;
  clearRefusal: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);
const SESSION_KEY = ["session"];

export function SessionProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [actor, setActor] = useState<Actor>("analyst");
  const [refusal, setRefusal] = useState<string | null>(null);
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: async (): Promise<SignedIn> => (await fetch("/api/me")).json(),
    staleTime: Infinity,
  });
  const { data, isError } = useQuery({
    queryKey: SESSION_KEY,
    queryFn: async (): Promise<Omit<SessionState, "actor">> => {
      const response = await fetch("/api/session", { signal: AbortSignal.timeout(10_000) });
      if (!response.ok) {
        throw new Error(`Session request failed with ${response.status}`);
      }
      return response.json();
    },
    staleTime: Infinity,
  });

  const dispatch = useCallback(
    (action: Action) => {
      if (action.type === "set-actor") {
        setActor(action.actor);
        return;
      }
      setRefusal(null);
      const request =
        action.type === "reset"
          ? send("/api/session/reset")
          : send("/api/session/events", { type: action.type, actor, payload: payloadOf(action) });
      request
        .then((next) => {
          client.setQueryData(SESSION_KEY, next);
          if (action.type === "reset") {
            setActor("analyst");
          }
        })
        .catch((error: Error) => setRefusal(error.message));
    },
    [actor, client],
  );

  const value = useMemo(
    () => ({
      state: { ...initial, ...data, actor: me?.role ?? actor },
      me: me ?? null,
      dispatch,
      // An unreachable session must not look like a case with no work done.
      refusal: refusal ?? (isError ? "The session service is not responding." : null),
      clearRefusal: () => setRefusal(null),
    }),
    [data, actor, me, dispatch, refusal, isError],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used inside SessionProvider");
  }
  return context;
}

export function termStatus(term: Term, state: SessionState): "approved" | "review" | "missing" {
  if (term.status === "missing") {
    return "missing";
  }
  return state.termApprovals[term.name] === "approved" ? "approved" : "review";
}
