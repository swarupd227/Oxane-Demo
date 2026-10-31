/* The analyst's session. Phase 5 moves this state to the server. */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import type { Term, Workbench } from "./workbench";

export type Actor = "analyst" | "approver";
export type ExceptionOutcome = "accepted" | "queried" | "escalated";

export interface AuditEntry {
  at: string;
  actor: string;
  action: string;
  reason?: string;
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
  audit: AuditEntry[];
}

export const ANALYST = "Onboarding analyst";
export const APPROVER = "Second analyst";

// These are worked live on stage. Everything else was done before the demo, and says so.
const LIVE_TERMS = new Set(["Facility limit", "Advance rate"]);
const TERM_EXCEPTIONS: Record<string, string> = {
  "Advance rate": "X1",
  "Facility limit": "X3",
};
const EARLIER_EXCEPTIONS: Record<string, ExceptionOutcome> = {
  X2: "queried",
  X7: "queried",
  X8: "accepted",
  X9: "accepted",
  X10: "accepted",
};

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
  audit: [],
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
  | { type: "approve-load"; openItems: number }
  | { type: "reset" };

function log(state: SessionState, action: string, reason?: string): AuditEntry[] {
  const actor = state.actor === "analyst" ? ANALYST : APPROVER;
  return [...state.audit, { at: new Date().toISOString(), actor, action, reason }];
}

function withEarlierWork(state: SessionState, terms: Term[]): SessionState {
  const earlier = terms.filter(
    (term) => term.tier === 1 && term.status === "approved" && !LIVE_TERMS.has(term.name),
  );
  const approvals = { ...state.termApprovals };
  const audit = [...state.audit];
  for (const term of earlier) {
    approvals[term.name] = "approved";
    audit.push({
      at: new Date().toISOString(),
      actor: ANALYST,
      action: `Approved ${term.name}`,
      earlier: true,
    });
  }
  for (const [id, outcome] of Object.entries(EARLIER_EXCEPTIONS)) {
    audit.push({
      at: new Date().toISOString(),
      actor: ANALYST,
      action: `${id}: ${outcome}`,
      earlier: true,
    });
  }
  return {
    ...state,
    termApprovals: approvals,
    exceptions: { ...EARLIER_EXCEPTIONS, ...state.exceptions },
    audit,
  };
}

function reducer(state: SessionState, action: Action): SessionState {
  switch (action.type) {
    case "intake-done":
      return withEarlierWork(
        {
          ...state,
          intakeDone: true,
          startedAt: state.startedAt ?? new Date().toISOString(),
          audit: log(state, "Uploaded 8-file document pack"),
        },
        action.workbench.terms,
      );
    case "approve-term": {
      // Confirming these values is also what closes their exception.
      const closes = TERM_EXCEPTIONS[action.name];
      return {
        ...state,
        termApprovals: { ...state.termApprovals, [action.name]: "approved" },
        exceptions: closes ? { ...state.exceptions, [closes]: "accepted" } : state.exceptions,
        audit: log(state, `Approved ${action.name}`),
      };
    }
    case "bulk-approve":
      return {
        ...state,
        termApprovals: {
          ...state.termApprovals,
          ...Object.fromEntries(action.names.map((name) => [name, "approved" as const])),
        },
        audit: log(state, `Bulk approved ${action.names.length} Tier 2 and 3 values`),
      };
    case "queue-term":
      return {
        ...state,
        termApprovals: { ...state.termApprovals, [action.name]: "queued" },
        audit: log(state, `Sent ${action.name} to the queue`),
      };
    case "edit-term":
      return {
        ...state,
        termEdits: { ...state.termEdits, [action.name]: action.value },
        audit: log(state, `Edited ${action.name} to ${action.value}`, action.reason),
      };
    case "accept-mapping":
      return { ...state, mappingAccepted: true, audit: log(state, "Accepted tape mapping") };
    case "run":
      return state.ran
        ? state
        : {
            ...state,
            ran: true,
            audit: log(state, "Ran the April tape: 16 rules run, E7 not evaluated"),
          };
    case "work-exception":
      return {
        ...state,
        exceptions: { ...state.exceptions, [action.id]: action.outcome },
        dealerMatched: state.dealerMatched || (action.id === "X6" && action.outcome === "accepted"),
        audit: log(state, `${action.id}: ${action.outcome}`, action.note),
      };
    case "propose-rule":
      return {
        ...state,
        ruleEdit: { ...action.edit, status: "pending" },
        audit: log(
          state,
          `Proposed ${action.edit.rule_id}: ${action.edit.from} to ${action.edit.to}`,
          action.edit.reason,
        ),
      };
    case "decline-rule":
      return state.ruleEdit
        ? {
            ...state,
            ruleEdit: { ...state.ruleEdit, status: "declined", decline_reason: action.reason },
            audit: log(state, `Declined rule change to ${state.ruleEdit.rule_id}`, action.reason),
          }
        : state;
    case "set-actor":
      return { ...state, actor: action.actor };
    case "approve-load":
      return {
        ...state,
        approvedAt: new Date().toISOString(),
        audit: log(
          state,
          action.openItems
            ? `Approved load file with ${action.openItems} open items`
            : "Approved load file",
        ),
      };
    case "reset":
      return initial;
  }
}

const STORAGE_KEY = "workbench.session.v1";

function restore(): SessionState {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? { ...initial, ...JSON.parse(stored) } : initial;
  } catch {
    return initial;
  }
}

const SessionContext = createContext<{
  state: SessionState;
  dispatch: Dispatch<Action>;
} | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, restore);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // A reload loses the session if storage is blocked. The demo itself still works.
    }
  }, [state]);

  const value = useMemo(() => ({ state, dispatch }), [state]);
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
