import clsx from "clsx";
import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { usd, useFacilities, type FacilitySummary } from "../../lib/deals";
import { Skeleton } from "../../components/ui/layout";
import { useCycle, useCycleSession, type Cycle, type CycleSession } from "../cycle";
import { allSubmissions, deskRows, REPORT_LABEL, useScope, type DeskRow } from "../desk";
import { NoAiBadge, OutcomePill } from "../parts";
import { useReuse } from "./ReuseView";
import { SCHEDULE_STATUS } from "./Schedules";
import { Activity, Badge, DataTable, FilterSelect, fmtUnit, Kpis, PageTitle, Person, RecordId, useWide, when, type Column, type Tone } from "../ui";

const STATUS: Record<DeskRow["status"], { label: string; tone: Tone }> = {
  breach: { label: "Breach", tone: "danger" },
  watch: { label: "Watch", tone: "warn" },
  ok: { label: "On track", tone: "ok" },
};
const REPORT_TONE: Record<DeskRow["report"]["status"], Tone> = { released: "ok", in_review: "info", preparing: "neutral", provisional: "warn", held: "danger" };
const SEVERITY = { breach: 0, watch: 1, ok: 2 };

/** A facility onboarded on the platform, as a desk row. Its own page holds the detail. */
function dealRow(f: FacilitySummary): DeskRow {
  const latest = f.latest;
  const limit = latest?.delinquency_limit ? Number(latest.delinquency_limit) : null;
  const tests = latest?.delinquency_average && limit !== null
    ? [{ test: "Delinquency, rolling average", value: Number(latest.delinquency_average), limit, unit: "%", direction: "max" as const, passed: !latest.breached, early_warning: latest.warning, headroom: limit - Number(latest.delinquency_average) }]
    : [];
  const released = latest?.status === "released";
  return {
    id: `deal-${f.id}`,
    name: f.name,
    client: `deal:${f.client.id}` as DeskRow["client"],
    client_name: f.client.name,
    ai_permitted: f.client.ai_permitted,
    type: f.deal_type,
    asset_class: f.deal_type,
    role: "Calculation agent",
    size: usd(f.commitment_cents).replace(".00", ""),
    analyst: "Priya Raman",
    reporting: "Monthly",
    period: latest?.period ?? f.submissions[0]?.period ?? "",
    worked: true,
    documents: { received: f.submissions.filter((s) => s.status !== "expected").length, total: f.submissions.length, late: 0 },
    tests: tests as DeskRow["tests"],
    breaches: tests.filter((t) => !t.passed).length,
    warnings: tests.filter((t) => t.early_warning).length,
    open: latest?.open ?? 0,
    exceptions: latest?.open ?? 0,
    status: tests.some((t) => !t.passed) ? "breach" : tests.some((t) => t.early_warning) || latest?.open ? "watch" : "ok",
    report: { status: released ? "released" : latest ? "in_review" : "preparing", done: 0, levels: f.client.approval_levels, at: null, by: null },
    trend: null,
  };
}

function Spark({ row }: { row: DeskRow }) {
  if (!row.trend || row.trend.series.length < 2) {
    return null;
  }
  const values = row.trend.series.map((s) => s.value);
  const top = Math.max(...values.map(Math.abs)) || 1;
  return (
    <span aria-hidden className="flex h-4 items-end gap-0.5">
      {values.map((v, i) => (
        <span key={i} className="w-1.5 rounded-sm bg-subtle/60" style={{ height: `${Math.max(15, (Math.abs(v) / top) * 100)}%` }} />
      ))}
    </span>
  );
}

function Drawer({ row, cycle, session, onClose }: { row: DeskRow; cycle: Cycle; session: CycleSession | undefined; onClose: () => void }) {
  const subs = allSubmissions(cycle).filter((s) => s.facility === row.id);
  const findings = cycle.findings.filter((f) => f.facility.split(",").includes(row.id));
  const ids = new Set([row.id, ...findings.map((f) => f.id)]);
  const audit = (session?.audit ?? []).filter((a) => a.subject && ids.has(a.subject));
  const book = cycle.book?.facilities.find((f) => f.id === row.id);
  const schedule = cycle.schedules?.find((s) => s.facility === row.id);
  const reuse = useReuse().data?.facilities.find((f) => f.facility === row.id);
  const origin = book
    ? [
        ...(book.report.prepared ? [{ at: book.report.prepared.at, by: book.report.prepared.by, text: "Report prepared" }] : []),
        ...book.report.approvals.map((a) => ({ at: a.at, by: a.by, text: `Approved at level ${a.level}${a.level === book.report.levels ? ": released" : ""}` })),
      ].reverse()
    : [];
  const received = subs
    .filter((s) => s.received)
    .map((s) => ({ at: s.received!, by: s.channel, text: `Received ${s.label.toLowerCase()} (${s.ref})` }))
    .sort((a, b) => b.at.localeCompare(a.at));
  return (
    <aside aria-label={`${row.name} details`} className="self-start rounded-lg border border-line bg-surface">
      <div className="flex items-start justify-between gap-2 border-b border-line px-3 py-2">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">{row.name}</h2>
          <p className="text-xs text-muted">
            {row.client_name} · {row.role}
          </p>
        </div>
        <button type="button" aria-label="Close" onClick={onClose} className="cursor-pointer rounded p-1 text-muted hover:bg-sand">
          <X aria-hidden className="size-4" />
        </button>
      </div>
      <dl className="grid grid-cols-[6.5rem_1fr] gap-x-2 gap-y-1 px-3 py-2 text-xs">
        <dt className="text-muted">Type</dt>
        <dd>{row.type}</dd>
        <dt className="text-muted">Asset class</dt>
        <dd className="flex items-center gap-1.5">
          {row.asset_class}
          {!row.ai_permitted && <NoAiBadge compact />}
        </dd>
        <dt className="text-muted">Commitment</dt>
        <dd className="numeric">{row.size}</dd>
        <dt className="text-muted">Reporting</dt>
        <dd>
          {row.reporting} · {row.period}
        </dd>
        <dt className="text-muted">Analyst</dt>
        <dd>
          <Person name={row.analyst} />
        </dd>
        <dt className="text-muted">Report</dt>
        <dd className="flex items-center gap-1.5">
          <Badge tone={REPORT_TONE[row.report.status]}>{REPORT_LABEL[row.report.status]}</Badge>
          <span className="numeric text-muted">
            {row.report.done}/{row.report.levels} levels
          </span>
        </dd>
        {reuse && (
          <>
            <dt className="text-muted">Set up from</dt>
            <dd>
              {reuse.counts.library_rules} rules from the bank's library · {reuse.counts.facility_rules} facility-specific · {reuse.counts.reused_layouts} layouts reused ·{" "}
              <Link to="/monitoring/mapping?view=reuse" className="text-info hover:underline">Reuse</Link>
            </dd>
          </>
        )}
      </dl>
      <div className="border-t border-line px-3 py-2">
        <p className="mb-1 text-[0.6875rem] font-semibold text-muted">Tests</p>
        <table className="w-full text-xs">
          <tbody>
            {row.tests.map((t) => (
              <tr key={t.test} className="border-b border-sand last:border-0">
                <td className="py-1 pr-2">{t.test}</td>
                <td className="numeric py-1 pr-2 text-right font-medium">{fmtUnit(t.value, t.unit)}</td>
                <td className="numeric py-1 pr-2 text-right whitespace-nowrap text-muted">
                  {t.direction === "max" ? "≤" : "≥"} {fmtUnit(t.limit, t.unit)}
                </td>
                <td className="py-1 text-right">
                  {!t.passed ? <Badge tone="danger">Over</Badge> : t.early_warning ? <Badge tone="warn">Near</Badge> : <Badge tone="ok">Pass</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="border-t border-line px-3 py-2">
        <p className="mb-1 text-[0.6875rem] font-semibold text-muted">Files</p>
        <ul className="space-y-0.5 text-xs">
          {subs.map((s) => (
            <li key={s.ref} className="flex items-center gap-2">
              <RecordId>{s.ref}</RecordId>
              <span className="min-w-0 flex-1 truncate">{s.label}</span>
              <span className={clsx("numeric", s.status === "late" ? "font-semibold text-danger" : "text-muted")}>{s.status === "late" ? "Overdue" : s.received ? when(s.received) : s.reused ? "Reused" : "–"}</span>
            </li>
          ))}
        </ul>
      </div>
      {schedule && (
        <div className="border-t border-line px-3 py-2">
          <p className="mb-1 flex items-center justify-between text-[0.6875rem] font-semibold text-muted">
            Document schedule
            <Link to="/monitoring/submissions?view=schedules" className="font-medium text-info hover:underline">
              {schedule.template}
            </Link>
          </p>
          <table className="w-full text-xs">
            <tbody>
              {schedule.lines.map((line) => (
                <tr key={line.document} className="border-b border-sand last:border-0">
                  <td className="py-1 pr-2">
                    {line.document}
                    <span className="block text-[0.6875rem] text-muted">
                      {line.format} · {line.frequency} · {line.channel}
                    </span>
                  </td>
                  <td className="numeric py-1 pr-2 text-right text-muted">{line.expected ? `${line.received}/${line.expected}` : "–"}</td>
                  <td className="py-1 text-right">
                    <Badge tone={SCHEDULE_STATUS[line.status].tone}>{SCHEDULE_STATUS[line.status].label}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {findings.length > 0 && (
        <div className="border-t border-line px-3 py-2">
          <p className="mb-1 text-[0.6875rem] font-semibold text-muted">Exceptions</p>
          <ul className="space-y-1 text-xs">
            {findings.map((f) => (
              <li key={f.id} className="flex items-center gap-2">
                <Link to={`/monitoring/triage?ref=${f.ref}`} className="font-mono text-[0.6875rem] text-info hover:underline">
                  {f.ref}
                </Link>
                <span className="min-w-0 flex-1 truncate">{f.title}</span>
                <OutcomePill outcome={session?.decisions[f.id] ?? null} pending="Open" />
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="border-t border-line px-3 py-2">
        <p className="mb-1.5 text-[0.6875rem] font-semibold text-muted">Activity</p>
        <Activity entries={audit} origin={[...origin, ...received]} />
      </div>
    </aside>
  );
}

export function PortfolioPage() {
  const { data: cycle, isPending } = useCycle();
  const { data: session } = useCycleSession();
  const { client } = useScope();
  const [params, setParams] = useSearchParams();
  const [asset, setAsset] = useState("all");
  const [status, setStatus] = useState("all");
  const selected = params.get("facility");
  const wide = useWide();
  const { data: onboarded } = useFacilities();
  const navigate = useNavigate();
  const rows = useMemo(() => [...(cycle ? deskRows(cycle, session) : []), ...(onboarded ?? []).filter((f) => f.status === "live").map(dealRow)], [cycle, session, onboarded]);
  if (isPending || !cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const scoped = rows.filter((r) => client === "all" || r.client === client);
  const shown = scoped.filter((r) => (asset === "all" || r.asset_class === asset) && (status === "all" || r.status === status));
  const assets = [...new Set(rows.map((r) => r.asset_class))].sort();
  const subs = allSubmissions(cycle).filter((s) => scoped.some((r) => r.id === s.facility));
  const row = rows.find((r) => r.id === selected);
  const select = (id: string | null) => setParams(id ? { facility: id } : {}, { replace: true });
  const short = (name: string) => name.replace(" Bank plc", "").replace(" Bank N.A.", "");
  const columns: Column<DeskRow>[] = [
    {
      key: "name",
      header: "Facility",
      sort: (r) => r.name,
      render: (r) => (
        <span className="flex items-center gap-1.5">
          <span className="font-medium">{r.name}</span>
          {!r.ai_permitted && <NoAiBadge compact />}
        </span>
      ),
    },
    { key: "client", header: "Client", sort: (r) => r.client_name, render: (r) => <span className="text-muted">{short(r.client_name)}</span> },
    { key: "asset", header: "Asset class", sort: (r) => r.asset_class, render: (r) => <span className="whitespace-nowrap">{r.asset_class}</span> },
    { key: "size", header: "Commitment", sort: (r) => parseFloat(r.size.replace(/[^\d.]/g, "")), align: "right", render: (r) => <span className="numeric">{r.size.replace(" drawn", "")}</span> },
    { key: "analyst", header: "Analyst", sort: (r) => r.analyst, render: (r) => <Person name={r.analyst} /> },
    {
      key: "files",
      header: "Files",
      sort: (r) => r.documents.late * 100 + r.documents.total - r.documents.received,
      render: (r) => (
        <span className="numeric inline-flex items-center gap-1.5 whitespace-nowrap">
          {r.documents.received}/{r.documents.total}
          {r.documents.late > 0 && <Badge tone="danger">{r.documents.late} overdue</Badge>}
        </span>
      ),
    },
    {
      key: "test",
      header: "Lead test",
      render: (r) =>
        r.trend ? (
          <span className="flex items-center gap-2 whitespace-nowrap">
            <Spark row={r} />
            <span className="max-w-44 truncate text-muted">{r.trend.label.replace(", three-month average", " (3m)")}</span>
            <span className="numeric font-medium">{fmtUnit(r.trend.series.at(-1)!.value, r.trend.unit)}</span>
          </span>
        ) : null,
    },
    {
      key: "status",
      header: "Status",
      sort: (r) => SEVERITY[r.status],
      render: (r) => (
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <Badge tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge>
          <span className="numeric text-xs text-muted">
            {r.tests.filter((t) => t.passed).length}/{r.tests.length}
          </span>
        </span>
      ),
    },
    { key: "open", header: "Open exc.", sort: (r) => r.open, align: "right", render: (r) => <span className={clsx("numeric", r.open ? "font-semibold" : "text-muted")}>{r.open}</span> },
    {
      key: "report",
      header: "Report",
      sort: (r) => r.report.status,
      render: (r) => (
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <Badge tone={REPORT_TONE[r.report.status]}>{REPORT_LABEL[r.report.status]}</Badge>
          {r.report.at && <span className="numeric text-xs text-muted">{when(r.report.at.slice(0, 10))}</span>}
        </span>
      ),
    },
  ];
  return (
    <>
      <PageTitle title="Portfolio" meta={`${cycle.cycle.label} · period end ${when(cycle.cycle.period_end)}`} />
      <Kpis
        items={[
          { label: "Facilities", value: scoped.length },
          { label: "Files received", value: `${subs.filter((s) => s.received || s.reused).length}/${subs.length}`, tone: subs.some((s) => s.status === "late") ? "danger" : undefined },
          { label: "Open exceptions", value: cycle.findings.filter((f) => !f.rule_outcome && !session?.decisions[f.id] && f.facility.split(",").some((id) => scoped.some((r) => r.id === id))).length },
          { label: "Tests over limit", value: scoped.reduce((n, r) => n + r.breaches, 0), tone: scoped.some((r) => r.breaches) ? "danger" : "ok" },
          { label: "Early warnings", value: scoped.reduce((n, r) => n + r.warnings, 0), tone: scoped.some((r) => r.warnings) ? "warn" : undefined },
          { label: "Reports released", value: `${scoped.filter((r) => r.report.status === "released").length}/${scoped.length}` },
        ]}
      />
      <div className={clsx("grid gap-3", row ? "grid-cols-[minmax(0,1fr)_22rem]" : "grid-cols-1")}>
        <DataTable
          rows={shown}
          columns={row ? columns.filter((c) => !["client", "size", "analyst", "test"].includes(c.key)) : wide ? columns : columns.filter((c) => !["client", "size"].includes(c.key))}
          rowKey={(r) => r.id}
          search={(r) => `${r.name} ${r.client_name} ${r.asset_class} ${r.analyst} ${r.type}`}
          searchPlaceholder="Filter facilities"
          initialSort={{ key: "name", dir: "asc" }}
          onRowClick={(r) => (r.id.startsWith("deal-") ? navigate(`/facilities/${r.id.slice(5)}`) : select(r.id === selected ? null : r.id))}
          selected={selected}
          toolbar={
            <>
              <FilterSelect label="Asset class" value={asset} onChange={setAsset} options={[{ value: "all", label: "All asset classes" }, ...assets.map((a) => ({ value: a, label: a }))]} />
              <FilterSelect
                label="Status"
                value={status}
                onChange={setStatus}
                options={[
                  { value: "all", label: "All statuses" },
                  { value: "breach", label: "Breach" },
                  { value: "watch", label: "Watch" },
                  { value: "ok", label: "On track" },
                ]}
              />
            </>
          }
        />
        {row && <Drawer row={row} cycle={cycle} session={session} onClose={() => select(null)} />}
      </div>
    </>
  );
}

