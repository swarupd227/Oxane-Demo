import clsx from "clsx";
import { ArrowRight, Bot, CheckCircle2, FileText, Gavel, ListChecks, Scale } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { PageHeader } from "../../components/ui/PageHeader";
import { OUTCOMES, Refusal, useCycle, useCycleAction, useCycleSession, type Finding, type Outcome, type Source } from "../cycle";
import { FacilityTag, OutcomePill, SourcePanel } from "../parts";

const COLUMNS: Outcome[] = ["query", "confirmed", "expert", "logged"];
const ICONS = { query: FileText, confirmed: CheckCircle2, expert: Scale, logged: ListChecks };

export function TriagePage() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const action = useCycleAction();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [change, setChange] = useState<Outcome | null>(null);
  const [note, setNote] = useState("");
  const [source, setSource] = useState<Source | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  const byColumn = useMemo(() => {
    const groups: Record<Outcome, Finding[]> = { query: [], confirmed: [], expert: [], logged: [] };
    for (const finding of cycle?.findings ?? []) {
      groups[session?.decisions[finding.id] ?? finding.suggested.outcome].push(finding);
    }
    return groups;
  }, [cycle, session]);

  const selected = cycle?.findings.find((f) => f.id === selectedId) ?? null;
  useEffect(() => {
    if (!selectedId && cycle) {
      setSelectedId(cycle.findings.find((f) => !f.rule_outcome)?.id ?? null);
    }
  }, [cycle, selectedId]);

  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const names = Object.fromEntries(cycle.facilities.map((f) => [f.id, f.name.split(" ")[0]]));
  const open = cycle.findings.filter((f) => !session?.decisions[f.id]);
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
            setSelectedId(next.id);
            setSource(undefined);
          }
        },
        onError: (e) => setError(e instanceof Refusal ? e.message : "The decision could not be saved."),
      },
    );
  };
  const decided = selected ? session?.decisions[selected.id] : null;
  const evidence = selected ? [...selected.sources.filter(Boolean), ...selected.clauses] : [];
  const shown = source === undefined ? (evidence[0] as Source | undefined) : source;

  return (
    <>
      <PageHeader
        title="Triage"
        summary="Every finding goes to one of four outcomes, with its reason. Rules log what is within tolerance; the AI suggests the rest; the analyst decides."
        actions={
          <>
            <span className="numeric text-sm text-muted">{open.length ? `${open.length} to decide` : "All decided"}</span>
            <Button onClick={() => navigate("/monitoring/pack")}>
              Lender pack
              <ArrowRight aria-hidden className="size-4" />
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] gap-5">
        <div className="grid grid-cols-2 gap-4">
          {COLUMNS.map((column) => {
            const Icon = ICONS[column];
            return (
              <section key={column} aria-label={OUTCOMES[column].label} className={clsx("rounded-xl border border-line p-3", column === "logged" ? "bg-canvas" : "bg-surface")}>
                <header className="mb-2 flex items-center justify-between px-1">
                  <p className="flex items-center gap-1.5 text-sm font-semibold">
                    <Icon aria-hidden className="size-4 text-muted" />
                    {column === "logged" ? "Held back: logged, no alert" : OUTCOMES[column].label}
                  </p>
                  <span className="numeric text-xs font-medium text-muted">{byColumn[column].length}</span>
                </header>
                <p className="mb-2 px-1 text-[0.6875rem] text-muted">{OUTCOMES[column].who}</p>
                <ul className="space-y-1.5">
                  {byColumn[column].map((finding) => {
                    const done = !!session?.decisions[finding.id];
                    return (
                      <li key={finding.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedId(finding.id);
                            setSource(undefined);
                            setChange(null);
                            setError(null);
                          }}
                          aria-current={finding.id === selectedId ? "true" : undefined}
                          className={clsx(
                            "w-full cursor-pointer rounded-lg border px-2.5 py-2 text-left transition-colors",
                            finding.id === selectedId ? "border-ink bg-canvas ring-1 ring-ink" : "border-line bg-surface hover:border-stone",
                          )}
                        >
                          <span className="flex items-center justify-between gap-2">
                            <span className="flex items-center gap-1">
                              {finding.facility.split(",").map((id) => (
                                <FacilityTag key={id} id={id} name={names[id]} />
                              ))}
                            </span>
                            {done ? (
                              <CheckCircle2 aria-label="Decided" className="size-3.5 text-ok" />
                            ) : (
                              <span className="text-[0.6875rem] font-medium text-muted">{finding.suggested.by === "AI" ? "Suggested" : "By rule"}</span>
                            )}
                          </span>
                          <span className="mt-1 line-clamp-2 block text-[0.8125rem] leading-snug font-medium">{finding.title}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>

        <div className="space-y-3">
          {selected ? (
            <Card className="p-5">
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-xs text-muted">
                  {selected.facility.split(",").map((id) => (
                    <FacilityTag key={id} id={id} name={names[id]} />
                  ))}
                  {selected.check}
                </span>
                <OutcomePill outcome={decided ?? null} />
              </div>
              <h2 className="mt-2 text-lg leading-snug font-semibold">{selected.title}</h2>
              <p className="mt-1 text-sm text-muted">{selected.detail}</p>
              <div className="mt-3 rounded-lg bg-canvas p-3">
                <p className="flex items-center gap-1.5 text-xs font-semibold">
                  {selected.suggested.by === "AI" ? <Bot aria-hidden className="size-3.5" /> : <Gavel aria-hidden className="size-3.5" />}
                  {selected.suggested.by === "AI" ? "AI suggests" : "Tolerance rule"}: {OUTCOMES[selected.suggested.outcome].label}
                </p>
                <p className="mt-1 text-sm">{selected.suggested.reason}</p>
              </div>
              {selected.clauses.length > 0 && (
                <div className="mt-3">
                  <SectionLabel>Clauses involved</SectionLabel>
                  <div className="mt-1.5 flex flex-wrap gap-2">
                    {selected.clauses.map((clause) => (
                      <Button key={clause.label} size="sm" variant="secondary" onClick={() => setSource(clause)}>
                        <FileText aria-hidden className="size-3.5" />
                        {clause.label}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
              {!decided && !selected.rule_outcome && (
                <div className="mt-4 border-t border-sand pt-4">
                  {change ? (
                    <div className="space-y-2">
                      <label className="block text-sm font-medium" htmlFor="triage-reason">
                        Reason for {OUTCOMES[change].label.toLowerCase()}
                      </label>
                      <textarea
                        id="triage-reason"
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        rows={2}
                        className="w-full rounded-lg border border-line px-3 py-2 text-sm"
                        placeholder="Why the suggestion does not fit"
                      />
                      <div className="flex gap-2">
                        <Button size="sm" disabled={!note.trim() || action.isPending} onClick={() => decide(selected, change, note)}>
                          Save decision
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setChange(null)}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-wrap items-center gap-2">
                      <Button disabled={action.isPending} onClick={() => decide(selected, selected.suggested.outcome)}>
                        <CheckCircle2 aria-hidden className="size-4" />
                        {selected.suggested.outcome === "query" ? "Confirm: query the sender" : selected.suggested.outcome === "expert" ? "Confirm: send to expert" : "Confirm issue"}
                      </Button>
                      {(["query", "confirmed", "expert"] as Outcome[])
                        .filter((o) => o !== selected.suggested.outcome)
                        .map((o) => (
                          <Button key={o} size="sm" variant="ghost" onClick={() => setChange(o)}>
                            {OUTCOMES[o].short} instead
                          </Button>
                        ))}
                    </div>
                  )}
                  {error && (
                    <p role="alert" className="mt-2 text-sm text-danger">
                      {error}
                    </p>
                  )}
                </div>
              )}
              {decided && session?.triage[selected.id]?.note && <p className="mt-3 text-sm text-muted">Analyst's reason: {session.triage[selected.id].note}</p>}
            </Card>
          ) : (
            <Card className="p-5 text-sm text-muted">Select a finding.</Card>
          )}
          <SourcePanel source={shown} emptyText="No document page for this finding: it comes from the tapes or the cycle's own records." />
        </div>
      </div>
    </>
  );
}
