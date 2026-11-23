/* Partial reuse: each bank's rule library, the layouts reused per sender, and what each
 * facility set for itself. Read from the facility record; code only. */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Skeleton } from "../../components/ui/layout";
import { Badge, Kpis, Panel, RecordId } from "../ui";

export interface FacilityReuse {
  facility: string;
  name: string;
  client: string;
  kind: string;
  library: { name: string; version: number; owner: string };
  rules: { id: string; rule: string; from: "bank_library"; parameter: string; parameter_from: "facility" }[];
  validation_sets: { set: string; from: "bank_library" }[];
  layouts: { id: string | null; document: string; sender: string; version: number | null; from: "sender_layout" | "lender_template" | "facility"; shared_with: string[] }[];
  specific: { rule: string; from: "facility" }[];
  counts: { library_rules: number; facility_rules: number; reused_layouts: number; own_layouts: number };
}

export interface Reuse {
  libraries: { client: string; name: string; version: number; owner: string; updated: string; facilities: number; rules: { id: string; rule: string; kinds: string[]; facilities: string[] }[] }[];
  facilities: FacilityReuse[];
}

export function useReuse() {
  return useQuery({
    queryKey: ["cycle-reuse"],
    queryFn: async () => {
      const response = await fetch("/api/monitoring/reuse");
      if (!response.ok) {
        throw new Error(`Reuse ${response.status}`);
      }
      return (await response.json()) as Reuse;
    },
    staleTime: Infinity,
  });
}

const LAYOUT_FROM = { sender_layout: "Reused from the sender's layout", lender_template: "Bank's summary template", facility: "Set for this facility" };

export function FacilityReusePanel({ reuse }: { reuse: FacilityReuse }) {
  return (
    <div className="space-y-3">
      <Kpis
        items={[
          { label: "Rules from the bank's library", value: reuse.counts.library_rules },
          { label: "Facility-specific rules", value: reuse.counts.facility_rules },
          { label: "Layouts reused from senders", value: reuse.counts.reused_layouts },
          { label: "Layouts set for this facility", value: reuse.counts.own_layouts },
        ]}
      />
      <Panel title={`${reuse.library.name} v${reuse.library.version}`} meta={`Owner ${reuse.library.owner} · thresholds and clauses are this facility's own`} flush>
        <table className="w-full text-xs">
          <thead><tr className="border-b border-line text-left text-[0.6875rem] text-muted uppercase"><th className="px-3 py-1">Rule</th><th>From</th><th className="pr-3">This facility's threshold</th></tr></thead>
          <tbody>
            {reuse.rules.map((r) => (
              <tr key={r.id} className="border-b border-sand last:border-0">
                <td className="px-3 py-1.5"><RecordId>{r.id}</RecordId> {r.rule}</td>
                <td><Badge tone="info">Bank library</Badge></td>
                <td className="pr-3"><Badge tone="neutral">Facility-specific</Badge> {r.parameter}</td>
              </tr>
            ))}
            {reuse.validation_sets.map((v) => (
              <tr key={v.set} className="border-b border-sand last:border-0">
                <td className="px-3 py-1.5">Validation set <span className="font-mono">{v.set}</span></td>
                <td><Badge tone="info">Bank library</Badge></td>
                <td className="pr-3 text-muted">Same blocking and warning checks</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Data layouts" flush>
        <table className="w-full text-xs">
          <tbody>
            {reuse.layouts.map((l) => (
              <tr key={`${l.id}-${l.document}`} className="border-b border-sand last:border-0">
                <td className="px-3 py-1.5">{l.id && <RecordId>{l.id}</RecordId>} {l.document}{l.version && <span className="text-muted"> v{l.version}</span>}</td>
                <td>{l.sender}</td>
                <td className="pr-3">
                  <Badge tone={l.from === "facility" ? "neutral" : "info"}>{LAYOUT_FROM[l.from]}</Badge>
                  {l.shared_with.length > 0 && <span className="ml-1 text-muted">also {l.shared_with.join(", ")}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Set for this facility alone">
        {reuse.specific.length ? <ul className="list-disc pl-4 text-xs">{reuse.specific.map((s) => <li key={s.rule}>{s.rule}</li>)}</ul> : <p className="text-xs text-muted">Nothing beyond its thresholds: every rule came from the bank's library.</p>}
      </Panel>
    </div>
  );
}

export function ReuseView({ client }: { client: string }) {
  const { data } = useReuse();
  const [selected, setSelected] = useState<string>("northmoor");
  if (!data) {
    return <Skeleton className="h-64 w-full" />;
  }
  const facilities = data.facilities.filter((f) => client === "all" || f.client === client);
  const current = facilities.find((f) => f.facility === selected) ?? facilities[0];
  const libraries = data.libraries.filter((l) => client === "all" || l.client === client);
  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
      <div className="space-y-3">
        {libraries.map((l) => (
          <Panel key={l.client} title={l.name} meta={`v${l.version} · ${l.owner} · used by ${l.facilities} facilities`} flush>
            <ul className="text-xs">
              {l.rules.map((r) => (
                <li key={r.id} className="flex items-start gap-2 border-b border-sand px-3 py-1.5 last:border-0">
                  <RecordId>{r.id}</RecordId>
                  <span className="flex-1">{r.rule}</span>
                  <span className="numeric text-muted">{r.facilities.length}</span>
                </li>
              ))}
            </ul>
          </Panel>
        ))}
        <p className="text-[0.6875rem] text-muted">A bank's library is offered only to its own facilities: nothing is pooled across clients.</p>
      </div>
      <div className="space-y-3">
        <label className="flex items-center gap-2 text-xs">
          Facility
          <select aria-label="Facility" className="h-8 rounded border border-line bg-surface px-2 text-xs" value={current?.facility} onChange={(e) => setSelected(e.target.value)}>
            {facilities.map((f) => <option key={f.facility} value={f.facility}>{f.name}</option>)}
          </select>
        </label>
        {current && <FacilityReusePanel reuse={current} />}
      </div>
    </div>
  );
}
