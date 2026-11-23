import clsx from "clsx";
import { ArrowDownRight, ArrowUpRight, BellPlus, CheckCircle2, Minus, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { SectionLabel, Skeleton } from "../../components/ui/layout";
import { DraftRefusal, Refusal, useAlertDraft, useCycle, useCycleAction, useCycleSession, type AlertDraft, type ClientId, type HeadroomRow } from "../cycle";
import { allHeadroom, deskRows, useScope } from "../desk";
import { NoAiBadge } from "../parts";
import { Badge, DataTable, FilterSelect, fmtUnit, Kpis, PageTitle, Panel, Person, RecordId, SuggestedChip, useWide, when, type Column } from "../ui";

function Room({ row }: { row: HeadroomRow }) {
  const used = Math.min(row.used_pct, 115);
  return (
    <div className="relative h-1.5 w-24 rounded bg-sand" aria-label={`${row.used_pct.toFixed(0)}% of limit used`}>
      <div className={clsx("h-full rounded", !row.passed ? "bg-danger" : row.early_warning ? "bg-warn" : "bg-subtle")} style={{ width: `${(used / 115) * 100}%` }} />
      <span className="absolute -top-0.5 h-2.5 w-0.5 bg-ink" style={{ left: `${(100 / 115) * 100}%` }} />
    </div>
  );
}

const trendIcon = { towards: ArrowUpRight, away: ArrowDownRight, flat: Minus };
const rank = (r: HeadroomRow) => (!r.passed ? 0 : r.early_warning ? 1 : 2);

function DraftResult({ draft, onRequest, busy }: { draft: AlertDraft; onRequest: () => void; busy: boolean }) {
  const top = Math.max(...draft.back_test.map((b) => Math.abs(b.value)), draft.rule ? Math.abs(draft.rule.threshold) : 1) * 1.15;
  return (
    <div className="mt-3 space-y-2">
      <div className="rounded-md bg-canvas p-2.5">
        <p className="flex items-center gap-1.5 text-xs">
          <SuggestedChip by="AI" detail={`Ontology concepts: ${draft.drafted.concepts.join(", ")}`} />
          <span className="font-medium">{draft.drafted.summary}</span>
        </p>
        {draft.rule && (
          <p className="mt-1.5 font-mono text-[0.6875rem]">
            {draft.rule.facility}.{draft.rule.metric} {draft.rule.operator} {draft.rule.threshold.toLocaleString("en-GB")} {draft.rule.unit}
          </p>
        )}
      </div>
      <p className={clsx("flex items-center gap-1.5 text-xs font-semibold", draft.valid ? "text-ok" : "text-danger")}>
        <ShieldCheck aria-hidden className="size-3.5" />
        {draft.valid ? "Rule checks passed" : "Rule rejected"}
      </p>
      {!draft.valid && (
        <ul className="list-disc pl-5 text-xs">
          {draft.problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
      {draft.valid && (
        <div>
          <SectionLabel>Back-test</SectionLabel>
          <div className="mt-1.5 flex h-20 items-end gap-2 border-b border-line px-1" role="img" aria-label="Back-test">
            {draft.back_test.map((b) => (
              <div key={b.period} className="flex h-full flex-1 flex-col justify-end text-center">
                <span className="numeric text-[0.625rem] font-semibold">{fmtUnit(b.value, draft.rule?.unit ?? "%").replace("US$", "")}</span>
                <div className={clsx("mx-auto w-full max-w-10 rounded-t", b.fires ? "bg-danger" : "bg-subtle")} style={{ height: `${(Math.abs(b.value) / top) * 70}%` }} />
              </div>
            ))}
          </div>
          <div className="mt-1 flex gap-2 px-1">
            {draft.back_test.map((b) => (
              <span key={b.period} className="flex-1 text-center text-[0.625rem] text-muted">
                {b.period}
              </span>
            ))}
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs">
              Fired in <strong className="numeric">{draft.fires}</strong> of {draft.back_test.length} periods
            </span>
            <Button size="sm" onClick={onRequest} disabled={busy}>
              <BellPlus aria-hidden className="size-3.5" />
              Submit request
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function MonitorPage() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const { client: scope } = useScope();
  const action = useCycleAction();
  const drafting = useAlertDraft();
  const [clientId, setClientId] = useState<ClientId>("calderwood");
  const [state, setState] = useState("all");
  const wide = useWide();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const desk = deskRows(cycle, session);
  const facilityOf = Object.fromEntries(desk.map((f) => [f.id, f]));
  const rows = allHeadroom(cycle).filter((r) => scope === "all" || facilityOf[r.facility]?.client === scope);
  const shown = rows.filter((r) => state === "all" || (state === "over" ? !r.passed : state === "near" ? r.passed && r.early_warning : r.passed && !r.early_warning));
  const client = cycle.clients.find((c) => c.id === clientId)!;
  const alerts = cycle.alerts[clientId];
  const draft = drafting.data && drafting.data.client === clientId ? drafting.data : null;
  const requests = (session?.alerts ?? []).filter((a) => a.client === clientId);
  const ask = (request: string) => {
    setText(request);
    setError(null);
    drafting.mutate({ client: clientId, request }, { onError: (e) => setError(e instanceof DraftRefusal ? e.message : "The request could not be drafted.") });
  };
  const send = () => {
    if (!draft?.rule) {
      return;
    }
    setError(null);
    action.mutate(
      { type: "request-alert", as: "client", payload: { client: clientId, request: draft.request, rule: draft.rule, summary: draft.drafted.summary, fires: draft.fires } },
      { onSuccess: () => drafting.reset(), onError: (e) => setError(e instanceof Refusal ? e.message : "The request could not be sent.") },
    );
  };
  const columns: Column<HeadroomRow>[] = [
    { key: "facility", header: "Facility", sort: (r) => facilityOf[r.facility]?.name ?? r.facility, render: (r) => <span className="whitespace-nowrap">{facilityOf[r.facility]?.name}</span> },
    {
      key: "test",
      header: "Test",
      sort: (r) => r.test,
      render: (r) => (
        <span className="block max-w-72">
          {r.test}
          {r.note && <span className="block truncate text-[0.6875rem] text-muted">{r.note}</span>}
        </span>
      ),
    },
    { key: "clause", header: "Clause", render: (r) => <span className="text-xs whitespace-nowrap text-muted">{r.clause}</span> },
    { key: "value", header: "Value", align: "right", render: (r) => <span className="numeric font-medium">{fmtUnit(r.value, r.unit)}</span> },
    { key: "limit", header: "Limit", align: "right", render: (r) => <span className="numeric whitespace-nowrap text-muted">{r.direction === "max" ? "≤" : "≥"} {fmtUnit(r.limit, r.unit)}</span> },
    { key: "headroom", header: "Headroom", align: "right", render: (r) => <span className={clsx("numeric", !r.passed && "font-semibold text-danger")}>{fmtUnit(r.headroom, r.unit)}</span> },
    { key: "used", header: "Used", sort: (r) => r.used_pct, render: (r) => <Room row={r} /> },
    {
      key: "trend",
      header: "Trend",
      sort: (r) => r.trend,
      render: (r) => {
        const Trend = trendIcon[r.trend];
        return (
          <span className={clsx("inline-flex items-center gap-1 text-xs whitespace-nowrap", r.trend === "towards" ? "text-warn" : "text-muted")}>
            <Trend aria-hidden className="size-3.5" />
            {wide ? r.series.map((s) => fmtUnit(s.value, r.unit).replace("US$", "")).join(" → ") : r.trend === "towards" ? "Towards" : r.trend === "away" ? "Away" : "Flat"}
          </span>
        );
      },
    },
    {
      key: "status",
      header: "Status",
      sort: rank,
      render: (r) => (!r.passed ? <Badge tone="danger">Over limit</Badge> : r.early_warning ? <Badge tone="warn">Early warning</Badge> : <Badge tone="ok">Within</Badge>),
    },
  ];
  return (
    <>
      <PageTitle title="Alerts" meta={`${cycle.cycle.label} · ${rows.length} tests across ${new Set(rows.map((r) => r.facility)).size} facilities`} />
      <Kpis
        items={[
          { label: "Tests", value: rows.length },
          { label: "Over limit", value: rows.filter((r) => !r.passed).length, tone: "danger", onClick: () => setState("over") },
          { label: "Early warning", value: rows.filter((r) => r.passed && r.early_warning).length, tone: "warn", onClick: () => setState("near") },
          { label: "Within limit", value: rows.filter((r) => r.passed && !r.early_warning).length, tone: "ok", onClick: () => setState("within") },
          { label: "Indicators", value: cycle.early_warnings.length },
          { label: "Live client alerts", value: (session?.alerts ?? []).filter((a) => a.status === "live").length },
        ]}
      />
      <DataTable
        title="Covenant headroom"
        rows={shown}
        columns={wide ? columns : columns.filter((c) => c.key !== "clause")}
        rowKey={(r) => `${r.facility}-${r.test}`}
        search={(r) => `${facilityOf[r.facility]?.name} ${r.test} ${r.clause}`}
        searchPlaceholder="Filter tests"
        initialSort={{ key: "status", dir: "asc" }}
        pageSize={15}
        rowClassName={(r) => (!r.passed ? "bg-danger-tint/30" : undefined)}
        toolbar={
          <FilterSelect
            label="Status"
            value={state}
            onChange={setState}
            options={[
              { value: "all", label: "All statuses" },
              { value: "over", label: "Over limit" },
              { value: "near", label: "Early warning" },
              { value: "within", label: "Within" },
            ]}
          />
        }
      />
      <div className="mt-3 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3">
        <Panel title="Early-warning indicators" meta={`${cycle.early_warnings.length} open`} flush>
          <table className="w-full text-left text-[0.8125rem]">
            <tbody>
              {cycle.early_warnings.map((w) => (
                <tr key={`${w.kind}-${w.subject}`} className="border-b border-sand last:border-0">
                  <td className="px-3 py-1.5 whitespace-nowrap">
                    <Badge tone="warn">{w.kind}</Badge>
                  </td>
                  <td className="px-3 py-1.5 whitespace-nowrap">{facilityOf[w.facility]?.name.split(" ")[0]}</td>
                  <td className="px-3 py-1.5 font-medium">{w.subject}</td>
                  <td className="px-3 py-1.5 text-xs text-muted">{w.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <div className="space-y-3">
          <Panel
            title="Client alert requests"
            actions={
              <div role="tablist" aria-label="Client" className="flex rounded-md border border-line p-0.5">
                {cycle.clients.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    role="tab"
                    aria-selected={clientId === c.id}
                    onClick={() => {
                      setClientId(c.id);
                      setError(null);
                      drafting.reset();
                    }}
                    className={clsx("h-6 cursor-pointer rounded px-2 text-xs", clientId === c.id ? "bg-accent-tint text-accent-strong font-medium" : "text-muted hover:text-ink")}
                  >
                    {c.name.split(" ")[0]}
                  </button>
                ))}
              </div>
            }
          >
            {!alerts.ai_permitted ? (
              <div className="space-y-1.5 text-xs">
                <NoAiBadge compact />
                <p>{client.ai_note}</p>
                <p className="text-muted">
                  Alerts maintained by <Person name={client.contact.name} />.
                </p>
              </div>
            ) : (
              <>
                <label htmlFor="alert-request" className="flex items-center gap-1.5 text-xs font-medium">
                  <Person name={client.client_contact.name} sub={client.client_contact.role} />
                </label>
                <textarea id="alert-request" value={text} onChange={(e) => setText(e.target.value)} rows={2} className="mt-1.5 w-full rounded-md border border-line px-2 py-1.5 text-[0.8125rem]" placeholder="Alert request" />
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {alerts.presets.map((p) => (
                    <button key={p.request} type="button" onClick={() => ask(p.request)} className="cursor-pointer rounded-full border border-line px-2 py-0.5 text-left text-[0.6875rem] hover:border-stone">
                      {p.request}
                    </button>
                  ))}
                </div>
                <div className="mt-2 flex justify-end">
                  <Button size="sm" disabled={!text.trim() || drafting.isPending} onClick={() => ask(text)}>
                    Draft rule
                  </Button>
                </div>
                {error && (
                  <p role="alert" className="mt-1.5 text-xs text-danger">
                    {error}
                  </p>
                )}
                {draft && <DraftResult draft={draft} onRequest={send} busy={action.isPending} />}
              </>
            )}
          </Panel>
          {requests.length > 0 && (
            <Panel title="Requests" meta={`${requests.length}`} flush>
              <ul>
                {requests.map((a) => (
                  <li key={a.id} className="flex items-start gap-3 border-b border-sand px-3 py-2 text-[0.8125rem] last:border-0">
                    <RecordId>ALR-{String(a.id).padStart(4, "0")}</RecordId>
                    <span className="min-w-0 flex-1">
                      <span className="block font-medium">{a.summary ?? a.request}</span>
                      <span className="block text-xs text-muted">
                        Requested {when(a.requestedAt)} · back-test fired {a.fires ?? 0}×{a.status === "live" ? ` · approved by ${a.approvedBy}` : ""}
                      </span>
                    </span>
                    {a.status === "live" ? (
                      <Badge tone="ok" icon={<CheckCircle2 aria-hidden className="size-3" />}>
                        Live
                      </Badge>
                    ) : (
                      <Button size="sm" variant="secondary" disabled={action.isPending} onClick={() => action.mutate({ type: "approve-alert", as: "analyst", payload: { alert: a.id } })}>
                        Approve
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
