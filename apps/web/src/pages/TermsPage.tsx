import clsx from "clsx";
import { Check, Pencil, Send } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { EvidencePanel } from "../components/evidence/EvidencePanel";
import {
  Confidence,
  Kbd,
  ProvenanceChip,
  StatusPill,
  TierBadge,
  type ConfidenceLevel,
} from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader, SeedNotice } from "../components/ui/PageHeader";
import { formatDate } from "../lib/format";
import { termStatus, useSession } from "../lib/session";
import { useKeys } from "../lib/useKeys";
import { useWorkbench, type Citation, type Term } from "../lib/workbench";

type Filter = "all" | "tier1" | "open";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "tier1", label: "Tier 1" },
  { id: "open", label: "Needs review" },
];

const START = Date.UTC(2026, 0, 15);
const END = Date.UTC(2026, 3, 30);
const DAY = 86_400_000;

function AsOfControl({ onCitation, term }: { term: Term; onCitation: (c: Citation) => void }) {
  const [time, setTime] = useState(END);
  const EFFECTIVE = Date.parse(`${term.effective_from ?? "2026-03-01"}T00:00:00Z`);
  const original = term.original_value ?? "85%";
  const current = term.amended_value ?? "82.5%";
  const amended = time >= EFFECTIVE;
  const iso = new Date(time).toISOString().slice(0, 10);
  const markerPct = ((EFFECTIVE - START) / (END - START)) * 100;

  function change(value: number) {
    setTime(value);
    const cited = value >= EFFECTIVE ? term.source : term.also_cited[0];
    if (cited) {
      onCitation(cited);
    }
  }

  return (
    <div className="rounded-lg bg-canvas p-4">
      <div className="flex items-baseline justify-between gap-3">
        <SectionLabel>Advance rate as of</SectionLabel>
        <span className="numeric text-sm font-medium">{formatDate(iso)}</span>
      </div>
      <div className="mt-2 flex items-baseline gap-3">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={amended ? "amended" : "original"}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.18 }}
            className="numeric text-[2rem] leading-none font-semibold tracking-tight"
          >
            {amended ? current : original}
          </motion.span>
        </AnimatePresence>
        {amended && <s className="numeric text-lg text-muted">{original}</s>}
        <span className="text-[0.8125rem] text-muted">
          {amended ? "Amendment No. 1, 2(a)" : "Credit Agreement 2.3"}
        </span>
      </div>
      <div className="relative mt-3">
        <input
          type="range"
          aria-label="Date the advance rate is read as of"
          min={START}
          max={END}
          step={DAY}
          value={time}
          onChange={(event) => change(Number(event.target.value))}
          className="w-full cursor-pointer accent-ink"
        />
        <span
          aria-hidden
          className="absolute -bottom-0.5 h-2 w-0.5 bg-ink"
          style={{ left: `${markerPct}%` }}
        />
      </div>
      <div className="numeric mt-1 flex justify-between text-[0.6875rem] text-muted">
        <span>15 Jan 2026</span>
        <span>1 Mar: amendment effective</span>
        <span>30 Apr 2026</span>
      </div>
    </div>
  );
}

function TermRow({
  term,
  selected,
  value,
  status,
  onSelect,
}: {
  term: Term;
  selected: boolean;
  value: string;
  status: "approved" | "review" | "missing";
  onSelect: () => void;
}) {
  return (
    <tr
      onClick={onSelect}
      aria-selected={selected}
      className={clsx(
        "cursor-pointer border-b border-sand transition-colors duration-75 last:border-0",
        selected ? "bg-sand" : "hover:bg-canvas",
      )}
    >
      <td className="relative py-2.5 pr-3 pl-4">
        {selected && <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-accent" />}
        <button
          type="button"
          onClick={onSelect}
          className="cursor-pointer text-left text-sm font-medium"
        >
          {term.name}
        </button>
      </td>
      <td className={clsx("py-2.5 pr-3 text-sm", term.status === "missing" && "text-muted")}>
        {value}
      </td>
      <td className="py-2.5 pr-3">
        <TierBadge tier={term.tier} />
      </td>
      <td className="py-2.5 pr-3">
        {term.confidence === "none" ? (
          <span className="text-xs text-muted">None</span>
        ) : (
          <Confidence level={term.confidence as ConfidenceLevel} />
        )}
      </td>
      <td className="py-2.5 pr-4">
        <StatusPill status={status} />
      </td>
    </tr>
  );
}

export function TermsPage() {
  const { data } = useWorkbench();
  const { state, dispatch } = useSession();
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedName, setSelectedName] = useState("Advance rate");
  const [override, setOverride] = useState<Citation | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState("");

  const terms = useMemo(() => data?.terms ?? [], [data]);
  const visible = terms.filter((term) => {
    if (filter === "tier1") {
      return term.tier === 1;
    }
    return filter === "open" ? termStatus(term, state) !== "approved" : true;
  });
  const selected = terms.find((term) => term.name === selectedName) ?? terms[0];
  const bulk = terms.filter(
    (term) =>
      term.tier > 1 && term.confidence === "high" && termStatus(term, state) === "review",
  );

  function move(step: number) {
    const index = visible.findIndex((term) => term.name === selectedName);
    const next = visible[index + step];
    if (next) {
      setSelectedName(next.name);
      setOverride(null);
    }
  }

  function approve() {
    if (selected && selected.status !== "missing") {
      dispatch({ type: "approve-term", name: selected.name });
    }
  }

  function startEdit() {
    setDraft(state.termEdits[selected.name] ?? selected.value);
    setReason("");
    setEditing(true);
  }

  useKeys({
    j: () => move(1),
    k: () => move(-1),
    a: approve,
    e: () => selected && startEdit(),
    q: () => selected && dispatch({ type: "queue-term", name: selected.name }),
  });

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data || !selected) {
    return <Skeleton className="h-96 w-full" />;
  }

  const approved = terms.filter((term) => termStatus(term, state) === "approved").length;
  const citation = override ?? selected.source;

  return (
    <div>
      <PageHeader
        title="Facility terms"
        summary={`${approved} of ${terms.length} approved. Tier 1 terms require analyst approval at any confidence level.`}
        actions={
          <Button
            variant="secondary"
            disabled={bulk.length === 0}
            onClick={() => dispatch({ type: "bulk-approve", names: bulk.map((t) => t.name) })}
          >
            <Check aria-hidden className="size-4" />
            Approve high-confidence Tier 2 and 3 ({bulk.length})
          </Button>
        }
      />
      {data.seed && (
        <SeedNotice>
          Reference data: values are from the reference set. Highlights are located in the source PDFs.
        </SeedNotice>
      )}

      <div className="grid grid-cols-[minmax(0,1fr)_34rem] items-start gap-5">
        <Card className="overflow-hidden">
          <div className="flex items-center gap-1 border-b border-line p-2">
            {FILTERS.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-pressed={filter === item.id}
                onClick={() => setFilter(item.id)}
                className={clsx(
                  "h-8 cursor-pointer rounded-md px-3 text-[0.8125rem] font-medium",
                  filter === item.id ? "bg-ink text-white" : "text-muted hover:bg-sand",
                )}
              >
                {item.label}
              </button>
            ))}
            <span className="ml-auto flex items-center gap-1.5 pr-2 text-xs text-muted">
              <Kbd>J</Kbd>
              <Kbd>K</Kbd>
              move
              <Kbd>A</Kbd>
              approve
              <Kbd>E</Kbd>
              edit
              <Kbd>Q</Kbd>
              queue
            </span>
          </div>
          <div className="max-h-[calc(100vh-19rem)] overflow-y-auto">
            <table className="w-full text-left">
              <thead className="sticky top-0 z-10 bg-surface">
                <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
                  <th className="py-2 pr-3 pl-4">Term</th>
                  <th className="py-2 pr-3">Value</th>
                  <th className="py-2 pr-3">Tier</th>
                  <th className="py-2 pr-3">Confidence</th>
                  <th className="py-2 pr-4">Status</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((term) => (
                  <TermRow
                    key={term.name}
                    term={term}
                    selected={term.name === selected.name}
                    value={state.termEdits[term.name] ?? term.value}
                    status={termStatus(term, state)}
                    onSelect={() => {
                      setSelectedName(term.name);
                      setOverride(null);
                    }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="sticky top-32 space-y-4 p-5">
          <div>
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-lg leading-snug font-semibold">{selected.name}</h2>
              <StatusPill status={termStatus(selected, state)} />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <TierBadge tier={selected.tier} />
              <ProvenanceChip kind={state.termEdits[selected.name] ? "edited" : "ai"} />
              <span className="text-[0.8125rem] text-muted">{selected.clause}</span>
            </div>
          </div>

          {selected.name === "Advance rate" ? (
            <AsOfControl key={selected.name} term={selected} onCitation={setOverride} />
          ) : (
            <p className="text-xl font-semibold tracking-tight">
              {state.termEdits[selected.name] ?? selected.value}
            </p>
          )}

          <EvidencePanel
            citation={citation}
            documents={data.documents}
            emptyText={
              selected.status === "missing"
                ? "Schedule 4 was not in the pack, so there is no source page."
                : "Source is a workbook. No page preview available."
            }
          />

          {selected.also_cited.length > 0 && (
            <div className="space-y-1">
              <SectionLabel>Sources</SectionLabel>
              {[selected.source, ...selected.also_cited].filter(Boolean).map((item) => (
                <button
                  key={`${item!.document}-${item!.page}`}
                  type="button"
                  onClick={() => setOverride(item)}
                  aria-pressed={citation === item}
                  className={clsx(
                    "block w-full cursor-pointer rounded-md px-2 py-1 text-left text-[0.8125rem] hover:bg-sand",
                    citation === item ? "font-medium text-ink" : "text-muted",
                  )}
                >
                  {item!.label ?? selected.clause}, page {item!.page}
                  {item!.note && <span className="font-normal text-muted"> ({item!.note})</span>}
                </button>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            <Button
              className="flex-1"
              disabled={selected.status === "missing" || termStatus(selected, state) === "approved"}
              onClick={approve}
            >
              <Check aria-hidden className="size-4" />
              Approve
            </Button>
            <Button variant="secondary" onClick={startEdit}>
              <Pencil aria-hidden className="size-4" />
              Edit
            </Button>
            <Button
              variant="secondary"
              onClick={() => dispatch({ type: "queue-term", name: selected.name })}
            >
              <Send aria-hidden className="size-4" />
              Send to queue
            </Button>
          </div>
        </Card>
      </div>

      <Dialog
        open={editing}
        onOpenChange={setEditing}
        title={`Edit ${selected.name}`}
        description="The change is logged with your name and reason."
      >
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            dispatch({ type: "edit-term", name: selected.name, value: draft, reason });
            setEditing(false);
          }}
        >
          <label className="block text-sm font-medium">
            Value
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-line px-3 font-normal"
            />
          </label>
          <label className="block text-sm font-medium">
            Reason
            <textarea
              required
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={2}
              className="mt-1 w-full rounded-lg border border-line px-3 py-2 font-normal"
            />
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!reason.trim()}>
              Save edit
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
