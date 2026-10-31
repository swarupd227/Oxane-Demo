import clsx from "clsx";
import { ArrowRight, Check, Download, ShieldAlert, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { StatusPill } from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader } from "../components/ui/PageHeader";
import { formatUsd } from "../lib/format";
import { ANALYST, APPROVER, termStatus, useSession } from "../lib/session";
import { useValidationRun, useWorkbench, type RunResult, type Workbench } from "../lib/workbench";

function Check_({ passed, label }: { passed: boolean; label: string }) {
  return (
    <li className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <span>{label}</span>
      <StatusPill status={passed ? "approved" : "review"} label={passed ? "Done" : "Outstanding"} />
    </li>
  );
}

function downloadLoadFile(data: Workbench, run: RunResult, openItems: string[], approvedAt: string) {
  const payload = {
    note: "Demo layout. Not a Panorama format. All data is synthetic.",
    case: "0412",
    approved_at: approvedAt,
    prepared_by: ANALYST,
    approved_by: APPROVER,
    run_digest: run.digest,
    provisional: run.provisional,
    open_items: openItems,
    terms: data.terms.map(({ name, tier, value, clause }) => ({ name, tier, value, clause })),
    borrowing_base: run.system,
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "case-0412-load-file.json";
  link.click();
  URL.revokeObjectURL(url);
}

export function ApprovePage() {
  const { data } = useWorkbench();
  const { state, dispatch } = useSession();
  const navigate = useNavigate();
  const run = useValidationRun(state.dealerMatched, state.ran).data;
  const [carried, setCarried] = useState(false);

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }

  const tier1 = data.terms.filter((term) => term.tier === 1 && term.status !== "missing");
  const tier1Done = tier1.every((term) => termStatus(term, state) === "approved");
  const unworked = data.exceptions.filter((item) => !state.exceptions[item.id]);
  const ruleOpen = state.ruleEdit?.status === "pending";
  const open = data.exceptions.filter(
    (item) => item.blocking && state.exceptions[item.id] !== "accepted",
  );
  const openItems = [
    ...open.map((item) => `${item.id}: ${item.title} (${item.owner})`),
    "Restricted Jurisdictions: open until Schedule 4 arrives",
  ];
  const approver = state.actor === "approver";
  const ready =
    tier1Done && unworked.length === 0 && state.ran && !ruleOpen && carried && Boolean(run);
  const approved = Boolean(state.approvedAt);

  return (
    <div>
      <PageHeader
        title="Approve and load"
        summary="No data reaches the platform without a second analyst."
        actions={
          approved && (
            <Button size="lg" onClick={() => navigate("/results")}>
              See the scorecard
              <ArrowRight aria-hidden className="size-4" />
            </Button>
          )
        }
      />

      <div className="grid grid-cols-[minmax(0,1fr)_28rem] items-start gap-5">
        <div className="space-y-4">
          <Card className="p-5">
            <h2 className="font-semibold">Change summary</h2>
            <ul className="mt-2 divide-y divide-sand">
              <Check_ passed={tier1Done} label={`All ${tier1.length} Tier 1 values with a source approved`} />
              <Check_ passed={unworked.length === 0} label="All exceptions worked" />
              <Check_ passed={state.ran} label="Validation run complete" />
              <Check_ passed={!ruleOpen} label="No rule change pending" />
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
              These wait on outside parties, so they stay open after approval and go in the load
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
            <h2 className="border-b border-line px-5 py-3 font-semibold">Audit log</h2>
            <ol className="max-h-72 overflow-y-auto">
              {[...state.audit].reverse().map((entry, index) => (
                <li key={`${entry.at}-${index}`} className="border-b border-sand px-5 py-2 last:border-0">
                  <p className="text-sm">
                    <span className="font-medium">{entry.actor}</span>
                    <span className="text-muted">: {entry.action}</span>
                    {entry.earlier && (
                      <span className="ml-2 rounded bg-sand px-1.5 py-0.5 text-xs text-muted">
                        Before the demo
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
          <SectionLabel>Signed in as</SectionLabel>
          <div className="mt-2 flex items-center gap-2 rounded-lg bg-canvas p-1">
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
              onClick={() => dispatch({ type: "approve-load", openItems: openItems.length })}
            >
              <Check aria-hidden className="size-4" />
              Approve with {openItems.length} open items
            </Button>
          )}
          {approved && run && state.approvedAt && (
            <div className="mt-4 space-y-3">
              <p className="flex items-center gap-2 rounded-lg bg-ok-tint p-3 text-sm font-medium text-ok">
                <ShieldCheck aria-hidden className="size-4 shrink-0" />
                Approved with {openItems.length} open items by {APPROVER}
              </p>
              <Button
                variant="secondary"
                size="lg"
                className="w-full"
                onClick={() => downloadLoadFile(data, run, openItems, state.approvedAt as string)}
              >
                <Download aria-hidden className="size-4" />
                Download load file
              </Button>
              <p className="text-xs text-muted">
                Demo layout. Mapping to Panorama's real format is a discovery task.
              </p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
