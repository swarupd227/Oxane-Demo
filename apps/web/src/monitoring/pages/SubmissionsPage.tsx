import clsx from "clsx";
import { ArrowRight, BellRing, Bot, CheckCircle2, Clock3, Columns3, Mail, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { PageHeader } from "../../components/ui/PageHeader";
import { formatDate } from "../../lib/format";
import { useCycle, useCycleAction, useCycleSession, type Submission } from "../cycle";
import { FacilityTag } from "../parts";

const statusView = {
  received: { label: "Received", icon: CheckCircle2, className: "bg-ok-tint text-ok" },
  received_late: { label: "Received late", icon: Clock3, className: "bg-warn-tint text-warn" },
  late: { label: "Late", icon: TriangleAlert, className: "bg-danger-tint text-danger" },
  awaited: { label: "Awaited", icon: Clock3, className: "bg-sand text-muted" },
};

function ChaseDialog({ submission, onClose }: { submission: Submission | null; onClose: () => void }) {
  return (
    <Dialog open={!!submission} onOpenChange={(open) => !open && onClose()} title="Chase history" description={submission ? `${submission.label}, due ${formatDate(submission.due)}` : undefined}>
      <ol className="space-y-4">
        {submission?.chase.map((step) => (
          <li key={step.at} className="rounded-lg border border-line p-3">
            <p className="flex items-center justify-between gap-2 text-sm font-semibold">
              <span className="flex items-center gap-1.5">
                <Mail aria-hidden className="size-4 text-muted" />
                {step.action}
              </span>
              <span className="numeric text-xs font-medium text-muted">{formatDate(step.at)}</span>
            </p>
            <p className="mt-1 text-xs text-muted">To: {step.to}</p>
            <p className="mt-2 text-sm">{step.text}</p>
          </li>
        ))}
      </ol>
    </Dialog>
  );
}

export function SubmissionsPage() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const action = useCycleAction();
  const navigate = useNavigate();
  const [chase, setChase] = useState<Submission | null>(null);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const late = cycle.submissions.filter((s) => s.status === "late");
  const layout = cycle.layout;
  return (
    <>
      <PageHeader
        title="Submission tracker"
        summary="Documents due under each facility's reporting clause, what arrived and when. Late files are chased automatically."
        actions={
          <Button onClick={() => navigate("/monitoring/reconciliation")}>
            Reconcile
            <ArrowRight aria-hidden className="size-4" />
          </Button>
        }
      />
      {late.map((s) => (
        <div key={s.label} role="status" className="mb-4 flex items-center justify-between gap-4 rounded-lg bg-danger-tint px-4 py-3 text-sm">
          <span className="flex items-center gap-2 text-danger">
            <BellRing aria-hidden className="size-4 shrink-0" />
            <span>
              <strong>{cycle.facilities.find((f) => f.id === s.facility)?.name}:</strong> {s.label} was due {formatDate(s.due)}.{" "}
              {s.chase.map((c, i) => `${i ? c.action.toLowerCase() : c.action} ${formatDate(c.at)}`).join(", then ")}.
            </span>
          </span>
          <Button variant="secondary" size="sm" onClick={() => setChase(s)}>
            View chase
          </Button>
        </div>
      ))}
      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-5">
        <Card>
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
                <th className="py-2.5 pr-3 pl-5">Facility</th>
                <th className="py-2.5 pr-3">Document</th>
                <th className="py-2.5 pr-3">Due</th>
                <th className="py-2.5 pr-3">Received</th>
                <th className="py-2.5 pr-5">Status</th>
              </tr>
            </thead>
            <tbody>
              {cycle.submissions.map((s) => {
                const view = statusView[s.status];
                const Icon = view.icon;
                const facility = cycle.facilities.find((f) => f.id === s.facility)!;
                return (
                  <tr key={`${s.facility}-${s.label}`} className={clsx("border-b border-sand last:border-0", s.status === "late" && "bg-danger-tint/40")}>
                    <td className="py-2.5 pr-3 pl-5">
                      <FacilityTag id={facility.id} name={facility.name.split(" ")[0]} />
                    </td>
                    <td className="py-2.5 pr-3 text-sm">
                      {s.label}
                      {s.file && <p className="truncate text-xs text-muted">{s.file}</p>}
                    </td>
                    <td className="numeric py-2.5 pr-3 text-sm text-muted">{formatDate(s.due)}</td>
                    <td className="numeric py-2.5 pr-3 text-sm">{s.received ? formatDate(s.received) : "–"}</td>
                    <td className="py-2.5 pr-5">
                      <span className="flex items-center gap-2">
                        <span className={clsx("inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium", view.className)}>
                          <Icon aria-hidden className="size-3.5" />
                          {view.label}
                        </span>
                        {s.chase.length > 0 && (
                          <button type="button" onClick={() => setChase(s)} className="cursor-pointer text-xs font-medium text-info underline-offset-2 hover:underline">
                            {s.chase.length} chases
                          </button>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>

        <Card className="self-start p-5">
          <p className="flex items-center gap-2 font-semibold">
            <Columns3 aria-hidden className="size-4 text-muted" />
            Layout change: Bramble May tape
          </p>
          <p className="mt-1 text-sm text-muted">
            <span className="numeric font-medium text-ink">{layout.from_memory}</span> of {layout.columns_total} columns mapped from last month's mapping. The servicer added{" "}
            {layout.new_columns.length} columns.
          </p>
          <ul className="mt-4 space-y-3">
            {layout.new_columns.map((column) => (
              <li key={column.column} className="rounded-lg border border-line p-3">
                <div className="flex items-center justify-between gap-2">
                  <code className="font-mono text-sm font-semibold">{column.column}</code>
                  <span className="inline-flex h-6 items-center rounded-full bg-sand px-2.5 text-xs font-medium text-muted">Logged, no alert</span>
                </div>
                <p className="mt-1.5 flex items-start gap-1.5 text-sm">
                  <Bot aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted" />
                  <span>
                    {column.field ? `Maps to ${column.field}. ` : ""}
                    {column.reason}
                  </span>
                </p>
                <p className="mt-1 text-xs text-muted">
                  Values: {column.values.join(", ")} · {column.outcome}
                </p>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex items-center justify-between gap-3">
            <SectionLabel>AI suggests, analyst confirms</SectionLabel>
            {session?.layoutConfirmed ? (
              <span className="inline-flex items-center gap-1.5 text-sm font-medium text-ok">
                <CheckCircle2 aria-hidden className="size-4" />
                Confirmed
              </span>
            ) : (
              <Button size="sm" variant="secondary" disabled={action.isPending} onClick={() => action.mutate({ type: "confirm-layout" })}>
                Confirm mapping
              </Button>
            )}
          </div>
        </Card>
      </div>
      <ChaseDialog submission={chase} onClose={() => setChase(null)} />
    </>
  );
}
