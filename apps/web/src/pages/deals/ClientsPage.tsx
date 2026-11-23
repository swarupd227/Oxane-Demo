import { Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ActionButton, Activity, Field, FormMessage, Select, TextInput, useForm, when } from "../../components/deals/parts";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Skeleton } from "../../components/ui/layout";
import { post, STAGE_LABEL, usd, useClient, useClients, useDealAction, type ClientRow } from "../../lib/deals";
import { useRole } from "../../lib/persona";
import { NoAiBadge } from "../../monitoring/parts";
import { Badge, DataTable, Panel, PageTitle, RecordId, type Column } from "../../monitoring/ui";

const FIELDS = ["loan_id", "obligor_id", "origination_date", "maturity_date", "original_balance", "current_balance", "apr", "original_term", "remaining_term", "days_past_due", "status", "credit_score", "risk_grade", "obligor_state", "region", "sector", "product", "merchant", "collateral_type"];

export function ClientForm({ client, open, onOpenChange }: { client?: ClientRow; open: boolean; onOpenChange: (open: boolean) => void }) {
  const form = useForm();
  const action = useDealAction<ClientRow>();
  const navigate = useNavigate();
  const [values, setValues] = useState({
    name: client?.name ?? "",
    short_name: client?.short_name ?? "",
    contact_name: client?.contact_name ?? "",
    ai_permitted: client?.ai_permitted ?? true,
    approval_levels: client?.approval_levels ?? 2,
    reason: "",
  });
  const [overrides, setOverrides] = useState<[string, string][]>(Object.entries(client?.master_field_overrides ?? {}));
  const set = (key: string, value: unknown) => setValues((v) => ({ ...v, [key]: value }));
  const aiChanged = client && client.ai_permitted !== values.ai_permitted;
  const submit = async () => {
    const body = { ...values, master_field_overrides: Object.fromEntries(overrides.filter(([f, c]) => f && c)) };
    const saved = await form.run(() =>
      action.mutateAsync(() => (client ? post<ClientRow>(`/api/deals/clients/${client.id}`, body, "PATCH") : post<ClientRow>("/api/deals/clients", body))),
    );
    if (saved) {
      onOpenChange(false);
      if (!client) {
        navigate(`/clients/${saved.id}`);
      }
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={client ? `Edit ${client.name}` : "New client"}>
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <FormMessage message={form.message} />
        <Field id="client-name" label="Legal name" error={form.errors.name}>
          <TextInput id="client-name" value={values.name} onChange={(e) => set("name", e.target.value)} invalid={Boolean(form.errors.name)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field id="client-short" label="Short name" error={form.errors.short_name}>
            <TextInput id="client-short" value={values.short_name} onChange={(e) => set("short_name", e.target.value)} invalid={Boolean(form.errors.short_name)} />
          </Field>
          <Field id="client-contact" label="Named client contact" error={form.errors.contact_name}>
            <TextInput id="client-contact" value={values.contact_name} onChange={(e) => set("contact_name", e.target.value)} invalid={Boolean(form.errors.contact_name)} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field id="client-ai" label="AI" error={form.errors.ai_permitted}>
            <Select id="client-ai" value={values.ai_permitted ? "yes" : "no"} onChange={(e) => set("ai_permitted", e.target.value === "yes")}>
              <option value="yes">Permitted</option>
              <option value="no">Not permitted</option>
            </Select>
          </Field>
          <Field id="client-levels" label="Approval levels" error={form.errors.approval_levels}>
            <Select id="client-levels" value={values.approval_levels} onChange={(e) => set("approval_levels", Number(e.target.value))} invalid={Boolean(form.errors.approval_levels)}>
              <option value={2}>2: preparer, second analyst</option>
              <option value={3}>3: plus head of monitoring</option>
            </Select>
          </Field>
        </div>
        {aiChanged && (
          <Field id="client-reason" label="Reason for the AI change" error={form.errors.reason}>
            <TextInput id="client-reason" value={values.reason} onChange={(e) => set("reason", e.target.value)} invalid={Boolean(form.errors.reason)} />
          </Field>
        )}
        <Field id="client-overrides" label="Master-field overrides" hint="Loader field and the client's column that always supplies it" error={form.errors.master_field_overrides}>
          <div className="space-y-1">
            {overrides.map(([f, c], i) => (
              <div key={i} className="flex gap-2">
                <Select aria-label="Field" value={f} onChange={(e) => setOverrides((o) => o.map((x, j) => (j === i ? [e.target.value, x[1]] : x)))}>
                  <option value="">Field</option>
                  {FIELDS.map((name) => (
                    <option key={name}>{name}</option>
                  ))}
                </Select>
                <TextInput aria-label="Column" value={c} placeholder="Column name" onChange={(e) => setOverrides((o) => o.map((x, j) => (j === i ? [x[0], e.target.value] : x)))} />
              </div>
            ))}
            <Button size="sm" variant="ghost" onClick={() => setOverrides((o) => [...o, ["", ""]])}>
              <Plus aria-hidden className="size-3.5" />
              Add override
            </Button>
          </div>
        </Field>
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" type="submit" disabled={form.busy}>
            {client ? "Save changes" : "Create client"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function ClientsPage() {
  const { data } = useClients();
  const role = useRole();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const columns: Column<ClientRow>[] = [
    { key: "ref", header: "Client", sort: (c) => c.ref, render: (c) => <RecordId>{c.ref}</RecordId> },
    { key: "name", header: "Name", sort: (c) => c.name, render: (c) => <span className="flex items-center gap-1.5 font-medium">{c.name}{!c.ai_permitted && <NoAiBadge compact />}</span> },
    { key: "contact", header: "Contact", render: (c) => <span className="text-muted">{c.contact_name || "–"}</span> },
    { key: "levels", header: "Approval levels", align: "right", render: (c) => <span className="numeric">{c.approval_levels}</span> },
    { key: "created", header: "Created", sort: (c) => c.created_at, render: (c) => <span className="numeric text-muted">{when(c.created_at)}</span> },
  ];
  return (
    <>
      <PageTitle
        title="Clients"
        meta={data ? `${data.length} clients` : undefined}
        actions={<ActionButton reason={role === "admin" ? null : "For the administrator"} onClick={() => setOpen(true)}>New client</ActionButton>}
      />
      {!data ? <Skeleton className="h-64 w-full" /> : <DataTable rows={data} columns={columns} rowKey={(c) => String(c.id)} search={(c) => `${c.name} ${c.contact_name}`} searchPlaceholder="Filter clients" onRowClick={(c) => navigate(`/clients/${c.id}`)} empty="No clients yet." />}
      {open && <ClientForm open={open} onOpenChange={setOpen} />}
    </>
  );
}

export function ClientPage() {
  const id = Number(useParams().id);
  const { data } = useClient(id);
  const role = useRole();
  const [edit, setEdit] = useState(false);
  const [newCase, setNewCase] = useState(false);
  const action = useDealAction<unknown>();
  const form = useForm();
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }
  return (
    <>
      <PageTitle
        title={data.name}
        meta={<span className="flex items-center gap-2">{data.ref} · {data.approval_levels} approval levels · {data.ai_permitted ? "AI permitted" : <NoAiBadge compact />}{data.archived_at && <Badge tone="neutral">Archived</Badge>}</span>}
        actions={
          <>
            <ActionButton variant="secondary" reason={role === "admin" ? (data.archived_at ? "Archived" : null) : "For the administrator"} onClick={() => setEdit(true)}>Edit</ActionButton>
            <ActionButton variant="secondary" reason={role === "admin" ? (data.archived_at ? "Archived" : null) : "For the administrator"} onClick={() => void form.run(() => action.mutateAsync(() => post(`/api/deals/clients/${id}/archive`, { note: "Archived by the administrator" })))}>Archive</ActionButton>
            <ActionButton reason={role === "onboarding_analyst" ? (data.archived_at ? "Archived" : null) : "For the onboarding analyst"} onClick={() => setNewCase(true)}>New case</ActionButton>
          </>
        }
      />
      <FormMessage message={form.message} />
      <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <Panel title="Onboarding cases" flush>
            <table className="w-full text-[0.8125rem]">
              <tbody>
                {data.case_list.map((c) => (
                  <tr key={c.id} className="border-b border-sand last:border-0">
                    <td className="px-3 py-2"><Link to={`/deals/cases/${c.id}`} className="font-mono text-xs font-semibold hover:underline">{c.ref}</Link></td>
                    <td className="py-2">{c.facility_name}</td>
                    <td className="py-2">{c.deal_type}</td>
                    <td className="py-2"><Badge tone={c.stage === "live" ? "ok" : "info"}>{STAGE_LABEL[c.stage]}</Badge></td>
                    <td className="numeric py-2 pr-3 text-right">{usd(c.commitment_cents)}</td>
                  </tr>
                ))}
                {data.case_list.length === 0 && <tr><td className="px-3 py-4 text-muted">No cases yet.</td></tr>}
              </tbody>
            </table>
          </Panel>
          <Panel title="Live facilities" flush>
            <table className="w-full text-[0.8125rem]">
              <tbody>
                {data.facility_list.map((f) => (
                  <tr key={f.id} className="border-b border-sand last:border-0">
                    <td className="px-3 py-2"><Link to={`/facilities/${f.id}`} className="font-mono text-xs font-semibold hover:underline">{f.ref}</Link></td>
                    <td className="py-2">{f.name}</td>
                    <td className="py-2">{f.status}</td>
                  </tr>
                ))}
                {data.facility_list.length === 0 && <tr><td className="px-3 py-4 text-muted">None live yet.</td></tr>}
              </tbody>
            </table>
          </Panel>
          <Panel title="Stored tape mappings" meta="This client's only; never shared">
            {data.mappings.length === 0 ? <p className="text-xs text-muted">None yet.</p> : (
              <ul className="space-y-1 text-xs">
                {data.mappings.map((m) => (
                  <li key={m.signature}><span className="font-mono text-muted">{m.signature}</span> · {m.headers.length} columns · {when(m.updated_at)}</li>
                ))}
              </ul>
            )}
            {Object.keys(data.master_field_overrides).length > 0 && (
              <p className="mt-2 text-xs">Overrides: {Object.entries(data.master_field_overrides).map(([f, c]) => `${f} ← ${c}`).join(", ")}</p>
            )}
          </Panel>
        </div>
        <Panel title="Activity">
          <Activity history={data.history} />
        </Panel>
      </div>
      {edit && <ClientForm client={data} open={edit} onOpenChange={setEdit} />}
      {newCase && <NewCaseDialog open={newCase} onOpenChange={setNewCase} clientId={data.id} />}
    </>
  );
}

const DEAL_TYPES = ["Consumer instalment", "SME loans", "Auto ABS", "Equipment finance", "Fund finance", "Other"];

export function NewCaseDialog({ open, onOpenChange, clientId }: { open: boolean; onOpenChange: (open: boolean) => void; clientId?: number }) {
  const { data: clients } = useClients();
  const form = useForm();
  const action = useDealAction<{ id: number }>();
  const navigate = useNavigate();
  const [values, setValues] = useState({ client_id: clientId ?? 0, facility_name: "", deal_type: "", commitment: "" });
  const set = (key: string, value: unknown) => setValues((v) => ({ ...v, [key]: value }));
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="New onboarding case">
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void form
            .run(() => action.mutateAsync(() => post<{ id: number }>("/api/deals/cases", { ...values, client_id: Number(values.client_id) || null, commitment: values.commitment ? Number(values.commitment.replace(/[^\d.]/g, "")) : null })))
            .then((saved) => {
              if (saved) {
                onOpenChange(false);
                navigate(`/deals/cases/${saved.id}/documents`);
              }
            });
        }}
      >
        <FormMessage message={form.message} />
        <Field id="case-client" label="Client" error={form.errors.client_id}>
          <Select id="case-client" value={values.client_id} onChange={(e) => set("client_id", Number(e.target.value))} invalid={Boolean(form.errors.client_id)}>
            <option value={0}>Choose a client</option>
            {(clients ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.ai_permitted ? "" : " (no AI)"}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="case-facility" label="Facility name" error={form.errors.facility_name}>
          <TextInput id="case-facility" value={values.facility_name} onChange={(e) => set("facility_name", e.target.value)} invalid={Boolean(form.errors.facility_name)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field id="case-type" label="Deal type" error={form.errors.deal_type}>
            <Select id="case-type" value={values.deal_type} onChange={(e) => set("deal_type", e.target.value)} invalid={Boolean(form.errors.deal_type)}>
              <option value="">Choose</option>
              {DEAL_TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </Select>
          </Field>
          <Field id="case-commitment" label="Commitment (US$)" error={form.errors.commitment}>
            <TextInput id="case-commitment" inputMode="decimal" value={values.commitment} onChange={(e) => set("commitment", e.target.value)} invalid={Boolean(form.errors.commitment)} />
          </Field>
        </div>
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button size="sm" type="submit" disabled={form.busy}>Open case</Button>
        </div>
      </form>
    </Dialog>
  );
}
