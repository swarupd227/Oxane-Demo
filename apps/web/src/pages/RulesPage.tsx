import { CircleAlert, History, Pencil } from "lucide-react";
import { useEffect, useState } from "react";
import { ProvenanceChip, StatusPill } from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader, SeedNotice } from "../components/ui/PageHeader";
import { formatCount, formatUsd } from "../lib/format";
import { ANALYST, useSession } from "../lib/session";
import { useRulePreview, useWorkbench, type Rule } from "../lib/workbench";

const signed = (value: number) => `${value > 0 ? "+" : ""}${formatUsd(value)}`;

function EditRuleDialog({ rule, onClose }: { rule: Rule; onClose: () => void }) {
  const { dispatch } = useSession();
  const [value, setValue] = useState(String(rule.threshold ?? ""));
  const [reason, setReason] = useState("");
  const preview = useRulePreview();
  const { mutate } = preview;
  const number = Number(value);
  const changed = value !== "" && Number.isFinite(number) && number !== rule.threshold;

  useEffect(() => {
    if (!changed) {
      return;
    }
    const timer = setTimeout(() => mutate({ rule_id: rule.id, value: number }), 250);
    return () => clearTimeout(timer);
  }, [changed, number, rule.id, mutate]);

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Change ${rule.id}`}
      description={rule.plain_english}
    >
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          dispatch({
            type: "propose-rule",
            edit: { rule_id: rule.id, from: rule.threshold ?? 0, to: number, reason },
          });
          onClose();
        }}
      >
        <label className="block text-sm font-medium">
          New threshold
          <input
            type="number"
            autoFocus
            value={value}
            onChange={(event) => setValue(event.target.value)}
            className="numeric mt-1 h-10 w-full rounded-lg border border-line px-3 font-normal"
          />
        </label>

        <div className="rounded-lg bg-canvas p-3" aria-live="polite">
          <SectionLabel>What this would change</SectionLabel>
          {!changed && <p className="mt-1 text-sm text-muted">Enter a new value to see.</p>}
          {changed && preview.data && (
            <dl className="numeric mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted">Loans becoming eligible</dt>
              <dd className="text-right font-medium">{preview.data.newly_eligible}</dd>
              <dt className="text-muted">Loans becoming ineligible</dt>
              <dd className="text-right font-medium">{preview.data.newly_ineligible}</dd>
              <dt className="text-muted">Eligible pool</dt>
              <dd className="text-right font-medium">{signed(preview.data.eligible_pool_change)}</dd>
              <dt className="text-muted">Borrowing base</dt>
              <dd className="text-right font-medium">
                {signed(preview.data.borrowing_base_change)}
              </dd>
            </dl>
          )}
        </div>

        <label className="block text-sm font-medium">
          Reason
          <textarea
            required
            rows={2}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="mt-1 w-full rounded-lg border border-line px-3 py-2 font-normal"
          />
        </label>
        <p className="text-[0.8125rem] text-muted">
          Saved as pending. Runs keep using the approved rules until a second analyst decides.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!changed || !reason.trim()}>
            Save as pending
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function RuleRow({ rule, onEdit, pending }: { rule: Rule; onEdit: () => void; pending: boolean }) {
  return (
    <tr className="border-b border-sand align-top last:border-0">
      <td className="numeric py-3 pr-3 pl-5 text-sm font-semibold">{rule.id}</td>
      <td className="w-[34%] py-3 pr-5">
        <p className="text-[0.8125rem] leading-snug text-muted">{rule.clause_text}</p>
        <p className="mt-1 text-xs font-medium text-muted">{rule.clause_ref}</p>
      </td>
      <td className="py-3 pr-5 text-sm font-medium">{rule.plain_english}</td>
      <td className="py-3 pr-5">
        <code className="font-mono text-[0.8125rem] leading-snug">{rule.logic}</code>
        {rule.effective_from && (
          <p className="numeric mt-1 text-xs text-muted">From 1 Mar 2026</p>
        )}
      </td>
      <td className="py-3 pr-5">
        {rule.status === "not_evaluated" && (
          <StatusPill status="missing" label="Cannot run: Schedule 4 missing" />
        )}
        {pending && <StatusPill status="review" label="Change pending" />}
        {rule.status === "ready" && !pending && <ProvenanceChip kind="ai" />}
      </td>
      <td className="py-3 pr-5 text-right">
        {rule.threshold !== null && (
          <Button variant="ghost" size="sm" aria-label={`Edit ${rule.id}`} onClick={onEdit}>
            <Pencil aria-hidden className="size-3.5" />
            Edit
          </Button>
        )}
      </td>
    </tr>
  );
}

function RuleGroup(props: {
  title: string;
  summary: string;
  rules: Rule[];
  pendingId?: string;
  onEdit: (rule: Rule) => void;
}) {
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-line px-5 py-3">
        <h2 className="font-semibold">{props.title}</h2>
        <p className="text-[0.8125rem] text-muted">{props.summary}</p>
      </div>
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
            <th className="py-2 pr-3 pl-5">Rule</th>
            <th className="py-2 pr-5">Clause as written</th>
            <th className="py-2 pr-5">Plain English</th>
            <th className="py-2 pr-5">Test logic</th>
            <th className="py-2 pr-5">State</th>
            <th>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {props.rules.map((rule) => (
            <RuleRow
              key={rule.id}
              rule={rule}
              pending={props.pendingId === rule.id}
              onEdit={() => props.onEdit(rule)}
            />
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export function RulesPage() {
  const { data } = useWorkbench();
  const { state } = useSession();
  const [editing, setEditing] = useState<Rule | null>(null);

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }

  const edit = state.ruleEdit;
  const pendingId = edit?.status === "pending" ? edit.rule_id : undefined;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Rules from the agreement"
        summary={`${formatCount(data.rules.length)} tests, each shown three ways. The model drafts them. A deterministic engine runs them.`}
      />
      <SeedNotice>
        Seed data: rule set v1 was written by hand. The rule drafter arrives in phase 4. Previews
        are real engine runs.
      </SeedNotice>

      {edit && (
        <div className="flex items-start gap-3 rounded-lg border border-warn/30 bg-warn-tint p-3 text-sm">
          <History aria-hidden className="mt-0.5 size-4 shrink-0 text-warn" />
          <p>
            <span className="font-medium">
              {edit.status === "pending" ? "Pending rule set v2:" : "Declined:"}
            </span>{" "}
            {edit.rule_id} from {edit.from} to {edit.to}, by {ANALYST}. Reason: {edit.reason}
            {edit.status === "pending" && " Runs still use the approved rule set v1."}
          </p>
        </div>
      )}
      {data.rules.some((rule) => rule.status === "not_evaluated") && (
        <div className="flex items-center gap-3 rounded-lg bg-danger-tint p-3 text-sm">
          <CircleAlert aria-hidden className="size-4 shrink-0 text-danger" />
          E7 cannot run until Schedule 4 arrives, so every result stays provisional.
        </div>
      )}

      <RuleGroup
        title="Eligibility criteria"
        summary="Schedule 1. A loan that fails any test is excluded in full."
        rules={data.rules.filter((rule) => rule.group === "eligibility")}
        pendingId={pendingId}
        onEdit={setEditing}
      />
      <RuleGroup
        title="Concentration limits"
        summary="Schedule 2, as amended. The amount above each limit is cut, in schedule order."
        rules={data.rules.filter((rule) => rule.group === "concentration")}
        onEdit={setEditing}
      />
      {editing && <EditRuleDialog rule={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}
