import clsx from "clsx";
import { FileText, Quote } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/layout";
import { OUTCOMES, Refusal, useActor, useCycle, useCycleAction, useCycleSession, type Finding, type Outcome, type Source } from "../cycle";
import { useScope } from "../desk";
import { NoAiBadge, OutcomePill, SourcePanel } from "../parts";
import { Activity, Avatar, Badge, DataTable, FilterSelect, Kpis, PageTitle, Person, RecordId, SuggestedChip, useWide, when, type Column } from "../ui";

type View = "open" | "decided" | "logged" | "all";

export function TriagePage() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const { actor } = useActor();
  const { client } = useScope();
  const action = useCycleAction();
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<View>("open");
  const [check, setCheck] = useState("all");
  const [change, setChange] = useState<Outcome | null>(null);
  const [note, setNote] = useState("");
  const [source, setSource] = useState<Source | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  const ref = params.get("ref");
  const wide = useWide();
  const selected = cycle?.findings.find((f) => f.ref === ref) ?? null;
  useEffect(() => {
    if (!ref && cycle) {
      const first = cycle.findings.find((f) => !f.rule_outcome && !session?.decisions[f.id]) ?? cycle.findings[0];
      setParams({ ref: first.ref }, { replace: true });
    }
  }, [cycle, ref, session, setParams]);

  const state = (f: Finding): View => (f.rule_outcome ? "logged" : session?.decisions[f.id] ? "decided" : "open");
  const scoped = useMemo(
    () => (cycle?.findings ?? []).filter((f) => client === "all" || f.facility.split(",").some((id) => cycle?.facilities.find((x) => x.id === id)?.client === client)),
    [cycle, client],
  );
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const names = Object.fromEntries(cycle.facilities.map((f) => [f.id, f.name.split(" ")[0]]));
  const clientOf = (f: Finding) => cycle.clients.find((c) => c.id === cycle.facilities.find((x) => x.id === f.facility.split(",")[0])?.client)!;
  const rows = scoped.filter((f) => (view === "all" || state(f) === view) && (check === "all" || f.check === check));
  const pick = (f: Finding) => {
    setParams({ ref: f.ref }, { replace: true });
    setSource(undefined);
    setChange(null);
    setNote("");
    setError(null);
  };
  const decide = (finding: Finding, outcome: Outcome, reason?: string) => {
    setError(null);
    action.mutate(
      { type: "triage", payload: { id: finding.id, outcome, note: reason || null } },
      {
        onSuccess: () => {
          setChange(null);
          setNote("");
          const next = cycle.findings.find((f) => f.id !== finding.id && !f.rule_outcome && !session?.decisions[f.id]);
          if (next) {
            pick(next);
          }
        },
        onError: (e) => setError(e instanceof Refusal ? e.message : "The decision could not be saved."),
      },
    );
  };
  const allColumns: Column<Finding>[] = [
    { key: "ref", header: "Ref", sort: (f) => f.ref, render: (f) => <RecordId>{f.ref}</RecordId> },
    {
      key: "facility",
      header: "Facility",
      sort: (f) => f.facility,
      render: (f) => <span className="whitespace-nowrap">{f.facility.split(",").map((id) => names[id]).join(", ")}</span>,
    },
    {
      key: "title",
      header: "Exception",
      sort: (f) => f.title,
      render: (f) => (
        <span className="block min-w-44">
          <span className="line-clamp-1" title={f.title}>
            {f.title}
          </span>
          <span className="block text-[0.6875rem] text-muted">{f.check}</span>
        </span>
      ),
    },
    { key: "raised", header: "Raised", sort: (f) => f.raised, render: (f) => <span className="numeric whitespace-nowrap text-muted">{when(f.raised)}</span> },
    {
      key: "suggested",
      header: "Suggested",
      sort: (f) => f.suggested.outcome,
      render: (f) => (
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <SuggestedChip by={f.suggested.by} detail={f.suggested.reason} />
          <span className="text-xs">{OUTCOMES[f.suggested.outcome].short}</span>
        </span>
      ),
    },
    {
      key: "outcome",
      header: "Outcome",
      sort: (f) => session?.decisions[f.id] ?? "~",
      render: (f) => <OutcomePill outcome={session?.decisions[f.id] ?? null} pending="Open" />,
    },
    {
      key: "owner",
      header: "Assignee",
      sort: (f) => clientOf(f).contact.name,
      render: (f) => (
        <span title={clientOf(f).contact.name}>
          <Avatar name={clientOf(f).contact.name} size="md" />
        </span>
      ),
    },
  ];
  const columns = allColumns.filter((c) => (view !== "open" || c.key !== "outcome") && (wide || c.key !== "raised"));
  const decided = selected ? session?.decisions[selected.id] : null;
  const evidence = selected ? [...selected.sources.filter(Boolean), ...selected.clauses] : [];
  const shown = source === undefined ? (evidence[0] as Source | undefined) : source;
  const count = (v: View) => scoped.filter((f) => state(f) === v).length;
  const audit = (session?.audit ?? []).filter((a) => a.subject === selected?.id);
  const quote = selected?.explanation?.quote;
  return (
    <>
      <PageTitle title="Exceptions" meta={`${cycle.cycle.label} · ${scoped.length} raised`} />
      <Kpis
        items={[
          { label: "Open", value: count("open"), tone: count("open") ? "warn" : "ok", onClick: () => setView("open") },
          { label: "Decided", value: count("decided"), onClick: () => setView("decided") },
          { label: "Logged by rule", value: count("logged"), onClick: () => setView("logged") },
          { label: "Expert review", value: scoped.filter((f) => session?.decisions[f.id] === "expert").length },
          { label: "Queries to sender", value: scoped.filter((f) => session?.decisions[f.id] === "query").length },
          { label: "Confirmed", value: scoped.filter((f) => session?.decisions[f.id] === "confirmed").length },
        ]}
      />
      <div className={clsx("grid gap-3", wide ? "grid-cols-[minmax(0,1fr)_26rem]" : "grid-cols-[minmax(0,1fr)_22rem]")}>
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(f) => f.ref}
          selected={selected?.ref}
          onRowClick={pick}
          search={(f) => `${f.ref} ${f.title} ${f.check} ${f.facility} ${f.detail}`}
          searchPlaceholder="Filter exceptions"
          initialSort={{ key: "ref", dir: "asc" }}
          empty="No exceptions in this view."
          toolbar={
            <>
              <div role="tablist" aria-label="View" className="flex rounded-md border border-line p-0.5">
                {(["open", "decided", "logged", "all"] as View[]).map((v) => (
                  <button
                    key={v}
                    type="button"
                    role="tab"
                    aria-selected={view === v}
                    onClick={() => setView(v)}
                    className={clsx("h-6 cursor-pointer rounded px-2 text-xs capitalize", view === v ? "bg-ink text-white" : "text-muted hover:text-ink")}
                  >
                    {v === "logged" ? "Logged" : v}
                  </button>
                ))}
              </div>
              <FilterSelect label="Check" value={check} onChange={setCheck} options={[{ value: "all", label: "All checks" }, ...[...new Set(scoped.map((f) => f.check))].sort().map((c) => ({ value: c, label: c }))]} />
            </>
          }
        />

        <div className="space-y-3 self-start">
          {selected ? (
            <section aria-label={`Exception ${selected.ref}`} className="rounded-lg border border-line bg-surface">
              <div className="border-b border-line px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <RecordId>{selected.ref}</RecordId>
                    <Badge tone="neutral">{selected.check}</Badge>
                    {selected.blocking && <Badge tone="danger">Blocking</Badge>}
                    {!clientOf(selected).ai_permitted && <NoAiBadge compact />}
                  </span>
                  <OutcomePill outcome={decided ?? null} pending="Open" />
                </div>
                <h2 className="mt-1.5 text-sm leading-snug font-semibold">{selected.title}</h2>
                <dl className="mt-1.5 grid grid-cols-[5rem_1fr] gap-x-2 gap-y-0.5 text-xs">
                  <dt className="text-muted">Facility</dt>
                  <dd>{selected.facility.split(",").map((id) => cycle.facilities.find((f) => f.id === id)?.name).join("; ")}</dd>
                  <dt className="text-muted">Raised</dt>
                  <dd className="numeric">{when(selected.raised)}</dd>
                  <dt className="text-muted">Assignee</dt>
                  <dd>
                    <Person name={clientOf(selected).contact.name} />
                  </dd>
                  {selected.owner && (
                    <>
                      <dt className="text-muted">Party</dt>
                      <dd>{selected.owner}</dd>
                    </>
                  )}
                </dl>
              </div>
              <div className="px-3 py-2">
                <p className="text-[0.8125rem]">{selected.detail}</p>
                {quote && (
                  <button type="button" onClick={() => setSource(selected.explanation?.source ?? null)} className="mt-1.5 flex cursor-pointer items-start gap-1 text-left text-xs text-info hover:underline">
                    <Quote aria-hidden className="mt-0.5 size-3 shrink-0" />“{quote}”
                  </button>
                )}
                <div className="mt-2 rounded-md bg-canvas px-2.5 py-2">
                  <p className="flex items-center gap-1.5 text-xs">
                    <SuggestedChip by={selected.suggested.by} />
                    <span className="font-semibold">{OUTCOMES[selected.suggested.outcome].label}</span>
                  </p>
                  <p className="mt-1 text-xs text-muted">{selected.suggested.reason}</p>
                </div>
                {selected.clauses.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {selected.clauses.map((clause) => (
                      <button
                        key={clause.label}
                        type="button"
                        onClick={() => setSource(clause)}
                        className="inline-flex h-6 cursor-pointer items-center gap-1 rounded border border-line px-1.5 text-[0.6875rem] hover:border-stone"
                      >
                        <FileText aria-hidden className="size-3" />
                        {clause.label}
                      </button>
                    ))}
                  </div>
                )}
                {!decided && !selected.rule_outcome && (
                  <div className="mt-3 border-t border-sand pt-2.5">
                    {change ? (
                      <div className="space-y-1.5">
                        <label className="block text-xs font-medium" htmlFor="triage-reason">
                          Reason for {OUTCOMES[change].label.toLowerCase()}
                        </label>
                        <textarea id="triage-reason" value={note} onChange={(event) => setNote(event.target.value)} rows={2} className="w-full rounded-md border border-line px-2 py-1.5 text-[0.8125rem]" />
                        <div className="flex gap-2">
                          <Button size="sm" disabled={!note.trim() || action.isPending} onClick={() => decide(selected, change, note)}>
                            Save
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setChange(null)}>
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Button size="sm" disabled={action.isPending || actor !== "analyst"} onClick={() => decide(selected, selected.suggested.outcome)}>
                          Accept: {OUTCOMES[selected.suggested.outcome].short}
                        </Button>
                        {(["query", "confirmed", "expert"] as Outcome[])
                          .filter((o) => o !== selected.suggested.outcome)
                          .map((o) => (
                            <Button key={o} size="sm" variant="secondary" disabled={actor !== "analyst"} onClick={() => setChange(o)}>
                              {OUTCOMES[o].short}
                            </Button>
                          ))}
                        {actor !== "analyst" && <span className="text-xs text-muted">Preparer action</span>}
                      </div>
                    )}
                    {error && (
                      <p role="alert" className="mt-1.5 text-xs text-danger">
                        {error}
                      </p>
                    )}
                  </div>
                )}
              </div>
              <div className="border-t border-line px-3 py-2">
                <p className="mb-1.5 text-[0.6875rem] font-semibold text-muted">Activity</p>
                <Activity
                  entries={audit}
                  origin={[
                    ...(selected.rule_outcome ? [{ at: selected.raised, text: `Logged by rule: ${selected.suggested.reason}` }] : []),
                    { at: selected.raised, text: `Raised by ${selected.check.toLowerCase()} check` },
                  ]}
                />
              </div>
            </section>
          ) : (
            <p className="rounded-lg border border-dashed border-line p-4 text-xs text-muted">No exception selected.</p>
          )}
          <SourcePanel source={shown} emptyText="No document page: raised from tape data." />
        </div>
      </div>
    </>
  );
}
