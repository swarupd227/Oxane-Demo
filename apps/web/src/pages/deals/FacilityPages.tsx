/* Facilities that went live from a new case, and their monthly submissions. */
import clsx from "clsx";
import { Download, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ActionButton, Activity, Field, FormMessage, Select, TextInput, useForm, when } from "../../components/deals/parts";
import { PanoramaReceipt } from "../../components/deals/Panorama";
import { HandOffHint } from "../../components/shell/Persona";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Skeleton } from "../../components/ui/layout";
import { post, upload, usd, useDealAction, useFacilities, useFacility, useSubmission, type FacilityView, type Finding, type SubmissionView } from "../../lib/deals";
import { useRole } from "../../lib/persona";
import { NoAiBadge } from "../../monitoring/parts";
import { Badge, DataTable, Kpis, Panel, PageTitle, RecordId, type Column } from "../../monitoring/ui";
import { MappingEditor } from "./DealCasePage";

const SUB_TONE: Record<string, "ok" | "warn" | "danger" | "info" | "neutral"> = { expected: "neutral", received: "info", held: "danger", in_review: "warn", in_approval: "info", released: "ok" };
const SUB_LABEL: Record<string, string> = { expected: "Expected", received: "Received", held: "Load held", in_review: "In review", in_approval: "In approval", released: "Released" };

export function FacilitiesPage() {
  const { data } = useFacilities();
  const navigate = useNavigate();
  const columns: Column<NonNullable<typeof data>[number]>[] = [
    { key: "ref", header: "Facility", sort: (f) => f.ref, render: (f) => <RecordId>{f.ref}</RecordId> },
    { key: "name", header: "Name", sort: (f) => f.name, render: (f) => <span className="flex items-center gap-1.5 font-medium">{f.name}{!f.client.ai_permitted && <NoAiBadge compact />}</span> },
    { key: "client", header: "Client", render: (f) => <span className="text-muted">{f.client.name}</span> },
    { key: "type", header: "Deal type", render: (f) => f.deal_type },
    { key: "commitment", header: "Commitment", align: "right", render: (f) => <span className="numeric">{usd(f.commitment_cents)}</span> },
    { key: "latest", header: "Latest", render: (f) => f.latest ? <span className="flex items-center gap-1.5"><Badge tone={SUB_TONE[f.latest.status]}>{SUB_LABEL[f.latest.status]}</Badge><span className="text-xs text-muted">{f.latest.period}</span></span> : <span className="text-xs text-muted">First month due {f.submissions[0]?.due_date}</span> },
  ];
  return (
    <>
      <PageTitle title="Facilities" meta={data ? `${data.length} onboarded on the platform` : undefined} />
      {!data ? <Skeleton className="h-64 w-full" /> : <DataTable rows={data} columns={columns} rowKey={(f) => String(f.id)} search={(f) => `${f.name} ${f.client.name}`} searchPlaceholder="Filter facilities" onRowClick={(f) => navigate(`/facilities/${f.id}`)} empty="No facility has gone live yet." />}
    </>
  );
}

function EditFacility({ open, onOpenChange, facility }: { open: boolean; onOpenChange: (o: boolean) => void; facility: { id: number; name: string; commitment_cents: number; reporting_day: number | null } }) {
  const form = useForm();
  const action = useDealAction<unknown>();
  const [v, setV] = useState({ name: facility.name, commitment: String(facility.commitment_cents / 100), reporting_day: String(facility.reporting_day ?? 15), reason: "" });
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Edit facility">
      <form noValidate onSubmit={(e) => { e.preventDefault(); void form.run(() => action.mutateAsync(() => post(`/api/deals/facilities/${facility.id}`, { name: v.name, commitment: Number(v.commitment), reporting_day: Number(v.reporting_day), reason: v.reason }, "PATCH"))).then((r) => r && onOpenChange(false)); }}>
        <FormMessage message={form.message} />
        <Field id="f-name" label="Name" error={form.errors.name}><TextInput id="f-name" value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} invalid={Boolean(form.errors.name)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field id="f-commit" label="Commitment (US$)" error={form.errors.commitment}><TextInput id="f-commit" value={v.commitment} onChange={(e) => setV({ ...v, commitment: e.target.value })} invalid={Boolean(form.errors.commitment)} /></Field>
          <Field id="f-day" label="Reporting day" error={form.errors.reporting_day}><TextInput id="f-day" value={v.reporting_day} onChange={(e) => setV({ ...v, reporting_day: e.target.value })} invalid={Boolean(form.errors.reporting_day)} /></Field>
        </div>
        <Field id="f-reason" label="Reason" error={form.errors.reason}><TextInput id="f-reason" value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value })} invalid={Boolean(form.errors.reason)} /></Field>
        <div className="flex justify-end gap-2"><Button size="sm" variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button size="sm" type="submit" disabled={form.busy}>Save</Button></div>
      </form>
    </Dialog>
  );
}

/** What this facility reused (the bank's rule library, the lender's stored mapping) and what
 * was set for it alone. */
function Provenance({ data }: { data: FacilityView }) {
  const p = data.provenance;
  if (!p) {
    return null;
  }
  return (
    <Panel title="Set up from" meta={`${p.library_rules} from ${p.client}'s rule library · ${p.facility_rules} facility-specific`}>
      <dl className="mb-2 grid grid-cols-[10rem_1fr] gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted">Data mapping</dt>
        <dd>{p.mapping.from === "lender_mapping" ? `Reused the lender's stored mapping (layout ${p.mapping.signature}, ${p.mapping.columns} columns)` : `New layout, mapped for this facility and stored for ${p.client} (${p.mapping.columns} columns)`}</dd>
        <dt className="text-muted">Thresholds</dt>
        <dd>Facility-specific: taken from this facility's approved terms</dd>
      </dl>
      <table className="w-full text-xs">
        <tbody>
          {p.rules.map((r) => (
            <tr key={r.id} className="border-b border-sand last:border-0">
              <td className="py-1 pr-2 font-mono font-semibold">{r.id}</td>
              <td className="py-1 pr-2">{r.plain_english}<span className="block font-mono text-[0.6875rem] text-muted">{r.describe}</span></td>
              <td className="py-1 text-right">{r.from === "bank_library" ? <Badge tone="info">Bank library{r.origin ? ` · from ${r.origin.ref}` : ""}</Badge> : <Badge tone="neutral">Facility-specific</Badge>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.bank_library.length > 0 && <p className="mt-2 text-[0.6875rem] text-muted">{p.client}'s library holds {data.bank_library.length} rules from its live facilities; each is reused only where a new agreement states the same clause and threshold.</p>}
    </Panel>
  );
}

export function FacilityPage() {
  const id = Number(useParams().id);
  const { data } = useFacility(id);
  const role = useRole();
  const [edit, setEdit] = useState(false);
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }
  const d = data.config.thresholds.delinquency;
  return (
    <>
      <PageTitle
        title={data.name}
        meta={<span className="flex items-center gap-1.5"><RecordId>{data.ref}</RecordId>{data.client.name} · {data.deal_type} · {usd(data.commitment_cents)} · live since {when(data.live_at)}{data.case_ref && <> · from <Link to={`/deals/cases/${data.case_id}`} className="hover:underline">{data.case_ref}</Link></>}{!data.client.ai_permitted && <NoAiBadge compact />}</span>}
        actions={<ActionButton variant="secondary" reason={role === "monitoring_analyst" || role === "admin" ? null : "For the monitoring analyst or administrator"} onClick={() => setEdit(true)}>Edit facility</ActionButton>}
      />
      <HandOffHint items={data.work} />
      <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <Panel title="Expected submissions" flush>
            <table className="w-full text-[0.8125rem]">
              <thead><tr className="border-b border-line text-left text-xs text-subtle"><th className="px-3 py-1.5">Ref</th><th>Period</th><th>Due</th><th>Status</th><th>Panorama</th><th /></tr></thead>
              <tbody>
                {data.submissions.map((s) => (
                  <tr key={s.id} className="border-b border-sand last:border-0">
                    <td className="px-3 py-1.5"><RecordId>{s.ref}</RecordId></td>
                    <td className="numeric">{s.period}</td>
                    <td className="numeric">{s.due_date}</td>
                    <td><Badge tone={SUB_TONE[s.status]}>{SUB_LABEL[s.status]}</Badge></td>
                    <td className="pr-3 text-right"><Link to={`/facilities/${id}/submissions/${s.id}`} className="text-xs font-medium text-info hover:underline">Open</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          <Panel title="Configuration">
            <dl className="grid grid-cols-[10rem_1fr] gap-x-3 gap-y-1 text-xs">
              <dt className="text-muted">Rule set</dt><dd>v{data.config.rules?.version} · {data.config.rules?.eligibility.length} eligibility, {data.config.rules?.concentration.length} concentration</dd>
              <dt className="text-muted">Delinquency trigger</dt><dd>{d ? `${d.limit_pct}% on ${d.days}+ days, ${d.months}-month average (${d.source})` : "None"}</dd>
              <dt className="text-muted">Loss trigger</dt><dd>{data.config.thresholds.loss ? `${data.config.thresholds.loss.limit_pct}% (${data.config.thresholds.loss.source})` : "None"}</dd>
              <dt className="text-muted">Stored mapping</dt><dd>{data.config.mapping.headers.length} columns</dd>
              <dt className="text-muted">Advance rate</dt><dd>{data.config.terms.advance_rate?.value} ({data.config.terms.advance_rate?.source})</dd>
              <dt className="text-muted">Load file in Panorama</dt><dd>{data.panorama ? <span className="font-mono">Sent to Panorama · receipt {data.panorama}</span> : "Not sent"}</dd>
            </dl>
          </Panel>
          <Provenance data={data} />
        </div>
        <Panel title="Activity"><Activity history={data.history} work={data.work} /></Panel>
      </div>
      {edit && <EditFacility open={edit} onOpenChange={setEdit} facility={data} />}
    </>
  );
}

function FindingRow({ f, sub, call }: { f: Finding; sub: SubmissionView; call: (path: string, body?: unknown) => Promise<unknown> }) {
  const [outcome, setOutcome] = useState(f.suggested.outcome);
  const [note, setNote] = useState("");
  const decided = f.decision;
  return (
    <li className="border-b border-sand py-2.5 last:border-0">
      <div className="flex items-start gap-2">
        <RecordId>{f.ref}</RecordId>
        <div className="min-w-0 flex-1">
          <p className="text-[0.8125rem] font-medium">{f.title}</p>
          <p className="text-xs text-muted">{f.check} · {f.detail}</p>
          <p className="text-xs text-muted">Suggested by {f.suggested.by.toLowerCase()}: {f.suggested.outcome} · {f.suggested.reason}</p>
          {decided && <p className="mt-0.5 text-xs">Decided: {decided.outcome} by {decided.by}{decided.note && ` · ${decided.note}`}{decided.status === "with_expert" && " · waiting on the credit expert"}{decided.expert && ` · expert: ${decided.expert.text} (${decided.expert.by})`}</p>}
        </div>
        {f.severity === "blocking" ? <Badge tone="danger">Blocking</Badge> : <Badge tone="warn">Warning</Badge>}
      </div>
      {!decided && (
        <div className="mt-2 flex items-center gap-2 pl-28">
          <Select aria-label={`Outcome for ${f.ref}`} className="h-8 w-44 text-xs" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="logged">Logged, no alert</option>
            <option value="query">Query to sender</option>
            <option value="confirmed">Confirmed issue</option>
            <option value="expert">Expert review</option>
          </Select>
          <TextInput aria-label={`Reason for ${f.ref}`} className="h-8 flex-1 text-xs" placeholder={outcome === f.suggested.outcome ? "Note (optional)" : "Reason (required)"} value={note} onChange={(e) => setNote(e.target.value)} />
          <ActionButton reason={sub.can.prepare} onClick={() => void call(`triage/${f.ref}`, { outcome, note })}>Decide</ActionButton>
        </div>
      )}
      {decided?.status === "with_expert" && (
        <div className="mt-2 flex items-center gap-2 pl-28">
          <TextInput aria-label={`Expert decision for ${f.ref}`} className="h-8 flex-1 text-xs" placeholder="Decision and reasoning" value={note} onChange={(e) => setNote(e.target.value)} />
          <ActionButton reason={sub.can.expert} onClick={() => void call(`expert/${f.ref}`, { text: note })}>Record decision</ActionButton>
        </div>
      )}
    </li>
  );
}

export function SubmissionPage() {
  const params = useParams();
  const sid = Number(params.sid);
  const { data: sub } = useSubmission(sid);
  const action = useDealAction<SubmissionView>();
  const form = useForm();
  const tape = useRef<HTMLInputElement>(null);
  const report = useRef<HTMLInputElement>(null);
  const [figure, setFigure] = useState({ key: "principal_collections", value: "", page: "" });
  if (!sub) {
    return <Skeleton className="h-96 w-full" />;
  }
  const call = (path: string, body?: unknown) => form.run(() => action.mutateAsync(() => post<SubmissionView>(`/api/deals/submissions/${sid}/${path}`, body)));
  const send = (files: FileList | null, kind: string) => {
    const file = files?.[0];
    if (file) {
      void form.run(() => action.mutateAsync(() => upload<SubmissionView>(`/api/deals/submissions/${sid}/documents`, file, { kind })));
    }
  };
  const s = sub.state;
  const e = s.validation?.engine;
  const t = s.tests ?? {};
  const roll = s.reconciliation?.roll_forward;
  const released = Boolean(s.report?.released_at);
  const prep = sub.can.prepare ?? (released ? "Released" : null);
  return (
    <>
      <PageTitle
        title={`${sub.facility.name} · ${sub.period_label}`}
        meta={<span className="flex items-center gap-1.5"><RecordId>{sub.ref}</RecordId>due {sub.due_date} · <Badge tone={SUB_TONE[sub.status]}>{SUB_LABEL[sub.status]}</Badge>{s.report && <Badge tone={released ? "ok" : "warn"}>{released ? "Released" : "Provisional"}</Badge>}<span>· model cost US${sub.cost.cost_usd.toFixed(2)}</span>{!sub.facility.client.ai_permitted && <NoAiBadge compact />}</span>}
        actions={<Link to={`/facilities/${sub.facility.id}`} className="text-xs font-medium text-info hover:underline">Facility</Link>}
      />
      <HandOffHint items={sub.work} />
      <FormMessage message={form.message} />
      <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <Panel
            title="1. Receive"
            actions={
              <>
                <input ref={tape} type="file" accept=".csv,.xlsx" className="sr-only" aria-label="Choose loan tape" onChange={(x) => send(x.target.files, "loan_tape")} />
                <input ref={report} type="file" accept=".pdf" className="sr-only" aria-label="Choose servicer report" onChange={(x) => send(x.target.files, "servicer_report")} />
                <ActionButton variant="secondary" reason={prep} onClick={() => tape.current?.click()}><Upload aria-hidden className="size-3.5" />Loan tape</ActionButton>
                <ActionButton variant="secondary" reason={prep} onClick={() => report.current?.click()}><Upload aria-hidden className="size-3.5" />Servicer report</ActionButton>
              </>
            }
          >
            <ul className="space-y-1 text-xs">
              {sub.documents.map((d) => <li key={d.id} className={clsx(d.status !== "active" && "text-muted line-through")}><RecordId>{d.ref}</RecordId> {d.name} · {d.kind.replace("_", " ")} · sha256 {d.sha256.slice(0, 12)} · {when(d.uploaded_at)}</li>)}
              {sub.documents.length === 0 && <li className="text-muted">Nothing received yet.</li>}
            </ul>
          </Panel>
          <Panel title="2. Map" actions={<ActionButton reason={prep ?? (sub.documents.some((d) => d.kind === "loan_tape" && d.status === "active") ? null : "Upload the loan tape first")} onClick={() => void call("map")}>Map tape</ActionButton>}>
            {s.mapping ? <p className="text-xs text-muted">{s.mapping.source === "facility" ? "Layout unchanged: the facility's stored mapping was reused, no AI." : `Layout changed (${s.mapping.changed_columns?.join(", ")}): ${s.mapping.source === "ai" ? "AI suggested the changed columns" : "name matching suggested"}; confirm below.`}</p> : <p className="text-xs text-muted">Not mapped yet.</p>}
            <p className="mt-1 text-[0.6875rem] text-muted">Once the mapping is confirmed, validation runs, and if no blocking check fails the calculations and covenant tests run automatically. No button to press.</p>
          </Panel>
          {s.mapping && !s.mapping.confirmed && <MappingEditor key={s.mapping.tape_doc} mapping={s.mapping} disabled={prep} errors={form.errors} onConfirm={(columns, status_map) => void call("mapping", { columns, status_map })} />}
          <Panel
            title="3. Validate, reconcile and test"
            meta={s.runs?.length ? `${s.runs[s.runs.length - 1].trigger === "auto" ? "Ran automatically" : `Re-run by ${s.runs[s.runs.length - 1].by}`} · ${when(s.runs[s.runs.length - 1].at)}` : "Runs automatically after validation"}
            actions={<ActionButton variant="secondary" reason={prep ?? (!s.mapping?.confirmed ? "Confirm the mapping first" : s.validation?.held && !s.hold_released ? "Decide the blocking finding first" : !s.validation ? "Runs automatically once the mapping is confirmed" : null)} onClick={() => void call("process")}>Re-run calculations</ActionButton>}
          >
            {s.hold_released && <p role="status" className="mb-2 rounded bg-warn-tint px-2 py-1 text-xs font-medium">Hold released by {s.hold_released.by} ({s.hold_released.ref}, {s.hold_released.rows} rows excluded). Re-run the calculations.</p>}
            {s.runs && s.runs.length > 0 && (
              <ol aria-label="Runs" className="mb-2 space-y-0.5 text-xs text-muted">
                {s.runs.map((r, i) => <li key={i}>{when(r.at)} · {r.trigger === "auto" ? "Automatic after validation" : "Manual re-run"} by {r.by} · {r.held ? "load held by a blocking check" : `borrowing base ${usd(r.borrowing_base_cents)}`}</li>)}
              </ol>
            )}
            {s.report_figures && (
              <div className="mb-2 text-xs">
                <p className="font-semibold">Servicer report figures</p>
                {Object.entries(s.report_figures).map(([k, f]) => <p key={k}>{k.replace(/_/g, " ")}: {f.value} ({f.document} p.{f.page}) {f.verified ? <Badge tone="ok">verified</Badge> : <Badge tone="danger">not verified</Badge>} <span className="text-muted">{f.source === "ai" ? "AI read" : "Entered"}</span></p>)}
                {!sub.facility.client.ai_permitted && (
                  <div className="mt-1 flex items-end gap-2">
                    <Select aria-label="Figure" className="h-8 w-48 text-xs" value={figure.key} onChange={(x) => setFigure({ ...figure, key: x.target.value })}><option value="principal_collections">Principal collections</option><option value="charge_offs">Charge-offs</option></Select>
                    <TextInput aria-label="Figure value" className="h-8 w-36 text-xs" placeholder="US$" value={figure.value} onChange={(x) => setFigure({ ...figure, value: x.target.value })} invalid={Boolean(form.errors.value)} />
                    <TextInput aria-label="Page" className="h-8 w-16 text-xs" placeholder="Page" value={figure.page} onChange={(x) => setFigure({ ...figure, page: x.target.value })} invalid={Boolean(form.errors.page)} />
                    <ActionButton variant="secondary" reason={prep} onClick={() => void call("figures", figure)}>Enter</ActionButton>
                  </div>
                )}
              </div>
            )}
            {s.validation?.held && <p role="alert" className="rounded bg-danger-tint px-2 py-1 text-xs font-medium text-danger">The load is held by a blocking check. Decide the blocking finding below.</p>}
            {e && (
              <Kpis items={[
                { label: "Pool", value: usd(e.gross_pool_cents) },
                { label: "Eligible", value: usd(e.eligible_pool_cents) },
                { label: "Borrowing base", value: usd(e.borrowing_base_cents) },
                { label: "Delinquency (avg)", value: t.delinquency_average ? `${String(t.delinquency_average)}%` : "–", tone: t.delinquency_breached ? "danger" : t.delinquency_warning ? "warn" : undefined },
                { label: "Trigger", value: t.delinquency_limit ? `${String(t.delinquency_limit)}%` : "–" },
              ]} />
            )}
            {roll && (
              <table className="mt-2 w-full text-xs">
                <tbody>
                  <tr><td className="py-0.5">Opening pool ({s.reconciliation?.prior_period})</td><td className="numeric text-right">{usd(roll.opening_cents as number)}</td></tr>
                  <tr><td className="py-0.5">+ New loans ({String(roll.new_loans)})</td><td className="numeric text-right">{usd(roll.new_cents as number)}</td></tr>
                  <tr><td className="py-0.5">− Principal collections (servicer report)</td><td className="numeric text-right">{usd(roll.collections_cents as number | null)}</td></tr>
                  <tr><td className="py-0.5">− Charge-offs ({String(roll.charged_off_loans)})</td><td className="numeric text-right">{usd(roll.charge_offs_cents as number)}</td></tr>
                  <tr className="border-t border-line"><td className="py-0.5">Expected</td><td className="numeric text-right">{usd(roll.expected_cents as number | null)}</td></tr>
                  <tr><td className="py-0.5">On the tape</td><td className="numeric text-right">{usd(roll.actual_cents as number)}</td></tr>
                  <tr className="font-semibold"><td className="py-0.5">Gap</td><td className="numeric text-right">{usd(roll.gap_cents as number | null)}</td></tr>
                </tbody>
              </table>
            )}
            {t.delinquency_months && <p className="mt-2 text-xs text-muted">Delinquency by month: {t.delinquency_months.map((m) => `${m.period} ${m.value}%`).join(" · ")} ({String(t.delinquency_source ?? "")})</p>}
          </Panel>
          {s.findings && (
            <Panel title="4. Triage" meta={`${s.findings.filter((f) => !f.decision).length} waiting`}>
              {s.findings.length === 0 ? <p className="text-xs text-muted">No findings.</p> : <ul>{s.findings.map((f) => <FindingRow key={f.ref} f={f} sub={sub} call={call} />)}</ul>}
            </Panel>
          )}
          <Panel
            title="5. Report and approvals"
            meta={`${sub.levels.length} levels for ${sub.facility.client.name}`}
            actions={
              <>
                <ActionButton variant="secondary" reason={prep ?? (e ? null : "Calculations have not run yet")} onClick={() => void call("report/draft")}>Draft report</ActionButton>
                <ActionButton reason={sub.can.approve ?? (s.report ? null : "Draft the report first")} onClick={() => void call("approve")}>{sub.next_level ? `Approve, level ${sub.next_level.level}` : "Approve"}</ActionButton>
              </>
            }
          >
            {s.report ? (
              <>
                {s.report.text.map((p, i) => <p key={i} className="mb-1 text-[0.8125rem]">{p}</p>)}
                <p className="text-[0.6875rem] text-muted">{s.report.drafted_by === "ai" ? "Wording drafted by AI; every figure filled by code." : "Code template."}</p>
                <ol className="mt-2 space-y-0.5 text-xs">
                  {sub.levels.map((l) => {
                    const done = s.report?.approvals.find((a) => a.level === l.level);
                    return <li key={l.level} className="flex items-center gap-2"><Badge tone={done ? "ok" : "neutral"}>Level {l.level}</Badge>{l.title}{done && ` · ${done.by} · ${when(done.at)}`}</li>;
                  })}
                </ol>
                {e && <a href={`/api/deals/submissions/${sid}/report.xlsx`} className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-info hover:underline"><Download aria-hidden className="size-3.5" />Lender workbook ({released ? "released" : "provisional"})</a>}
                <PanoramaReceipt sent={s.panorama} what="the released results" />
                {released && s.panorama && !s.panorama.ok && <ActionButton variant="secondary" reason={null} onClick={() => void call("panorama")}>Send to Panorama again</ActionButton>}
              </>
            ) : <p className="text-xs text-muted">Not drafted.</p>}
          </Panel>
        </div>
        <Panel title="Activity"><Activity history={sub.history} work={sub.work} /></Panel>
      </div>
    </>
  );
}
