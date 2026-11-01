import clsx from "clsx";
import { ArrowRight, Check, Download, ShieldAlert, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { StatusPill } from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader } from "../components/ui/PageHeader";
import { formatUsd } from "../lib/format";
import { ANALYST, APPROVER, useSession } from "../lib/session";
import { useValidationRun, useWorkbench } from "../lib/workbench";

function Check_({ passed, label }: { passed: boolean; label: string }) {
  return (
    <li className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <span>{label}</span>
      <StatusPill status={passed ? "approved" : "review"} label={passed ? "Done" : "Outstanding"} />
    </li>
  );
}

export function ApprovePage() {
  const { data } = useWorkbench();
  const { state, dispatch, me } = useSession();
  const navigate = useNavigate();
  const run = useValidationRun(state.dealerMatched, state.ran).data;
  const [carried, setCarried] = useState(false);

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }

  const tier1Count = data.terms.filter(
    (term) => term.tier === 1 && term.status !== "missing",
  ).length;
  const { readiness, openItems } = state;
  const ruleOpen = state.ruleEdit?.status === "pending";
  const approver = state.actor === "approver";
  const ready = Object.values(readiness).every(Boolean) && carried;
  const approved = Boolean(state.approvedAt);

  return (
    <div>
      <PageHeader
        title="Approve and load"
        summary="Second-analyst review before the load file is released."
        actions={
          approved && (
            <Button size="lg" onClick={() => navigate("/results")}>
              View scorecard
              <ArrowRight aria-hidden className="size-4" />
            </Button>
          )
        }
      />

      <div className="grid grid-cols-[minmax(0,1fr)_28rem] items-start gap-5">
        <div className="space-y-4">
          <Card className="p-5">
            <h2 className="font-semibold">Approval checklist</h2>
            <ul className="mt-2 divide-y divide-sand">
              <Check_
                passed={readiness.tier1_approved}
                label={`All sourced Tier 1 terms approved (${tier1Count})`}
              />
              <Check_ passed={readiness.exceptions_worked} label="All exceptions worked" />
              <Check_ passed={readiness.run_complete} label="Validation run complete" />
              <Check_ passed={readiness.no_rule_pending} label="No rule change pending" />
            </ul>
            {run && (
              <div className="numeric mt-3 grid grid-cols-3 gap-4 border-t border-line pt-3">
                {(
                  [
                    ["Eligible pool", run.system.eligible_pool],
                    ["Borrowing base", run.system.borrowing_base],
                    ["Availability", run.system.availability],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label}>
                    <SectionLabel>{label}</SectionLabel>
                    <p className="mt-1 text-lg font-semibold tracking-tight">{formatUsd(value)}</p>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {ruleOpen && state.ruleEdit && (
            <Card className="border-warn/40 p-5">
              <h2 className="font-semibold">Rule change awaiting a decision</h2>
              <p className="mt-1 text-sm text-muted">
                {state.ruleEdit.rule_id}: {state.ruleEdit.from} to {state.ruleEdit.to}. Reason given:{" "}
                {state.ruleEdit.reason}
              </p>
              <Button
                variant="secondary"
                className="mt-3"
                disabled={!approver}
                onClick={() =>
                  dispatch({
                    type: "decline-rule",
                    reason: "The agreement's threshold stands. An analyst cannot vary a term.",
                  })
                }
              >
                Decline: the agreement's threshold stands
              </Button>
            </Card>
          )}

          <Card className="p-5">
            <h2 className="font-semibold">Open items carried forward</h2>
            <p className="mt-0.5 text-[0.8125rem] text-muted">
              Awaiting third parties. These remain open after approval and are included in the load
              file.
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {openItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            {!approved && (
              <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm font-medium">
                <input
                  type="checkbox"
                  checked={carried}
                  disabled={!approver}
                  onChange={(event) => setCarried(event.target.checked)}
                  className="size-4 accent-ink"
                />
                I accept that these items carry forward
              </label>
            )}
          </Card>

          <Card className="overflow-hidden">
            <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-3">
              <h2 className="font-semibold">Audit log</h2>
              <StatusPill
                status={state.chainIntact ? "approved" : "missing"}
                label={state.chainIntact ? "Log integrity verified" : "Log integrity failed"}
              />
            </div>
            <ol tabIndex={0} aria-label="Audit log entries" className="max-h-72 overflow-y-auto">
              {[...state.audit].reverse().map((entry, index) => (
                <li key={`${entry.at}-${index}`} className="border-b border-sand px-5 py-2 last:border-0">
                  <p className="text-sm">
                    <span className="font-medium">{entry.actor}</span>
                    <span className="text-muted">: {entry.action}</span>
                    {entry.earlier && (
                      <span className="ml-2 rounded bg-sand px-1.5 py-0.5 text-xs text-muted">
                        Preloaded
                      </span>
                    )}
                  </p>
                  {entry.reason && (
                    <p className="mt-0.5 text-[0.8125rem] text-muted">Reason: {entry.reason}</p>
                  )}
                </li>
              ))}
            </ol>
          </Card>
        </div>

        <Card className="sticky top-32 p-5">
          <SectionLabel>{me?.signed_in ? "Signed in as" : "Acting as"}</SectionLabel>
          {me?.signed_in && <p className="mt-2 text-sm font-medium">{me.user}</p>}
          <div
            className="mt-2 flex items-center gap-2 rounded-lg bg-canvas p-1"
            hidden={me?.signed_in}
          >
            {(["analyst", "approver"] as const).map((actor) => (
              <button
                key={actor}
                type="button"
                aria-pressed={state.actor === actor}
                onClick={() => dispatch({ type: "set-actor", actor })}
                className={clsx(
                  "flex h-9 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-md text-[0.8125rem] font-medium",
                  state.actor === actor ? "bg-ink text-white" : "text-muted hover:bg-sand",
                )}
              >
                <UserRound aria-hidden className="size-3.5" />
                {actor === "analyst" ? ANALYST : APPROVER}
              </button>
            ))}
          </div>

          {!approved && !approver && (
            <p className="mt-4 flex items-start gap-2 rounded-lg bg-warn-tint p-3 text-sm text-warn">
              <ShieldAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
              You prepared this case, so you cannot approve it. Four-eyes review needs a second
              analyst.
            </p>
          )}
          {!approved && (
            <Button
              size="lg"
              className="mt-4 w-full"
              disabled={!approver || !ready}
              onClick={() => dispatch({ type: "approve-load" })}
            >
              <Check aria-hidden className="size-4" />
              Approve with {openItems.length} open items
            </Button>
          )}
          {approved && (
            <div className="mt-4 space-y-3">
              <p className="flex items-center gap-2 rounded-lg bg-ok-tint p-3 text-sm font-medium text-ok">
                <ShieldCheck aria-hidden className="size-4 shrink-0" />
                Approved with {openItems.length} open items by {APPROVER}
              </p>
              <a
                href="/api/load-file"
                download
                className="flex h-12 w-full items-center justify-center gap-2 rounded-lg border border-line bg-surface text-[0.9375rem] font-medium hover:border-stone hover:bg-canvas"
              >
                <Download aria-hidden className="size-4" />
                Download load file
              </a>
              <p className="text-xs text-muted">
                Sandbox output. This layout is not a Panorama import format.
              </p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
