import clsx from "clsx";
import { Check, Download, ShieldAlert, ShieldCheck, UserRound } from "lucide-react";
import { useState, type ReactNode } from "react";
import { StatusPill } from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, NextStep, PageHeader } from "../components/ui/PageHeader";
import { Avatar } from "../components/ui/Avatar";
import { Timeline } from "../components/ui/Timeline";
import { useCasework } from "../lib/casework";
import { formatDateTime } from "../lib/format";
import type { AuditEntry } from "../lib/session";
import { ruleChangeId } from "./RulesPage";
import { formatUsd } from "../lib/format";
import { ANALYST, APPROVER, useSession } from "../lib/session";
import { useValidationRun, useWorkbench } from "../lib/workbench";

const OUTCOMES = { accepted: "Accepted", queried: "Query drafted", escalated: "Escalated" };

function SummaryRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[10rem_minmax(0,1fr)] gap-4 py-2">
      <dt className="font-medium">{label}</dt>
      <dd className="space-y-0.5">{children}</dd>
    </div>
  );
}

function Check_({ passed, label }: { passed: boolean; label: string }) {
  return (
    <li className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <span>{label}</span>
      <StatusPill status={passed ? "approved" : "review"} label={passed ? "Done" : "Outstanding"} />
    </li>
  );
}

function at(audit: AuditEntry[], type: string): AuditEntry | undefined {
  return [...audit].reverse().find((entry) => entry.type === type);
}

function Approvals({
  audit,
  casework,
}: {
  audit: AuditEntry[];
  casework: ReturnType<typeof useCasework>["data"];
}) {
  const { state } = useSession();
  const edit = state.ruleEdit;
  const decided = edit && edit.status !== "pending" ? at(audit, edit.status === "approved" ? "approve-rule" : "decline-rule") : undefined;
  const rows = [
    ...(edit
      ? [{
          id: ruleChangeId(audit),
          item: `Rule change ${edit.rule_id}: ${edit.from} → ${edit.to}`,
          requested: at(audit, "propose-rule"),
          status: edit.status === "pending" ? "Pending" : edit.status === "approved" ? "Approved" : "Declined",
          decided,
        }]
      : []),
    {
      id: "AP-0412-LOAD",
      item: "Load file, case 0412",
      requested: at(audit, "run"),
      status: state.approvedAt ? "Approved" : Object.values(state.readiness).every(Boolean) ? "Pending" : "Not ready",
      decided: at(audit, "approve-load"),
    },
    {
      id: "AP-0412-REL",
      item: "First borrowing base report release",
      requested: at(audit, "approve-load"),
      status: casework?.qc.status === "released" ? "Released" : casework?.qc.can_release ? "Pending" : "Not ready",
      decided: at(audit, "release-report"),
    },
  ];
  const tone: Record<string, string> = {
    Pending: "bg-warn-tint text-warn",
    Approved: "bg-ok-tint text-ok",
    Released: "bg-ok-tint text-ok",
    Declined: "bg-danger-tint text-danger",
    "Not ready": "bg-sand text-muted",
  };
  return (
    <Card className="overflow-hidden">
      <h2 className="border-b border-line px-4 py-2 text-sm font-semibold">Approvals</h2>
      <table className="w-full text-left text-[0.8125rem]">
        <thead>
          <tr className="border-b border-line text-xs font-medium text-subtle">
            <th className="py-1.5 pr-3 pl-4">ID</th>
            <th className="py-1.5 pr-3">Item</th>
            <th className="py-1.5 pr-3">Requested</th>
            <th className="py-1.5 pr-3">Status</th>
            <th className="py-1.5 pr-4">Decided</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-sand last:border-0">
              <td className="py-1.5 pr-3 pl-4 font-mono text-xs whitespace-nowrap">{row.id}</td>
              <td className="py-1.5 pr-3">{row.item}</td>
              <td className="numeric py-1.5 pr-3 text-xs text-muted">
                {row.requested ? formatDateTime(row.requested.at) : "-"}
              </td>
              <td className="py-1.5 pr-3">
                <span className={`inline-flex h-5 items-center rounded px-1.5 text-[0.6875rem] font-medium ${tone[row.status]}`}>
                  {row.status}
                </span>
              </td>
              <td className="py-1.5 pr-4 text-xs">
                {row.decided ? (
                  // The time wraps under the date rather than being clipped by the card on a narrow screen.
                  <span className="flex items-center gap-1.5">
                    <Avatar name={row.decided.actor} />
                    <span className="numeric text-muted">{formatDateTime(row.decided.at)}</span>
                  </span>
                ) : (
                  <span className="text-muted">-</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export function ApprovePage() {
  const { data } = useWorkbench();
  const { state, dispatch, me } = useSession();
  const { data: casework } = useCasework();
  const run = useValidationRun(state.dealerMatched, state.ran).data;
  const [carried, setCarried] = useState(false);
  const [decision, setDecision] = useState("");

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
        summary={`Case 0412 · ${openItems.length} open items · ${Object.values(readiness).filter(Boolean).length} of ${Object.keys(readiness).length} checks done`}
        actions={approved && <NextStep to="/results" label="View scorecard" />}
      />

      <div className="grid grid-cols-[minmax(0,1fr)_28rem] items-start gap-5">
        <div className="space-y-4">
          <Approvals audit={state.audit} casework={casework} />
          <Card className="p-4">
            <h2 className="text-sm font-semibold">Approval checklist</h2>
            <ul className="mt-2 divide-y divide-sand">
              <Check_
                passed={readiness.tier1_approved}
                label={`All sourced Tier 1 terms approved (${tier1Count})`}
              />
              <Check_
                passed={readiness.all_terms_approved}
                label="All Tier 2 and 3 terms approved"
              />
              <Check_ passed={readiness.exceptions_worked} label="All exceptions worked" />
              <Check_ passed={readiness.mapping_accepted} label="Tape mapping accepted" />
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

          <Card className="p-4">
            <h2 className="text-sm font-semibold">Change summary</h2>
            <dl className="mt-2 divide-y divide-sand text-sm">
              <SummaryRow label="Terms edited">
                {state.changes.terms.length === 0 && "None"}
                {state.changes.terms.map((item) => (
                  <p key={item.name}>
                    {item.name}: {item.from} to {item.to}
                    {item.reason && <span className="text-muted">. {item.reason}</span>}
                  </p>
                ))}
              </SummaryRow>
              <SummaryRow label="Sent to the queue">
                {state.changes.held.length ? state.changes.held.join(", ") : "None"}
              </SummaryRow>
              <SummaryRow label="Exceptions">
                {state.changes.exceptions.map((item) => (
                  <p key={item.id}>
                    <span className="numeric font-medium">{item.id}</span>{" "}
                    {OUTCOMES[item.outcome]}: <span className="text-muted">{item.title}</span>
                  </p>
                ))}
              </SummaryRow>
              <SummaryRow label="Tape mapping">
                {state.changes.columns_accepted} of {data.mapping.rows.length} columns accepted
              </SummaryRow>
              <SummaryRow label="Rule changes">
                {state.ruleEdit
                  ? `${state.ruleEdit.rule_id}: ${state.ruleEdit.from} to ${state.ruleEdit.to} (${state.ruleEdit.status})`
                  : "None"}
              </SummaryRow>
            </dl>
          </Card>

          {ruleOpen && state.ruleEdit && (
            <Card className="border-warn/40 p-4">
              <h2 className="text-sm font-semibold">Rule change awaiting a decision</h2>
              <p className="mt-1 text-sm text-muted">
                {state.ruleEdit.rule_id}: {state.ruleEdit.from} to {state.ruleEdit.to}. Reason given:{" "}
                {state.ruleEdit.reason}
              </p>
              <label className="mt-3 block text-sm font-medium">
                Decision reason
                <input
                  value={decision}
                  disabled={!approver}
                  onChange={(event) => setDecision(event.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-line px-3 font-normal"
                />
              </label>
              <div className="mt-3 flex gap-2">
                <Button
                  variant="secondary"
                  disabled={!approver || !decision.trim()}
                  onClick={() => dispatch({ type: "decline-rule", reason: decision })}
                >
                  Decline
                </Button>
                <Button
                  variant="secondary"
                  disabled={!approver || !decision.trim()}
                  onClick={() => dispatch({ type: "approve-rule", reason: decision })}
                >
                  Approve change
                </Button>
              </div>
            </Card>
          )}

          <Card className="p-4">
            <h2 className="text-sm font-semibold">Open items carried forward</h2>
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

          <Card id="audit" className="overflow-hidden">
            <div className="flex items-center justify-between gap-4 border-b border-line px-4 py-2">
              <h2 className="text-sm font-semibold">
                Audit log <span className="font-normal text-muted">· {state.audit.length} events</span>
              </h2>
              <StatusPill
                status={state.chainIntact ? "approved" : "missing"}
                label={state.chainIntact ? "Log integrity verified" : "Log integrity failed"}
              />
            </div>
            <div tabIndex={0} role="region" aria-label="Audit log entries" className="max-h-80 overflow-y-auto px-4 py-3">
              <Timeline entries={[...state.audit].reverse()} showChain />
            </div>
          </Card>
        </div>

        <Card className="sticky top-14 p-4">
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
                  state.actor === actor ? "bg-accent-tint text-accent-strong font-medium" : "text-muted hover:bg-sand",
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
              You prepared this case. Approval requires a second analyst.
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
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
