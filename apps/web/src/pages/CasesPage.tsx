import clsx from "clsx";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ActionButton } from "../components/deals/parts";
import { Card, Skeleton } from "../components/ui/layout";
import { casePath, ownerName, useCases, type Stage } from "../lib/cases";
import { STAGE_LABEL, useDealCases } from "../lib/deals";
import { formatDate, formatUsdShort } from "../lib/format";
import { useRole } from "../lib/persona";
import { NoAiBadge } from "../monitoring/parts";
import { Avatar, DataTable, PageTitle, RecordId, type Column } from "../monitoring/ui";
import { NewCaseDialog } from "./deals/ClientsPage";

const STAGE_STYLE: Record<Stage, string> = {
  Intake: "bg-sand text-muted",
  Interpretation: "bg-info-tint text-info",
  Clarification: "bg-warn-tint text-warn",
  QC: "bg-[#f4f3ff] text-[#5925dc]",
  Live: "bg-ok-tint text-ok",
};
const STAGE_DOT: Record<Stage, string> = {
  Intake: "bg-stone",
  Interpretation: "bg-info",
  Clarification: "bg-warn",
  QC: "bg-[#7a5af8]",
  Live: "bg-ok",
};

/** Where a case opened on the platform sits in the pipeline's stages. */
const PLATFORM_STAGE: Record<string, Stage> = {
  documents: "Intake",
  terms: "Interpretation",
  rules: "Interpretation",
  mapping: "Interpretation",
  validation: "Interpretation",
  exceptions: "Clarification",
  qc: "QC",
  review: "QC",
  approved: "QC",
  live: "Live",
};

export function StagePill({ stage, label }: { stage: Stage; label?: string }) {
  return (
    <span className={clsx("inline-flex h-[1.375rem] items-center gap-1.5 rounded-full px-2 text-[0.6875rem] font-medium whitespace-nowrap", STAGE_STYLE[stage])}>
      <span aria-hidden className={clsx("size-1.5 rounded-full", STAGE_DOT[stage])} />
      {label ?? stage}
    </span>
  );
}

interface Row {
  key: string;
  ref: string;
  href: string;
  facility: string;
  note: string | null;
  isNew: boolean;
  client: string;
  aiPermitted: boolean;
  dealType: string;
  stage: Stage;
  stageLabel: string;
  daysInStage: number | null;
  owner: string;
  docs: { done: number; total: number } | null;
  docCount: number | null;
  terms: { done: number; total: number };
  exceptions: number;
  queries: number;
  size: number | null;
  active: boolean;
  activity: string | null;
}

function Progress({ done, total }: { done: number; total: number }) {
  if (!total) {
    return <span className="text-xs text-subtle">–</span>;
  }
  const complete = done >= total;
  return (
    <span className="inline-flex w-20 flex-col gap-1">
      <span className={clsx("numeric text-xs", complete ? "text-subtle" : "font-medium text-ink")}>
        {done}/{total}
      </span>
      <span className="h-1 overflow-hidden rounded-full bg-sand">
        <span className={clsx("block h-full rounded-full", complete ? "bg-ok" : "bg-accent")} style={{ width: `${Math.min(100, (done / total) * 100)}%` }} />
      </span>
    </span>
  );
}

function Count({ value, tone }: { value: number; tone: "warn" | "info" }) {
  if (!value) {
    return <span className="numeric text-subtle">0</span>;
  }
  return <span className={clsx("numeric font-semibold", tone === "warn" ? "text-warn" : "text-info")}>{value}</span>;
}

export function CasesPage() {
  const { data, isError, refetch } = useCases();
  const { data: platform } = useDealCases();
  const navigate = useNavigate();
  const role = useRole();
  const [stage, setStage] = useState<Stage | "all">("all");
  const [opening, setOpening] = useState(false);

  const all = useMemo<Row[]>(() => {
    const opened: Row[] = (platform ?? [])
      .filter((c) => !c.archived_at)
      .map((c) => {
        const bucket = PLATFORM_STAGE[c.stage] ?? "Intake";
        return {
          key: `onb-${c.id}`,
          ref: c.ref,
          href: `/deals/cases/${c.id}`,
          facility: c.facility_name,
          note: null,
          isNew: true,
          client: c.client.name,
          aiPermitted: c.client.ai_permitted,
          dealType: c.deal_type,
          stage: bucket,
          stageLabel: STAGE_LABEL[c.stage] ?? bucket,
          daysInStage: null,
          owner: c.created_by,
          docs: null,
          docCount: c.documents,
          terms: { done: c.terms.approved, total: c.terms.total },
          exceptions: c.exceptions_open,
          queries: c.queries_with_client,
          size: c.commitment_cents / 100,
          active: false,
          activity: c.created_at,
        };
      });
    const pipeline: Row[] = (data?.cases ?? []).map((c) => ({
      key: c.number,
      ref: c.number,
      href: casePath(c),
      facility: c.facility,
      note: c.parent ? `Backbook · case ${c.parent}` : null,
      isNew: false,
      client: c.client,
      aiPermitted: true,
      dealType: c.deal_type,
      stage: c.stage,
      stageLabel: c.stage,
      daysInStage: c.business_days_in_stage,
      owner: data ? ownerName(data, c.owner) : c.owner,
      docs: { done: c.documents.received, total: c.documents.expected },
      docCount: null,
      terms: { done: c.terms.approved, total: c.terms.total },
      exceptions: c.exceptions.open,
      queries: c.queries.with_client,
      size: c.pool_balance ?? c.limit_usd,
      active: c.active,
      activity: c.last_activity,
    }));
    return [...opened, ...pipeline];
  }, [data, platform]);

  if (isError) {
    return (
      <Card role="alert" className="p-4 text-sm">
        The case list could not be loaded.{" "}
        <button type="button" className="cursor-pointer font-medium underline" onClick={() => void refetch()}>
          Try again
        </button>
      </Card>
    );
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }
  const rows = all.filter((r) => stage === "all" || r.stage === stage);
  const byStage = (item: Stage) => all.filter((r) => r.stage === item).length;
  const open = all.reduce((n, r) => n + r.exceptions, 0);
  const withClient = all.reduce((n, r) => n + r.queries, 0);
  const clients = new Set(all.map((r) => r.client)).size;

  const columns: Column<Row>[] = [
    {
      key: "ref",
      header: "Case",
      sort: (r) => r.ref,
      render: (r) => <RecordId>{r.ref}</RecordId>,
    },
    {
      key: "facility",
      header: "Facility",
      sort: (r) => r.facility,
      render: (r) => (
        <span className="block min-w-0 max-w-72">
          <span className="flex items-center gap-1.5">
            <span className="truncate font-medium text-ink" title={r.facility}>
              {r.facility}
            </span>
            {r.isNew && <span className="shrink-0 rounded-full bg-accent-tint px-1.5 text-[0.625rem] leading-4 font-medium text-accent-strong">New</span>}
          </span>
          <span className="mt-0.5 flex items-center gap-1.5 text-xs text-subtle">
            <span className="truncate">{r.note ?? `${r.client} · ${r.dealType}`}</span>
            {!r.aiPermitted && <NoAiBadge compact />}
          </span>
        </span>
      ),
    },
    {
      key: "stage",
      header: "Stage",
      sort: (r) => (data.stages as readonly string[]).indexOf(r.stage),
      render: (r) => (
        <span className="block whitespace-nowrap">
          <StagePill stage={r.stage} label={r.stageLabel} />
          {r.daysInStage !== null && <span className="numeric mt-0.5 block text-xs text-subtle">{r.daysInStage} {r.daysInStage === 1 ? "day" : "days"} in stage</span>}
        </span>
      ),
    },
    {
      key: "owner",
      header: "Owner",
      sort: (r) => r.owner,
      render: (r) => (
        <span className="inline-flex" title={r.owner} aria-label={r.owner}>
          <Avatar name={r.owner} size="md" />
        </span>
      ),
    },
    {
      key: "docs",
      header: "Documents",
      sort: (r) => (r.docs ? r.docs.done / Math.max(1, r.docs.total) : r.docCount ?? 0),
      render: (r) => (r.docs ? <Progress done={r.docs.done} total={r.docs.total} /> : <span className="numeric text-xs text-ink-soft">{r.docCount} uploaded</span>),
    },
    {
      key: "terms",
      header: "Terms",
      sort: (r) => r.terms.done / Math.max(1, r.terms.total),
      render: (r) => <Progress done={r.terms.done} total={r.terms.total} />,
    },
    { key: "exceptions", header: "Exceptions", sort: (r) => r.exceptions, align: "right", render: (r) => <Count value={r.exceptions} tone="warn" /> },
    { key: "queries", header: "Queries", sort: (r) => r.queries, align: "right", render: (r) => <Count value={r.queries} tone="info" /> },
    {
      key: "size",
      header: "Size",
      sort: (r) => r.size ?? 0,
      align: "right",
      render: (r) => (r.size === null ? <span className="text-subtle">–</span> : <span className="numeric text-ink-soft">{formatUsdShort(r.size)}</span>),
    },
  ];

  const stages: (Stage | "all")[] = ["all", ...data.stages];
  return (
    <div>
      <PageTitle
        title="Onboarding cases"
        meta={`${all.length} cases · ${clients} clients · ${open} open exceptions · ${withClient} queries with clients · as of ${formatDate(data.as_of)}`}
        actions={
          <ActionButton reason={role === "onboarding_analyst" ? null : "For the onboarding analyst"} onClick={() => setOpening(true)}>
            New case
          </ActionButton>
        }
      />
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(r) => r.key}
        search={(r) => `${r.ref} ${r.facility} ${r.client} ${r.dealType} ${r.owner}`}
        searchPlaceholder="Filter by case, client or facility"
        onRowClick={(r) => navigate(r.href)}
        rowClassName={(r) => (r.active ? "bg-accent-tint/40" : undefined)}
        empty="No cases match."
        toolbar={
          <div role="tablist" aria-label="Stage" className="flex items-center gap-0.5 rounded-lg bg-sand p-0.5">
            {stages.map((item) => (
              <button
                key={item}
                type="button"
                role="tab"
                aria-selected={stage === item}
                onClick={() => setStage(item)}
                className={clsx(
                  "flex h-7 cursor-pointer items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors",
                  stage === item ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink",
                )}
              >
                {item === "all" ? "All" : item}
                <span className="numeric text-[0.6875rem] text-subtle">{item === "all" ? all.length : byStage(item)}</span>
              </button>
            ))}
          </div>
        }
      />
      {opening && <NewCaseDialog open={opening} onOpenChange={setOpening} />}
    </div>
  );
}
