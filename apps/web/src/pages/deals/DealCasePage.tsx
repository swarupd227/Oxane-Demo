/* One new onboarding case, from documents to go-live. Every check and figure comes from the API. */
import clsx from "clsx";
import { Download, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ActionButton, Activity, EXC_LABEL, Field, FormMessage, Select, STATUS_TONE, Tabs, TextInput, useForm, when } from "../../components/deals/parts";
import { PanoramaReceipt } from "../../components/deals/Panorama";
import { HandOffHint } from "../../components/shell/Persona";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Skeleton } from "../../components/ui/layout";
import {
  KIND_LABEL,
  post,
  STAGE_LABEL,
  upload,
  usd,
  useDealAction,
  useDealCase,
  useDealsStatus,
  type CaseException,
  type CaseView,
  type Rule,
  type Term,
} from "../../lib/deals";
import { NoAiBadge } from "../../monitoring/parts";
import { Badge, Kpis, Panel, PageTitle, RecordId } from "../../monitoring/ui";
import { DEAL_TYPES } from "./ClientsPage";

type Act = ReturnType<typeof useActions>;

function useActions(id: number) {
  const action = useDealAction<CaseView>();
  const form = useForm();
  const call = (path: string, body?: unknown, method?: string) => form.run(() => action.mutateAsync(() => post<CaseView>(`/api/deals/cases/${id}/${path}`, body, method)));
  return { form, call, action };
}

function Stages({ view }: { view: CaseView }) {
  const at = view.stages.indexOf(view.stage);
  return (
    <ol aria-label="Stage" className="mb-3 flex flex-wrap gap-1 text-[0.6875rem]">
      {view.stages.map((s, i) => (
        <li key={s} className={clsx("rounded px-1.5 py-0.5", i < at ? "bg-ok-tint text-ok" : i === at ? "bg-ink font-semibold text-white" : "bg-sand text-muted")} aria-current={i === at ? "step" : undefined}>
          {STAGE_LABEL[s]}
        </li>
      ))}
    </ol>
  );
}

function Documents({ view, act }: { view: CaseView; act: Act }) {
  const status = useDealsStatus().data;
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState(view.client.ai_permitted ? "auto" : "agreement");
  const [effective, setEffective] = useState("");
  const blocked = view.can.prepare ?? (status && !status.access_configured ? "Uploads are switched off on this environment" : null);
  const send = (files: FileList | null) => {
    if (!files) {
      return;
    }
    void act.form.run(async () => {
      for (const file of Array.from(files)) {
        await act.action.mutateAsync(() => upload<CaseView>(`/api/deals/cases/${view.id}/documents`, file, { kind, ...(effective ? { effective_date: effective } : {}) }));
      }
    });
  };
  const replace = (doc: number, files: FileList | null) => {
    const file = files?.[0];
    if (file) {
      void act.form.run(() => act.action.mutateAsync(() => upload<CaseView>(`/api/deals/cases/${view.id}/documents/${doc}/replace`, file, {})));
    }
  };
  const docs = view.documents_list.filter((d) => d.status === "active");
  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Panel
        title="Documents"
        meta={`${docs.length} active`}
        actions={
          <ActionButton variant="secondary" reason={view.can.prepare ?? view.can.ai ?? (docs.some((d) => d.kind === "auto") ? null : "Every document has a type")} onClick={() => void act.call("classify")}>
            Classify with AI
          </ActionButton>
        }
      >
        <table className="w-full text-[0.8125rem]">
          <thead>
            <tr className="border-b border-line text-left text-xs text-subtle">
              <th className="py-1.5">Document</th>
              <th>Type</th>
              <th>Version</th>
              <th>Effective</th>
              <th className="text-right">Size</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {view.documents_list.map((d) => (
              <tr key={d.id} className={clsx("border-b border-sand last:border-0", d.status !== "active" && "text-muted line-through")}>
                <td className="py-1.5">
                  <a href={`/api/deals/documents/${d.id}/file`} target="_blank" rel="noreferrer" className="font-medium hover:underline">{d.name}</a>
                  <span className="block font-mono text-[0.6875rem] text-muted">{d.ref} · sha256 {d.sha256.slice(0, 12)} · {d.uploaded_by}</span>
                </td>
                <td>
                  {d.status === "active" ? (
                    <Select aria-label={`Type of ${d.name}`} value={d.kind} disabled={Boolean(view.can.prepare)} onChange={(e) => void act.call(`documents/${d.id}`, { kind: e.target.value }, "PATCH")} className="h-7 w-36 text-xs">
                      {Object.entries(KIND_LABEL).filter(([k]) => k !== "auto" || d.kind === "auto").map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </Select>
                  ) : d.status}
                  {d.kind_source === "ai" && <span className="ml-1 text-[0.6875rem] text-muted">AI</span>}
                </td>
                <td className="numeric">v{d.version}</td>
                <td className="numeric">{d.effective_date ?? "–"}</td>
                <td className="numeric text-right">{(d.size / 1024).toFixed(0)} KB</td>
                <td className="pl-2 text-right whitespace-nowrap">
                  {d.status === "active" && !view.can.prepare && (
                    <>
                      <label className="cursor-pointer text-xs text-info hover:underline">
                        Replace
                        <input type="file" className="sr-only" accept=".pdf,.csv,.xlsx" onChange={(e) => replace(d.id, e.target.files)} />
                      </label>
                      <button type="button" className="ml-2 cursor-pointer text-xs text-danger hover:underline" onClick={() => void act.call(`documents/${d.id}`, undefined, "DELETE")}>
                        Remove
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {view.documents_list.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-muted">No documents yet.</td></tr>}
          </tbody>
        </table>
      </Panel>
      <Panel title="Upload">
        <Field id="upload-kind" label="Type">
          <Select id="upload-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
            {Object.entries(KIND_LABEL).filter(([k]) => view.client.ai_permitted || k !== "auto").map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </Select>
        </Field>
        <Field id="upload-effective" label="Effective date (optional)">
          <TextInput id="upload-effective" type="date" value={effective} onChange={(e) => setEffective(e.target.value)} />
        </Field>
        <input ref={input} type="file" multiple accept=".pdf,.csv,.xlsx" className="sr-only" aria-label="Choose files" onChange={(e) => send(e.target.files)} />
        <ActionButton reason={blocked} onClick={() => input.current?.click()}>
          <Upload aria-hidden className="size-3.5" />
          Choose files
        </ActionButton>
        <p className="mt-2 text-[0.6875rem] text-muted">PDF, CSV or XLSX, up to {status?.max_upload_mb ?? 20} MB each.</p>
      </Panel>
    </div>
  );
}

function TermRow({ term, view, act }: { term: Term; view: CaseView; act: Act }) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({ value: term.value ?? "", document: term.doc_name ?? "", page: term.page ? String(term.page) : "", quote: term.quote ?? "", reason: "", effective_from: term.effective_from ?? "" });
  const pdfs = view.documents_list.filter((d) => d.status === "active" && d.name.toLowerCase().endsWith(".pdf"));
  const action = term.status === "missing" || term.source === "analyst" && term.status !== "approved" ? "enter" : "edit";
  const local = useForm();
  const save = () =>
    void local.run(() => act.action.mutateAsync(() => post<CaseView>(`/api/deals/cases/${view.id}/terms/${term.key}`, { action, ...values, page: values.page ? Number(values.page) : null, quote: values.quote || null, basis_days: term.key === "delinquency_trigger" ? term.basis_days ?? 60 : undefined, window_months: term.key === "delinquency_trigger" ? term.window_months ?? 3 : undefined }))).then((r) => r && setOpen(false));
  return (
    <>
      <tr className="border-b border-sand align-top last:border-0">
        <td className="py-2">
          <span className="font-medium">{term.label}</span>
          <span className="ml-1 text-[0.6875rem] text-muted">Tier {term.tier}</span>
        </td>
        <td className="py-2">
          <span className="numeric font-medium">{term.value ?? "–"}</span>
          {term.original && <span className="block text-[0.6875rem] text-muted line-through">{term.original.value} ({term.original.doc_name} p.{term.original.page})</span>}
          {term.effective_from && <span className="block text-[0.6875rem] text-muted">from {term.effective_from}</span>}
          {term.edited && <span className="block text-[0.6875rem] text-muted">Edited from {term.edited.from ?? "–"}: {term.edited.reason}</span>}
          {term.absent_reason && <span className="block text-[0.6875rem] text-muted">{term.absent_reason}</span>}
        </td>
        <td className="max-w-md py-2 text-xs">
          {term.doc_name && <span className="block text-muted">{term.doc_name} p.{term.page ?? "–"} {term.clause}</span>}
          {term.quote && <q className="block text-ink">{term.quote}</q>}
          {term.problem && <span className="block font-medium text-danger">{term.problem}</span>}
        </td>
        <td className="py-2">
          <Badge tone={STATUS_TONE[term.status]}>{term.status === "proposed" ? (term.source === "ai" ? "AI read" : "Entered") : term.status[0].toUpperCase() + term.status.slice(1)}</Badge>
          {term.confidence && <span className="ml-1 text-[0.6875rem] text-muted">{term.confidence}</span>}
        </td>
        <td className="py-2 text-right whitespace-nowrap">
          {term.status === "proposed" && term.verified && (
            <ActionButton reason={view.can.prepare} onClick={() => void act.call(`terms/${term.key}`, { action: "approve" })}>Approve</ActionButton>
          )}{" "}
          <ActionButton variant="secondary" reason={view.can.prepare} onClick={() => setOpen((o) => !o)}>{action === "enter" ? "Enter" : "Edit"}</ActionButton>{" "}
          {term.status === "missing" && !["commitment", "advance_rate"].includes(term.key) && (
            <ActionButton variant="ghost" reason={view.can.prepare} onClick={() => void act.call(`terms/${term.key}`, { action: "absent", reason: "Checked every document: not stated" })}>Not in documents</ActionButton>
          )}
        </td>
      </tr>
      {open && (
        <tr className="border-b border-sand bg-canvas">
          <td colSpan={5} className="p-3">
            <FormMessage message={local.message} />
            <div className="grid grid-cols-6 gap-2">
              <Field id={`v-${term.key}`} label="Value" error={local.errors.value}>
                <TextInput id={`v-${term.key}`} value={values.value} onChange={(e) => setValues({ ...values, value: e.target.value })} invalid={Boolean(local.errors.value)} />
              </Field>
              <Field id={`d-${term.key}`} label="Document" error={local.errors.document}>
                <Select id={`d-${term.key}`} value={values.document} onChange={(e) => setValues({ ...values, document: e.target.value })} invalid={Boolean(local.errors.document)}>
                  <option value="">Choose</option>
                  {pdfs.map((d) => <option key={d.id}>{d.name}</option>)}
                </Select>
              </Field>
              <Field id={`p-${term.key}`} label="Page" error={local.errors.page}>
                <TextInput id={`p-${term.key}`} inputMode="numeric" value={values.page} onChange={(e) => setValues({ ...values, page: e.target.value })} invalid={Boolean(local.errors.page)} />
              </Field>
              <div className="col-span-3">
                <Field id={`q-${term.key}`} label="Passage (optional)" error={local.errors.quote}>
                  <TextInput id={`q-${term.key}`} value={values.quote} onChange={(e) => setValues({ ...values, quote: e.target.value })} invalid={Boolean(local.errors.quote)} />
                </Field>
              </div>
              {action === "edit" && (
                <div className="col-span-4">
                  <Field id={`r-${term.key}`} label="Reason" error={local.errors.reason}>
                    <TextInput id={`r-${term.key}`} value={values.reason} onChange={(e) => setValues({ ...values, reason: e.target.value })} invalid={Boolean(local.errors.reason)} />
                  </Field>
                </div>
              )}
              <div className="col-span-2 flex items-end justify-end gap-2 pb-3">
                <Button size="sm" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
                <Button size="sm" onClick={save} disabled={local.busy}>Save and approve</Button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function Terms({ view, act }: { view: CaseView; act: Act }) {
  const terms = Object.values(view.state.terms ?? {});
  if (!terms.length) {
    return (
      <Panel title="Terms">
        <p className="mb-3 text-sm text-muted">{view.client.ai_permitted ? "The model reads the agreement and amendments; code finds every quote on its page." : `${view.client.name} is outside AI scope and stays on the existing process: enter each term with its page.`}</p>
        {view.client.ai_permitted ? (
          <ActionButton reason={view.can.prepare} onClick={() => void act.call("extract")}>Extract terms</ActionButton>
        ) : (
          <ActionButton reason={view.can.prepare} onClick={() => void act.call("terms/manual")}>Start manual entry</ActionButton>
        )}
      </Panel>
    );
  }
  return (
    <Panel
      title="Terms"
      meta={`${terms.filter((t) => ["approved", "absent"].includes(t.status)).length}/${terms.length} approved`}
      actions={
        <>
          {view.client.ai_permitted && <ActionButton variant="secondary" reason={view.can.prepare} onClick={() => void act.call("extract")}>Extract again</ActionButton>}
          <ActionButton variant="secondary" reason={view.can.prepare} onClick={() => void act.call("terms/approve-verified")}>Approve verified Tier 2 and 3</ActionButton>
        </>
      }
      flush
    >
      <table className="w-full text-[0.8125rem]">
        <tbody>
          {[...terms].sort((a, b) => a.tier - b.tier).map((t) => <TermRow key={t.key} term={t} view={view} act={act} />)}
        </tbody>
      </table>
    </Panel>
  );
}

const TEST_KINDS = ["max", "min", "below", "above", "between", "in_list", "not_in_list", "not_status", "unique"];

function RuleForm({ view, act, kind, onDone }: { view: CaseView; act: Act; kind: "eligibility" | "concentration"; onDone: () => void }) {
  const local = useForm();
  const pdfs = view.documents_list.filter((d) => d.status === "active" && d.name.toLowerCase().endsWith(".pdf"));
  const [v, setV] = useState({ ref: "", plain_english: "", clause_text: "", document: pdfs[0]?.name ?? "", test: "max", field: "days_past_due", value: "", values: "", limit: "", group_by: "" });
  const save = () => {
    const numeric = v.value ? Number(v.value) : null;
    const test = { kind: v.test, field: v.field, low: ["min", "above"].includes(v.test) ? numeric : null, high: ["max", "below"].includes(v.test) ? numeric : null, values: v.values ? v.values.split(",").map((s) => s.trim()) : [] };
    const rule = kind === "eligibility" ? { ref: v.ref, plain_english: v.plain_english, clause_text: v.clause_text, document: v.document, test } : { ref: v.ref, plain_english: v.plain_english, clause_text: v.clause_text, document: v.document, limit_pct: Number(v.limit), group_by: v.group_by || null, where: v.group_by ? null : test };
    void local.run(() => act.action.mutateAsync(() => post<CaseView>(`/api/deals/cases/${view.id}/rules`, { action: "add", kind, rule }))).then((r) => r && onDone());
  };
  const fields = ["days_past_due", "credit_score", "risk_grade", "original_term", "remaining_term", "current_balance", "original_balance", "apr", "obligor_state", "region", "sector", "product", "obligor_id", "status"];
  return (
    <div className="mt-3 rounded-md border border-line bg-canvas p-3">
      <FormMessage message={local.message} />
      <div className="grid grid-cols-4 gap-2">
        <Field id="r-ref" label="Clause reference"><TextInput id="r-ref" value={v.ref} onChange={(e) => setV({ ...v, ref: e.target.value })} /></Field>
        <Field id="r-doc" label="Document"><Select id="r-doc" value={v.document} onChange={(e) => setV({ ...v, document: e.target.value })}>{pdfs.map((d) => <option key={d.id}>{d.name}</option>)}</Select></Field>
        <div className="col-span-2"><Field id="r-plain" label="Plain English"><TextInput id="r-plain" value={v.plain_english} onChange={(e) => setV({ ...v, plain_english: e.target.value })} /></Field></div>
        <div className="col-span-4"><Field id="r-clause" label="Clause text, copied from the document" error={local.errors.rule}><TextInput id="r-clause" value={v.clause_text} onChange={(e) => setV({ ...v, clause_text: e.target.value })} invalid={Boolean(local.errors.rule)} /></Field></div>
        {kind === "concentration" && (
          <>
            <Field id="r-limit" label="Limit (%)"><TextInput id="r-limit" value={v.limit} onChange={(e) => setV({ ...v, limit: e.target.value })} /></Field>
            <Field id="r-group" label="Any single (field)"><Select id="r-group" value={v.group_by} onChange={(e) => setV({ ...v, group_by: e.target.value })}><option value="">Bucket test instead</option>{fields.map((f) => <option key={f}>{f}</option>)}</Select></Field>
          </>
        )}
        {(kind === "eligibility" || !v.group_by) && (
          <>
            <Field id="r-test" label="Test"><Select id="r-test" value={v.test} onChange={(e) => setV({ ...v, test: e.target.value })}>{TEST_KINDS.map((t) => <option key={t}>{t}</option>)}</Select></Field>
            <Field id="r-field" label="Field"><Select id="r-field" value={v.field} onChange={(e) => setV({ ...v, field: e.target.value })}>{fields.map((f) => <option key={f}>{f}</option>)}</Select></Field>
            <Field id="r-value" label="Threshold"><TextInput id="r-value" value={v.value} onChange={(e) => setV({ ...v, value: e.target.value })} /></Field>
            <Field id="r-values" label="Values (comma separated)"><TextInput id="r-values" value={v.values} onChange={(e) => setV({ ...v, values: e.target.value })} /></Field>
          </>
        )}
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="secondary" onClick={onDone}>Cancel</Button>
        <Button size="sm" onClick={save} disabled={local.busy}>Check and add</Button>
      </div>
    </div>
  );
}

function RuleTable({ rules, kind, view, act }: { rules: Rule[]; kind: "eligibility" | "concentration"; view: CaseView; act: Act }) {
  const locked = view.state.rules?.status === "approved";
  return (
    <table className="w-full text-[0.8125rem]">
      <tbody>
        {rules.map((r) => (
          <tr key={r.id} className="border-b border-sand align-top last:border-0">
            <td className="py-2 pr-2 font-mono text-xs font-semibold">{r.id}</td>
            <td className="py-2 pr-2">
              <span className="font-medium">{r.plain_english}</span>
              <span className="block font-mono text-[0.6875rem] text-muted">{r.describe}{r.effective_from && ` · from ${r.effective_from}`}</span>
            </td>
            <td className="max-w-md py-2 pr-2 text-xs">
              <span className="block text-muted">{r.ref} · {r.document} p.{r.page ?? "–"}</span>
              <q>{r.clause_text}</q>
              {r.problem && <span className="block font-medium text-danger">{r.problem}</span>}
            </td>
            <td className="py-2">{r.verified ? <Badge tone="ok">Checked</Badge> : <Badge tone="danger">Failed</Badge>} <span className="text-[0.6875rem] text-muted">{r.source === "ai" ? "AI draft" : r.source === "library" ? `Bank library${r.origin ? ` · ${r.origin.ref}` : ""}` : "Analyst"}</span></td>
            <td className="py-2 text-right">
              {!locked && <ActionButton variant="ghost" reason={view.can.prepare} onClick={() => void act.call("rules", { action: "remove", kind, id: r.id, reason: r.verified ? "Not a criterion of this facility" : `Failed code check: ${r.problem}` })}>Remove</ActionButton>}
            </td>
          </tr>
        ))}
        {rules.length === 0 && <tr><td className="py-4 text-muted">None yet.</td></tr>}
      </tbody>
    </table>
  );
}

function Rules({ view, act }: { view: CaseView; act: Act }) {
  const [adding, setAdding] = useState<"eligibility" | "concentration" | null>(null);
  const rules = view.state.rules;
  const locked = rules?.status === "approved";
  return (
    <div className="space-y-3">
      <Panel
        title="Rule set"
        meta={rules ? `v${rules.version} · ${locked ? `approved by ${rules.approved_by}` : "draft"}` : "Thresholds come from the approved terms"}
        actions={
          <>
            {!locked && <ActionButton variant="secondary" reason={view.can.prepare ?? (view.setup.rule_library.length ? null : `${view.client.name} has no live facility yet, so its rule library is empty`)} onClick={() => void act.call("rules", { action: "library" })}>Reuse bank library</ActionButton>}
            {view.client.ai_permitted && !locked && <ActionButton variant="secondary" reason={view.can.prepare ?? (view.readiness.terms_approved ? null : "Approve the Tier 1 terms first")} onClick={() => void act.call("rules/draft")}>Draft with AI</ActionButton>}
            {locked ? (
              <ActionButton variant="secondary" reason={view.can.prepare} onClick={() => void act.call("rules", { action: "reopen" })}>Reopen</ActionButton>
            ) : (
              <ActionButton reason={view.can.prepare ?? (rules?.eligibility.length ? null : "Add the rules first")} onClick={() => void act.call("rules", { action: "approve" })}>Approve rule set</ActionButton>
            )}
          </>
        }
      >
        <p className="text-xs text-muted">Advance rate, reserve and facility limit are taken from the approved terms. Every rule's clause is found on its page and each threshold must be a figure the clause states.</p>
        {rules?.not_codable && rules.not_codable.length > 0 && <p className="mt-2 text-xs text-warn">Not codable on the tape: {rules.not_codable.join("; ")}</p>}
        <p className="mt-2 text-xs text-muted">{view.client.name}'s rule library: {view.setup.rule_library.length} rules from its live facilities. A library rule is reused only where this agreement states the same clause and threshold; the rest of the rule set is specific to this facility.</p>
        {rules?.library_checked && (
          <p className="mt-1 text-xs">Library check: {rules.library_checked.added.length} reused{rules.library_checked.skipped.map((x) => `; ${x.describe}: ${x.why}`).join("")}</p>
        )}
      </Panel>
      {(["eligibility", "concentration"] as const).map((kind) => (
        <Panel key={kind} title={kind === "eligibility" ? "Eligibility" : "Concentration limits"} actions={!locked && <ActionButton variant="secondary" reason={view.can.prepare} onClick={() => setAdding(kind)}>Add rule</ActionButton>}>
          <RuleTable rules={rules?.[kind] ?? []} kind={kind} view={view} act={act} />
          {adding === kind && <RuleForm view={view} act={act} kind={kind} onDone={() => setAdding(null)} />}
        </Panel>
      ))}
    </div>
  );
}

const STANDARD = ["performing", "arrears", "defaulted", "charged_off", "paid_off"];
const LOADER = ["loan_id", "obligor_id", "origination_date", "maturity_date", "original_balance", "current_balance", "apr", "original_term", "remaining_term", "days_past_due", "status", "credit_score", "risk_grade", "obligor_state", "region", "sector", "product", "merchant", "collateral_type"];

export function MappingEditor({ mapping, disabled, onConfirm, errors }: { mapping: NonNullable<CaseView["state"]["mapping"]>; disabled: string | null; onConfirm: (columns: Record<string, string | null>, statuses: Record<string, string>) => void; errors: Record<string, string> }) {
  const [columns, setColumns] = useState(mapping.columns);
  const [statuses, setStatuses] = useState(mapping.status_map);
  const samples = Object.fromEntries(mapping.checks.filter((c) => c.column).map((c) => [c.column, c]));
  const words = { stored: "Client's stored mapping", ai: "AI suggestion", rules: "Name matching", facility: "Facility's stored mapping" };
  return (
    <Panel title="Tape mapping" meta={`${words[mapping.source]} · ${mapping.confirmed ? `confirmed by ${mapping.confirmed_by ?? "analyst"}` : "not confirmed"}`} actions={<ActionButton reason={disabled} onClick={() => onConfirm(columns, statuses)}>Confirm and store</ActionButton>}>
      <table className="w-full text-[0.8125rem]">
        <thead>
          <tr className="border-b border-line text-left text-xs text-subtle"><th className="py-1">Tape column</th><th>Sample</th><th>Loader field</th><th>Check</th></tr>
        </thead>
        <tbody>
          {mapping.headers.map((h) => (
            <tr key={h} className={clsx("border-b border-sand last:border-0", mapping.changed_columns?.includes(h) && "bg-warn-tint/40")}>
              <td className="py-1 font-medium">{h}</td>
              <td className="numeric text-xs text-muted">{samples[h]?.sample}</td>
              <td>
                <Select aria-label={`Field for ${h}`} className="h-7 text-xs" value={columns[h] ?? ""} disabled={Boolean(disabled)} onChange={(e) => setColumns({ ...columns, [h]: e.target.value || null })} invalid={Boolean(errors[h])}>
                  <option value="">Not loaded</option>
                  {LOADER.map((f) => <option key={f}>{f}</option>)}
                </Select>
              </td>
              <td className="text-xs">{errors[h] ? <span className="text-danger">{errors[h]}</span> : samples[h]?.problem ? <span className="text-danger">{samples[h].problem}</span> : columns[h] ? <span className="text-ok">Fits</span> : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {Object.keys(statuses).length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-semibold">Statuses</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(statuses).map(([raw, std]) => (
              <label key={raw} className="flex items-center gap-1 text-xs">
                {raw}
                <Select aria-label={`Standard status for ${raw}`} className="h-7 w-32 text-xs" value={std} disabled={Boolean(disabled)} onChange={(e) => setStatuses({ ...statuses, [raw]: e.target.value })}>
                  {STANDARD.map((s) => <option key={s}>{s}</option>)}
                </Select>
              </label>
            ))}
          </div>
        </div>
      )}
      {Object.entries(errors).filter(([k]) => !mapping.headers.includes(k)).map(([k, v]) => <p key={k} role="alert" className="mt-2 text-xs text-danger">{k}: {v}</p>)}
    </Panel>
  );
}

function MappingTab({ view, act }: { view: CaseView; act: Act }) {
  const mapping = view.state.mapping;
  return (
    <div className="space-y-3">
      <Panel title="Suggest" actions={<ActionButton reason={view.can.prepare} onClick={() => void act.call("mapping/suggest")}>{mapping ? "Suggest again" : "Suggest mapping"}</ActionButton>}>
        <p className="text-xs text-muted">The client's stored mapping is used when the layout matches; otherwise {view.client.ai_permitted ? "the model suggests and code checks each column against the tape" : "name matching suggests (existing process, outside AI scope)"}. The confirmed mapping is stored for this client only.</p>
      </Panel>
      {mapping && <MappingEditor key={`${mapping.source}-${mapping.confirmed}`} mapping={mapping} disabled={view.can.prepare} errors={act.form.errors} onConfirm={(columns, status_map) => void act.call("mapping", { columns, status_map })} />}
    </div>
  );
}

function ValidationTab({ view, act }: { view: CaseView; act: Act }) {
  const v = view.state.validation;
  const e = v?.engine;
  const [asOf, setAsOf] = useState(view.state.as_of ?? v?.as_of ?? "");
  return (
    <div className="space-y-3">
      <Panel
        title="Run"
        actions={
          <div className="flex items-end gap-2">
            <Field id="as-of" label="Reporting date" error={act.form.errors.as_of}>
              <TextInput id="as-of" type="date" value={asOf} onChange={(x) => setAsOf(x.target.value)} className="h-8 w-40" />
            </Field>
            <div className="pb-3"><ActionButton reason={view.can.prepare ?? (!view.readiness.rules_approved ? "Approve the rule set first" : !view.readiness.mapping_confirmed ? "Confirm the mapping first" : null)} onClick={() => void act.call("validate", { as_of: asOf || null })}>Validate and run</ActionButton></div>
          </div>
        }
      >
        {v ? <p className="text-xs text-muted">{v.rows.toLocaleString()} rows · as of {v.as_of}{v.held && " · load held by a blocking check"}{v.excluded.length > 0 && ` · ${v.excluded.length} rows excluded`}</p> : <p className="text-xs text-muted">Not run yet.</p>}
      </Panel>
      {e && (
        <Kpis items={[
          { label: "Gross pool", value: usd(e.gross_pool_cents) },
          { label: "Eligible pool", value: usd(e.eligible_pool_cents) },
          { label: "Excess concentration", value: usd(e.excess_cents) },
          { label: `Advance rate`, value: `${e.advance_rate_pct}%` },
          { label: "Borrowing base", value: usd(e.borrowing_base_cents) },
          { label: "Delinquency", value: e.delinquency_pct ? `${e.delinquency_pct}%` : "–" },
        ]} />
      )}
      {v && (
        <Panel title="Validation checks" flush>
          <table className="w-full text-[0.8125rem]">
            <tbody>
              {v.checks.map((c) => (
                <tr key={c.id} className="border-b border-sand last:border-0">
                  <td className="px-3 py-1.5">{c.text}</td>
                  <td>{c.severity === "blocking" ? <Badge tone="danger">Blocking</Badge> : <Badge tone="warn">Warning</Badge>}</td>
                  <td className="numeric pr-3 text-right">{c.failed ? <span className="font-semibold text-danger">{c.failed} fail</span> : <span className="text-ok">Pass</span>}</td>
                  <td className="pr-3 text-xs text-muted">{c.examples.slice(0, 3).map((x) => `${x.key} (row ${x.row})`).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
      {e && (
        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title="Eligibility results" flush>
            <table className="w-full text-[0.8125rem]">
              <tbody>
                {e.rules.map((r) => (
                  <tr key={r.id} className="border-b border-sand last:border-0">
                    <td className="px-3 py-1.5 font-mono text-xs">{r.id}</td>
                    <td className="numeric text-right">{r.failed} loans</td>
                    <td className="numeric pr-3 text-right">{usd(r.failed_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          <Panel title="Concentration" flush>
            <table className="w-full text-[0.8125rem]">
              <tbody>
                {e.concentrations.map((c) => (
                  <tr key={c.id} className="border-b border-sand last:border-0">
                    <td className="px-3 py-1.5 font-mono text-xs">{c.id}</td>
                    <td className="text-xs">{c.largest || "–"} {c.share_pct}% vs {c.limit_pct}%{!c.active && " (not yet in force)"}</td>
                    <td className="numeric pr-3 text-right">{c.excess_cents ? usd(c.excess_cents) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </div>
      )}
    </div>
  );
}

function ExceptionRow({ item, view, act }: { item: CaseException; view: CaseView; act: Act }) {
  const [note, setNote] = useState("");
  const local = useForm();
  const closed = ["accepted", "resolved"].includes(item.status);
  const send = (action: string) => void local.run(() => act.action.mutateAsync(() => post<CaseView>(`/api/deals/cases/${view.id}/exceptions/${item.ref}`, { action, note }))).then(() => setNote(""));
  const decide = () => void local.run(() => act.action.mutateAsync(() => post<CaseView>(`/api/deals/cases/${view.id}/exceptions/${item.ref}/decide`, { text: note })));
  const last = item.answer ?? item.decision;
  return (
    <li className="border-b border-sand py-2.5 last:border-0">
      <div className="flex items-start gap-2">
        <RecordId>{item.ref}</RecordId>
        <div className="min-w-0 flex-1">
          <p className="text-[0.8125rem] font-medium">{item.title}</p>
          <p className="text-xs text-muted">{item.type} · {item.detail}</p>
          {item.query && <p className="mt-0.5 text-xs">Query: {item.query.text} ({item.query.by})</p>}
          {item.escalation && <p className="mt-0.5 text-xs">Escalated: {item.escalation.text} ({item.escalation.by})</p>}
          {last && <p className="mt-0.5 rounded bg-info-tint px-2 py-0.5 text-xs">{item.answer ? "Client" : "Expert"}: {last.text} ({last.by})</p>}
          {!closed && <p className="mt-0.5 text-xs text-muted">Suggested: {item.suggested}</p>}
        </div>
        <span className="flex shrink-0 items-center gap-1">
          {item.severity === "blocking" && <Badge tone="danger">Blocking</Badge>}
          {item.severity === "warning" && <Badge tone="warn">Warning</Badge>}
          <Badge tone={STATUS_TONE[item.status]}>{EXC_LABEL[item.status]}</Badge>
        </span>
      </div>
      {item.status === "open" && (
        <div className="mt-2 flex items-start gap-2 pl-24">
          <div className="flex-1">
            <TextInput id={`n-${item.ref}`} aria-label={`Note for ${item.ref}`} placeholder="Note" value={note} onChange={(e) => setNote(e.target.value)} invalid={Boolean(local.errors.note)} />
          </div>
          <ActionButton variant="secondary" reason={view.can.prepare} onClick={() => send("accept")}>Accept</ActionButton>
          <ActionButton variant="secondary" reason={view.can.prepare} onClick={() => send("query")}>Query client</ActionButton>
          <ActionButton variant="secondary" reason={view.can.prepare} onClick={() => send("escalate")}>Send to expert</ActionButton>
        </div>
      )}
      {item.status === "with_expert" && (
        <div className="mt-2 flex items-start gap-2 pl-24">
          <div className="flex-1"><TextInput id={`d-${item.ref}`} aria-label={`Decision for ${item.ref}`} placeholder="Decision and reasoning" value={note} onChange={(e) => setNote(e.target.value)} /></div>
          <ActionButton reason={view.can.expert} onClick={decide}>Record decision</ActionButton>
        </div>
      )}
      {["answered", "decided"].includes(item.status) && (
        <div className="mt-2 pl-24"><ActionButton reason={view.can.prepare} onClick={() => send("close")}>Close with this answer</ActionButton></div>
      )}
      {local.message && <p role="alert" className="mt-1 pl-24 text-xs text-danger">{local.message}</p>}
    </li>
  );
}

function Exceptions({ view, act }: { view: CaseView; act: Act }) {
  const items = (view.state.exceptions ?? []).filter((e) => e.severity !== "info" || e.status !== "resolved");
  const [show, setShow] = useState<"open" | "all">("open");
  const shown = items.filter((e) => show === "all" || !["accepted", "resolved"].includes(e.status));
  return (
    <Panel
      title="Exceptions"
      meta={`${items.filter((e) => !["accepted", "resolved"].includes(e.status)).length} open of ${items.length}`}
      actions={
        <Select aria-label="Show" value={show} onChange={(e) => setShow(e.target.value as "open" | "all")} className="h-8 w-28 text-xs">
          <option value="open">Open</option>
          <option value="all">All</option>
        </Select>
      }
    >
      <QueryTracker view={view} />
      {view.state.client_model && view.state.client_model.length > 0 && (
        <p className="mb-2 text-xs text-muted">Client model compared cell by cell: {view.state.client_model.map((c) => `${c.label} ${c.model} (${c.cell})`).join("; ")}</p>
      )}
      {shown.length === 0 ? <p className="py-6 text-center text-sm text-muted">No open exceptions.</p> : <ul>{shown.map((item) => <ExceptionRow key={item.ref} item={item} view={view} act={act} />)}</ul>}
    </Panel>
  );
}

function Qc({ view, act }: { view: CaseView; act: Act }) {
  const qc = view.state.qc;
  const [notes, setNotes] = useState<Record<string, string>>({});
  const pending = qc?.status === "pending";
  return (
    <Panel
      title="Independent QC"
      meta={qc ? `${qc.status === "pending" ? "In QC" : qc.status === "passed" ? `Passed · ${qc.completed_by}` : "Returned to the analyst"} · submitted by ${qc.submitted_by}` : "Not submitted"}
      actions={
        pending ? (
          <ActionButton reason={view.can.qc} onClick={() => void act.call("qc/complete")}>Complete QC</ActionButton>
        ) : (
          <ActionButton reason={view.can.prepare ?? (Object.values(view.readiness).every(Boolean) ? null : "Work every exception and run validation first")} onClick={() => void act.call("submit-qc")}>Submit for QC</ActionButton>
        )
      }
    >
      <ul className="mb-2 flex flex-wrap gap-2 text-xs">
        {Object.entries(view.readiness).map(([k, v]) => <li key={k}><Badge tone={v ? "ok" : "warn"}>{k.replace(/_/g, " ")}</Badge></li>)}
      </ul>
      <table className="w-full text-[0.8125rem]">
        <tbody>
          {view.qc_items.map((item) => {
            const mark = qc?.marks[item.id];
            return (
              <tr key={item.id} className="border-b border-sand align-top last:border-0">
                <td className="py-1.5 pr-2"><span className="font-medium">{item.label}</span><span className="block text-xs text-muted">{item.source}</span></td>
                <td className="py-1.5 pr-2 text-xs">{item.value}{item.quote && <q className="block text-muted">{item.quote}</q>}{item.computed && <span className={clsx("block font-medium", item.computed === "agrees" ? "text-ok" : "text-danger")}>Recalculation {item.computed}</span>}</td>
                <td className="py-1.5 text-right whitespace-nowrap">
                  {mark ? <Badge tone={mark.result === "agrees" ? "ok" : "danger"}>{mark.result === "agrees" ? "Agrees" : `Variance: ${mark.note}`}</Badge> : pending && (
                    <span className="inline-flex items-center gap-1">
                      <TextInput aria-label={`Variance note for ${item.label}`} className="h-7 w-40 text-xs" placeholder="Variance note" value={notes[item.id] ?? ""} onChange={(e) => setNotes({ ...notes, [item.id]: e.target.value })} />
                      <ActionButton variant="secondary" reason={view.can.qc} onClick={() => void act.call("qc", { item: item.id, result: "agrees" })}>Agrees</ActionButton>
                      <ActionButton variant="ghost" reason={view.can.qc} onClick={() => void act.call("qc", { item: item.id, result: "variance", note: notes[item.id] ?? "" })}>Variance</ActionButton>
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Panel>
  );
}

function Approval({ view, act }: { view: CaseView; act: Act }) {
  const s = view.state;
  const [reason, setReason] = useState("");
  return (
    <div className="grid gap-3 xl:grid-cols-2">
      <Panel title="Four-eyes approval" meta={s.approved_at ? `Approved by ${s.approved_by} · ${when(s.approved_at)}` : s.qc?.status === "passed" ? "Waiting for the second analyst" : "QC must pass first"}>
        {!s.approved_at && (
          <div className="flex items-end gap-2">
            <div className="flex-1"><Field id="approve-reason" label="Note (needed to return)" error={act.form.errors.reason}><TextInput id="approve-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field></div>
            <div className="flex gap-2 pb-3">
              <ActionButton variant="secondary" reason={view.can.review ?? (s.qc?.status === "passed" ? null : "QC must pass first")} onClick={() => void act.call("return", { reason })}>Return</ActionButton>
              <ActionButton reason={view.can.review ?? (s.qc?.status === "passed" ? null : "QC must pass first")} onClick={() => void act.call("approve", { reason: reason || null })}>Approve</ActionButton>
            </div>
          </div>
        )}
        {s.approved_at && !s.live_at && <ActionButton reason={view.can.review} onClick={() => void act.call("go-live")}>Go live</ActionButton>}
        {s.live_at && view.facility_id && <p className="text-sm">Live since {when(s.live_at)} · <Link to={`/facilities/${view.facility_id}`} className="font-medium text-info hover:underline">Open facility</Link></p>}
        <PanoramaReceipt sent={view.panorama} what="the load file" />
        {s.live_at && view.panorama && !view.panorama.ok && <ActionButton variant="secondary" reason={view.can.review} onClick={() => void act.call("panorama")}>Send to Panorama again</ActionButton>}
        {!s.live_at && <p className="mt-2 text-xs text-muted">At go-live the approved load file is posted to Panorama and the receipt kept in the audit trail.</p>}
      </Panel>
      <Panel title="Outputs">
        <ul className="space-y-2 text-sm">
          <li>
            <a href={`/api/deals/cases/${view.id}/configuration.xlsx`} className={clsx("inline-flex items-center gap-1 font-medium", s.rules ? "text-info hover:underline" : "pointer-events-none text-muted")}>
              <Download aria-hidden className="size-3.5" /> Configuration workbook ({s.approved_at ? "final" : "provisional"})
            </a>
          </li>
          <li>
            <a href={`/api/deals/cases/${view.id}/load-file.json`} className={clsx("inline-flex items-center gap-1 font-medium", s.approved_at ? "text-info hover:underline" : "pointer-events-none text-muted")} aria-disabled={!s.approved_at}>
              <Download aria-hidden className="size-3.5" /> Load file {s.approved_at ? "" : "(after approval)"}
            </a>
          </li>
        </ul>
      </Panel>
    </div>
  );
}

/** Edit the case's own fields, or archive it with a reason. Both land in the case's history. */
function EditCase({ view, open, onOpenChange }: { view: CaseView; open: boolean; onOpenChange: (open: boolean) => void }) {
  const form = useForm();
  const action = useDealAction<CaseView>();
  const [v, setV] = useState({ facility_name: view.facility_name, deal_type: view.deal_type, commitment: String(view.commitment_cents / 100) });
  const submit = () =>
    void form
      .run(() => action.mutateAsync(() => post<CaseView>(`/api/deals/cases/${view.id}`, { facility_name: v.facility_name, deal_type: v.deal_type, commitment: v.commitment ? Number(v.commitment.replace(/[^\d.]/g, "")) : null }, "PATCH")))
      .then((saved) => saved && onOpenChange(false));
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Edit case">
      <form noValidate onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <FormMessage message={form.message} />
        <Field id="edit-facility" label="Facility name" error={form.errors.facility_name}>
          <TextInput id="edit-facility" value={v.facility_name} onChange={(e) => setV({ ...v, facility_name: e.target.value })} invalid={Boolean(form.errors.facility_name)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field id="edit-type" label="Deal type" error={form.errors.deal_type}>
            <Select id="edit-type" value={v.deal_type} onChange={(e) => setV({ ...v, deal_type: e.target.value })} invalid={Boolean(form.errors.deal_type)}>
              {DEAL_TYPES.map((t) => <option key={t}>{t}</option>)}
            </Select>
          </Field>
          <Field id="edit-commitment" label="Commitment (US$)" error={form.errors.commitment}>
            <TextInput id="edit-commitment" inputMode="decimal" value={v.commitment} onChange={(e) => setV({ ...v, commitment: e.target.value })} invalid={Boolean(form.errors.commitment)} />
          </Field>
        </div>
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button size="sm" type="submit" disabled={form.busy}>Save changes</Button>
        </div>
      </form>
    </Dialog>
  );
}

function ArchiveCase({ view, open, onOpenChange }: { view: CaseView; open: boolean; onOpenChange: (open: boolean) => void }) {
  const form = useForm();
  const action = useDealAction<CaseView>();
  const [note, setNote] = useState("");
  const submit = () => void form.run(() => action.mutateAsync(() => post<CaseView>(`/api/deals/cases/${view.id}/archive`, { note }))).then((saved) => saved && onOpenChange(false));
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={`Archive ${view.ref}`}>
      <form noValidate onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <FormMessage message={form.message} />
        <Field id="archive-note" label="Reason" error={form.errors.note}>
          <TextInput id="archive-note" value={note} onChange={(e) => setNote(e.target.value)} invalid={Boolean(form.errors.note)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button size="sm" type="submit" disabled={form.busy}>Archive case</Button>
        </div>
      </form>
    </Dialog>
  );
}

function hours(h: number | null): string {
  if (h === null) {
    return "–";
  }
  return h < 1 ? `${Math.round(h * 60)} min` : `${h.toFixed(1)} h`;
}

function QueryTracker({ view }: { view: CaseView }) {
  const q = view.setup.queries;
  if (!q.queries.length) {
    return null;
  }
  return (
    <div className="mb-3 rounded-md border border-line">
      <p className="flex items-center justify-between border-b border-line px-3 py-1.5 text-xs font-semibold">
        <span>Query tracker</span>
        <span className="font-normal text-muted">{q.open} waiting on the client · client waiting time {hours(q.client_wait_hours)}, kept apart from analyst time</span>
      </p>
      <table className="w-full text-xs">
        <thead><tr className="text-left text-[0.6875rem] text-muted uppercase"><th className="px-3 py-1">Ref</th><th>Query</th><th>Sent</th><th>Answered</th><th className="pr-3 text-right">Client waiting</th></tr></thead>
        <tbody>
          {q.queries.map((r) => (
            <tr key={r.ref} className="border-t border-sand">
              <td className="px-3 py-1 font-mono">{r.ref}</td>
              <td>{r.title}{r.model_check && <Badge tone="info">Model validation</Badge>}</td>
              <td className="numeric">{when(r.sent_at)} · {r.sent_by}</td>
              <td className="numeric">{r.answered_at ? when(r.answered_at) : <Badge tone="warn">Waiting</Badge>}</td>
              <td className="numeric pr-3 text-right">{hours(r.client_wait_hours)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const FREQUENCIES = ["Monthly", "Quarterly", "Weekly"];
const FORMATS = ["XLSX", "PDF", "CSV"];

function ReportingTab({ view, act }: { view: CaseView; act: Act }) {
  const current = view.state.reporting;
  const termDay = view.state.terms?.reporting_day?.typed;
  const [lines, setLines] = useState<string[]>(current?.lines ?? ["gross_pool", "eligible_pool", "excess_concentration", "advance_rate", "borrowing_base", "availability", "delinquency_ratio"]);
  const [v, setV] = useState({ frequency: current?.frequency ?? "Monthly", format: current?.format ?? "XLSX", day: current?.day ? String(current.day) : termDay ? String(termDay) : "", note: current?.note ?? "" });
  const toggle = (key: string) => setLines((l) => (l.includes(key) ? l.filter((k) => k !== key) : [...l, key]));
  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Panel
        title="Reporting the client needs"
        meta={current ? `v${current.version} · recorded by ${current.captured_by} · ${when(current.captured_at)}` : "Not recorded yet"}
        actions={<ActionButton reason={view.can.prepare} onClick={() => void act.call("reporting", { lines, frequency: v.frequency, format: v.format, day: v.day ? Number(v.day) : null, note: v.note })}>{current ? "Save changes" : "Record requirements"}</ActionButton>}
      >
        <p className="mb-2 text-xs text-muted">Captured at intake with the client. It feeds the Report sheet of the configuration workbook and the monthly lender workbook. Code produces every line.</p>
        <fieldset aria-label="Report lines" className="mb-3 grid gap-1 sm:grid-cols-2">
          {view.setup.report_catalogue.map((line) => (
            <label key={line.key} className="flex items-start gap-2 rounded px-1 py-0.5 text-xs hover:bg-sand">
              <input type="checkbox" checked={lines.includes(line.key)} disabled={Boolean(view.can.prepare)} onChange={() => toggle(line.key)} className="mt-0.5" />
              <span><span className="font-medium">{line.label}</span><span className="block text-muted">{line.how}</span></span>
            </label>
          ))}
        </fieldset>
        {act.form.errors.lines && <p role="alert" className="mb-2 text-xs text-danger">{act.form.errors.lines}</p>}
        <div className="grid grid-cols-3 gap-2">
          <Field id="rep-frequency" label="Frequency" error={act.form.errors.frequency}><Select id="rep-frequency" value={v.frequency} onChange={(e) => setV({ ...v, frequency: e.target.value })}>{FREQUENCIES.map((f) => <option key={f}>{f}</option>)}</Select></Field>
          <Field id="rep-format" label="Format" error={act.form.errors.format}><Select id="rep-format" value={v.format} onChange={(e) => setV({ ...v, format: e.target.value })}>{FORMATS.map((f) => <option key={f}>{f}</option>)}</Select></Field>
          <Field id="rep-day" label={termDay ? `Due by day (agreement: ${termDay})` : "Due by day"} error={act.form.errors.day}><TextInput id="rep-day" inputMode="numeric" value={v.day} onChange={(e) => setV({ ...v, day: e.target.value })} invalid={Boolean(act.form.errors.day)} /></Field>
        </div>
        <Field id="rep-note" label="Client's note (optional)"><TextInput id="rep-note" value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} /></Field>
      </Panel>
      <Panel title="Feeds">
        <ul className="space-y-1 text-xs">
          <li>Configuration workbook › Report sheet ({view.state.approved_at ? "final" : "provisional"})</li>
          <li>Client model › Report sheet, where Oxane builds the model</li>
          <li>Facility record at go-live: the monthly report follows these lines</li>
        </ul>
        {current && <p className="mt-2 text-xs">{current.lines.length} lines · {current.frequency} · {current.format}{current.day ? ` · by day ${current.day}` : ""}</p>}
      </Panel>
    </div>
  );
}

const MODEL_STATUS: Record<string, string> = { built: "Built, not sent", with_client: "With the client", confirmed: "Confirmed by the client", changes_requested: "Client asked for changes" };

function ClientModelTab({ view, act }: { view: CaseView; act: Act }) {
  const built = view.state.built_model;
  const diffs = view.state.client_model ?? [];
  const [note, setNote] = useState("Please review the borrowing base model we built from the agreement, and confirm it or tell us what to change.");
  if (view.setup.own_client_model) {
    return (
      <Panel title="Client's own model" meta="Compared with the agreement, cell by cell">
        {diffs.length ? (
          <ul className="space-y-1 text-xs">{diffs.map((d) => <li key={d.term}>{d.label} ({d.cell}): model {d.model}, agreement {d.agreed} {d.differs ? <Badge tone="warn">Differs: query raised</Badge> : <Badge tone="ok">Agrees</Badge>}</li>)}</ul>
        ) : <p className="text-xs text-muted">Run validation to compare the model with the approved terms.</p>}
      </Panel>
    );
  }
  const item = built ? (view.state.exceptions ?? []).find((e) => e.key === `model:validation:v${built.version}`) : undefined;
  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <Panel
        title="Client model built by Oxane"
        meta={built ? `v${built.version} · ${MODEL_STATUS[built.status]}` : "The client has no model of its own"}
        actions={<ActionButton variant={built ? "secondary" : "primary"} reason={view.can.prepare ?? (!view.readiness.rules_approved ? "Approve the rule set first" : !view.readiness.validation_run ? "Run validation first" : built && built.status !== "changes_requested" && built.status !== "built" ? "Waiting on the client" : null)} onClick={() => void act.call("client-model/build")}>{built ? "Rebuild" : "Build client model"}</ActionButton>}
      >
        <p className="mb-2 text-xs text-muted">No client model was provided, so Oxane builds one from the approved terms and rule set and validates it with the client. Code builds the workbook and every figure; {view.client.ai_permitted ? "AI may draft the covering notes, with every figure filled by code" : "the notes are a code template (existing process, outside AI scope)"}.</p>
        {built ? (
          <>
            <p className="text-sm">
              <a href={`/api/deals/documents/${built.doc_id}/file`} className="inline-flex items-center gap-1 font-medium text-info hover:underline"><Download aria-hidden className="size-3.5" />{built.name}</a>
              <span className="ml-2 text-xs text-muted">built by {built.built_by} · {when(built.built_at)} · rule set v{built.rules_version}</span>
            </p>
            <div className="mt-2 rounded bg-canvas p-2 text-xs">{built.notes.map((n, i) => <p key={i} className="mb-1">{n}</p>)}<p className="text-[0.6875rem] text-muted">{built.notes_by === "ai" ? "Notes worded by AI; every figure filled by code." : "Notes from the code template."}</p></div>
            {built.validation && <p className="mt-2 rounded bg-info-tint px-2 py-1 text-xs">Client ({built.validation.by}, {when(built.validation.at)}): {built.validation.outcome === "confirmed" ? "confirmed the model" : "asked for changes"}. {built.validation.text}</p>}
            {item?.status === "open" && (
              <div className="mt-2 flex items-end gap-2">
                <div className="flex-1"><Field id="model-note" label="Message to the client"><TextInput id="model-note" value={note} onChange={(e) => setNote(e.target.value)} /></Field></div>
                <div className="pb-3"><ActionButton reason={view.can.prepare} onClick={() => void act.call(`exceptions/${item.ref}`, { action: "query", note })}>Send to client for validation</ActionButton></div>
              </div>
            )}
            {item?.status === "answered" && built.status === "confirmed" && <div className="mt-2"><ActionButton reason={view.can.prepare} onClick={() => void act.call(`exceptions/${item.ref}`, { action: "close" })}>Close: model agreed</ActionButton></div>}
          </>
        ) : <p className="text-xs text-muted">Not built yet.</p>}
      </Panel>
      <Panel title="Validation with the client">
        <ol className="space-y-1 text-xs">
          <li><Badge tone={built ? "ok" : "neutral"}>1</Badge> Built from the approved terms</li>
          <li><Badge tone={built?.sent_at ? "ok" : "neutral"}>2</Badge> Sent to the client through the portal{built?.sent_at ? ` · ${when(built.sent_at)}` : ""}</li>
          <li><Badge tone={built?.validation ? "ok" : "neutral"}>3</Badge> Client confirms or asks for changes</li>
          <li><Badge tone={view.readiness.client_model_agreed ? "ok" : "neutral"}>4</Badge> Agreed: the case can go to QC</li>
        </ol>
        <p className="mt-2 text-[0.6875rem] text-muted">The wait is tracked as client waiting time, like any other query.</p>
      </Panel>
    </div>
  );
}

export function DealCasePage() {
  const params = useParams();
  const id = Number(params.id);
  const tab = params.tab ?? "overview";
  const { data: view, isError } = useDealCase(id);
  const act = useActions(id);
  const [dialog, setDialog] = useState<"edit" | "archive" | null>(null);
  if (isError) {
    return <p role="alert" className="text-sm text-danger">This case could not be loaded.</p>;
  }
  if (!view) {
    return <Skeleton className="h-96 w-full" />;
  }
  const open = (view.state.exceptions ?? []).filter((e) => e.severity !== "info" && !["accepted", "resolved"].includes(e.status)).length;
  const terms = Object.values(view.state.terms ?? {});
  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "documents", label: "Documents", count: view.documents },
    { id: "terms", label: "Terms", count: terms.length ? `${view.terms.approved}/${terms.length}` : "" },
    { id: "reporting", label: "Reporting", count: view.state.reporting ? view.state.reporting.lines.length : "" },
    { id: "rules", label: "Rules", count: (view.state.rules?.eligibility.length ?? 0) + (view.state.rules?.concentration.length ?? 0) },
    { id: "mapping", label: "Mapping" },
    { id: "validation", label: "Validation" },
    { id: "client-model", label: "Client model" },
    { id: "exceptions", label: "Exceptions", count: open },
    { id: "qc", label: "QC" },
    { id: "approval", label: "Approval" },
    { id: "activity", label: "Activity" },
  ];
  return (
    <>
      <PageTitle
        title={view.facility_name}
        meta={
          <span className="flex flex-wrap items-center gap-1.5">
            <RecordId>{view.ref}</RecordId>
            <Link to={`/clients/${view.client.id}`} className="hover:underline">{view.client.name}</Link> · {view.deal_type} · {usd(view.commitment_cents)}
            {!view.client.ai_permitted && <NoAiBadge compact />}
            <span title={`${view.cost.calls} model calls, ${view.cost.tokens.toLocaleString()} tokens`}>· model cost US${view.cost.cost_usd.toFixed(2)}</span>
            {view.archived_at && <Badge tone="neutral">Archived</Badge>}
          </span>
        }
        actions={
          <>
            <ActionButton variant="secondary" reason={view.archived_at ? "Archived" : view.can.prepare} onClick={() => setDialog("edit")}>Edit case</ActionButton>
            <ActionButton variant="secondary" reason={view.archived_at ? "Archived" : view.facility_id ? "Live: archive the facility instead" : view.can.prepare} onClick={() => setDialog("archive")}>Archive case</ActionButton>
          </>
        }
      />
      {dialog === "edit" && <EditCase view={view} open onOpenChange={(o) => setDialog(o ? "edit" : null)} />}
      {dialog === "archive" && <ArchiveCase view={view} open onOpenChange={(o) => setDialog(o ? "archive" : null)} />}
      <Stages view={view} />
      <HandOffHint items={view.work} />
      {act.form.message && !Object.keys(act.form.errors).length && <FormMessage message={act.form.message} />}
      <Tabs tabs={tabs} current={tab} base={`/deals/cases/${id}`} />
      {tab === "overview" && (
        <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Panel title="Readiness">
            <ul className="space-y-1 text-sm">
              {Object.entries(view.readiness).map(([k, v]) => <li key={k} className="flex items-center gap-2"><Badge tone={v ? "ok" : "warn"}>{v ? "Done" : "Open"}</Badge>{k.replace(/_/g, " ")}</li>)}
              <li className="flex items-center gap-2"><Badge tone={view.state.qc?.status === "passed" ? "ok" : "warn"}>{view.state.qc?.status ?? "Open"}</Badge>independent QC</li>
              <li className="flex items-center gap-2"><Badge tone={view.state.approved_at ? "ok" : "warn"}>{view.state.approved_at ? "Done" : "Open"}</Badge>four-eyes approval</li>
            </ul>
          </Panel>
          <Panel title="Client model and reporting">
            <ul className="space-y-1 text-xs">
              <li>Reporting: {view.state.reporting ? `${view.state.reporting.lines.length} lines, ${view.state.reporting.frequency.toLowerCase()}, ${view.state.reporting.format}` : "not recorded"}</li>
              <li>Client model: {view.setup.own_client_model ? "the client's own, compared with the agreement" : view.state.built_model ? `built by Oxane, v${view.state.built_model.version}: ${MODEL_STATUS[view.state.built_model.status].toLowerCase()}` : "none provided: Oxane builds one"}</li>
              <li>Queries: {view.setup.queries.queries.length} sent, {view.setup.queries.open} waiting · client waiting time {hours(view.setup.queries.client_wait_hours)}</li>
              {view.panorama && <li>{view.panorama.ok ? `Sent to Panorama · receipt ${view.panorama.receipt}` : "Panorama hand-off failed"}</li>}
            </ul>
          </Panel>
          <Panel title="Hand-offs">
            <Activity history={{ entries: view.history.entries.filter((e) => e.type.startsWith("handoff")).slice(0, 8), chain_intact: view.history.chain_intact }} work={view.work} />
          </Panel>
        </div>
      )}
      {tab === "documents" && <Documents view={view} act={act} />}
      {tab === "terms" && <Terms view={view} act={act} />}
      {tab === "reporting" && <ReportingTab view={view} act={act} />}
      {tab === "client-model" && <ClientModelTab view={view} act={act} />}
      {tab === "rules" && <Rules view={view} act={act} />}
      {tab === "mapping" && <MappingTab view={view} act={act} />}
      {tab === "validation" && <ValidationTab view={view} act={act} />}
      {tab === "exceptions" && <Exceptions view={view} act={act} />}
      {tab === "qc" && <Qc view={view} act={act} />}
      {tab === "approval" && <Approval view={view} act={act} />}
      {tab === "activity" && <Panel title="Activity"><Activity history={view.history} work={view.work} /></Panel>}
    </>
  );
}
