import { useCasework, formatStamp } from "./casework";
import { useCases } from "./cases";
import { useSession } from "./session";

export interface Notice {
  id: string;
  kind: "answer" | "variance" | "approval";
  title: string;
  detail: string;
  to: string;
}

/** What needs someone's attention: client answers in, open QC variances, approvals waiting. */
export function useNotifications(): Notice[] {
  const { state } = useSession();
  const { data: casework } = useCasework();
  const { data: pipeline } = useCases();
  const notices: Notice[] = [];
  if (state.intakeDone && casework) {
    for (const query of casework.tracker.queries) {
      if (query.answer_waiting || query.status === "answered") {
        notices.push({
          id: `answer-${query.id}`,
          kind: "answer",
          title: `${query.id} answered`,
          detail: `${query.to}${query.answered ? ` · ${formatStamp(query.answered)}` : ""}`,
          to: `/queries?id=${query.id}`,
        });
      }
    }
    for (const line of casework.qc.open) {
      notices.push({
        id: `variance-${line}`,
        kind: "variance",
        title: "QC variance open",
        detail: line,
        to: "/qc",
      });
    }
    if (casework.qc.can_release) {
      notices.push({ id: "release", kind: "approval", title: "First report ready for release", detail: "Case 0412 · reviewer", to: "/qc" });
    }
  }
  if (state.ruleEdit?.status === "pending") {
    notices.push({
      id: "rule",
      kind: "approval",
      title: `Rule change ${state.ruleEdit.rule_id} awaiting approval`,
      detail: `${state.ruleEdit.from} → ${state.ruleEdit.to}`,
      to: "/approve",
    });
  }
  const ready = state.intakeDone && Object.values(state.readiness).every(Boolean);
  if (ready && !state.approvedAt) {
    notices.push({ id: "load", kind: "approval", title: "Case 0412 ready for approval", detail: "Load file · second analyst", to: "/approve" });
  }
  for (const item of pipeline?.cases ?? []) {
    if (!item.active && item.qc_variances_open > 0) {
      notices.push({
        id: `pipeline-${item.number}`,
        kind: "variance",
        title: `QC variances open: ${item.qc_variances_open}`,
        detail: `${item.number} · ${item.facility}`,
        to: `/cases/${item.number}`,
      });
    }
  }
  return notices;
}
