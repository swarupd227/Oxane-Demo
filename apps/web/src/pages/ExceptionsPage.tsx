import clsx from "clsx";
import { ArrowUpRight, BellRing, Check, Send } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { EvidencePanel } from "../components/evidence/EvidencePanel";
import { Kbd, ProvenanceChip, StatusPill, TierBadge } from "../components/ui/badges";
import { Avatar } from "../components/ui/Avatar";
import { Timeline, useHistory } from "../components/ui/Timeline";
import { formatDateTime } from "../lib/format";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { KeyHints, NeedsIntake, NextStep, PageHeader, SeedNotice } from "../components/ui/PageHeader";
import { LoanDrill } from "../components/validation/LoanDrill";
import { formatUsd } from "../lib/format";
import { useSession, type ExceptionOutcome } from "../lib/session";
import { useKeys } from "../lib/useKeys";
import { useValidationRun, useWorkbench, type ExceptionItem } from "../lib/workbench";

const OUTCOMES: Record<ExceptionOutcome, string> = {
  accepted: "Accepted",
  queried: "Query drafted",
  escalated: "Escalated",
};

const TYPE_LABELS = { missing: "Missing", conflicting: "Conflicting", ambiguous: "Ambiguous" };
const TYPE_TONES = { missing: "bg-danger-tint text-danger", conflicting: "bg-warn-tint text-warn", ambiguous: "bg-info-tint text-info" };

function QueueRow({
  item,
  selected,
  outcome,
  onSelect,
}: {
  item: ExceptionItem;
  selected: boolean;
  outcome?: ExceptionOutcome;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        aria-current={selected || undefined}
        onClick={onSelect}
        className={clsx(
          "relative block w-full cursor-pointer border-b border-line/70 px-4 py-3.5 text-left transition-colors duration-75",
          selected ? "bg-accent-tint/60" : "hover:bg-canvas",
        )}
      >
        {selected && <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-accent" />}
        <div className="flex items-center gap-2">
          <span className="numeric font-mono text-[0.6875rem] text-subtle">{item.id}</span>
          <span className={clsx("inline-flex h-5 items-center rounded-full px-2 text-[0.6875rem] font-medium", TYPE_TONES[item.type])}>
            {TYPE_LABELS[item.type]}
          </span>
          {item.blocking && !outcome && (
            <span className="inline-flex items-center gap-1 text-[0.6875rem] font-medium text-danger">
              <span aria-hidden className="size-1.5 rounded-full bg-danger" />
              Blocking
            </span>
          )}
          <span className="ml-auto">{outcome && <StatusPill status="approved" label={OUTCOMES[outcome]} />}</span>
        </div>
        <p className={clsx("mt-1.5 text-sm leading-snug", outcome ? "text-subtle" : selected ? "font-medium text-accent-strong" : "font-medium text-ink")}>
          {item.title}
        </p>
        <p className="mt-0.5 truncate text-xs text-subtle">{item.label}</p>
      </button>
    </li>
  );
}

const DRAFTS: Record<string, { to: string; body: string }> = {
  X2: {
    to: "Borrower's counsel",
    body: "Please send Schedule 4 (Restricted Jurisdictions) to the Credit Agreement. It was not in the pack we received.",
  },
  X4: {
    to: "Bramble Auto Receivables I LLC, Treasurer",
    body: "Your April 2026 certificate applies a 60-day past-due test. Schedule 1, paragraph 1 specifies 30 days. Please reissue the certificate. 41 loans are affected.",
  },
  X7: {
    to: "Bramble Auto Finance LLC, Servicing",
    body: "Recoveries are blank for April in section 2 of the servicer report. Please confirm the figure.",
  },
};

export function ExceptionsPage() {
  const { data } = useWorkbench();
  const { state, dispatch } = useSession();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState(params.get("id") ?? "X4");
  const history = useHistory([selectedId]);
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState("");
  const runQuery = useValidationRun(state.dealerMatched, state.ran);
  // While the matched run loads, the query still holds the unmatched one. It must not be shown as the result.
  const run = runQuery.isPlaceholderData ? undefined : runQuery.data;
  const earlier = useValidationRun(false, state.ran).data;

  const items = [...(data?.exceptions ?? []), ...state.heldItems];
  const selected = items.find((item) => item.id === selectedId) ?? items[0];

  function work(outcome: ExceptionOutcome, note: string) {
    dispatch({ type: "work-exception", id: selected.id, outcome, note, term: selected.term });
  }

  function act(action: ExceptionItem["actions"][number]) {
    if (action === "accept") {
      work("accepted", selected.suggestion);
    } else if (action === "escalate") {
      work("escalated", "Escalated to credit for a decision");
    } else {
      setDraft(DRAFTS[selected.id]?.body ?? "");
      setDrafting(true);
    }
  }

  const open = items.filter((item) => !state.exceptions[item.id]);
  const raised = state.startedAt;

  useKeys({
    j: () => {
      const next = items[items.indexOf(selected) + 1];
      if (next) {
        setSelectedId(next.id);
      }
    },
    k: () => {
      const next = items[items.indexOf(selected) - 1];
      if (next) {
        setSelectedId(next.id);
      }
    },
    a: () => selected?.actions.includes("accept") && act("accept"),
    q: () => selected?.actions.includes("query") && act("query"),
    x: () => selected?.actions.includes("escalate") && act("escalate"),
  });

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data || !selected) {
    return <Skeleton className="h-96 w-full" />;
  }

  const outcome = state.exceptions[selected.id];
  const primary = selected.actions.includes("accept") ? "accept" : selected.actions[0];
  const drill = run?.pool_bridge.lines.find((line) => line.rule_id === selected.drill);
  const matchDone = selected.recalculates && outcome === "accepted" && earlier && run;

  return (
    <div>
      <PageHeader
        title="Exception queue"
        summary={`${open.length} open of ${items.length} · ${items.filter((item) => item.blocking).length} blocking · raised ${raised ? formatDateTime(raised) : "-"}`}
        actions={<NextStep to="/approve" label="View approval" />}
      />
      {data.seed && (
        <SeedNotice>
          Reference data: queue items are from the reference set. Loans and recalculations are
          calculated.
        </SeedNotice>
      )}

      <div className="grid grid-cols-[24rem_minmax(0,1fr)] items-start gap-5 2xl:grid-cols-[28rem_minmax(0,1fr)]">
        <Card className="sticky top-16 overflow-hidden">
          <ul className="max-h-[calc(100vh-17rem)] overflow-y-auto">
            {items.map((item) => (
              <QueueRow
                key={item.id}
                item={item}
                selected={item.id === selected.id}
                outcome={state.exceptions[item.id]}
                onSelect={() => setSelectedId(item.id)}
              />
            ))}
          </ul>
          <KeyHints>
          <p className="flex items-center gap-1.5 border-t border-line px-4 py-2 text-xs text-muted">
            <Kbd>J</Kbd>
            <Kbd>K</Kbd>
            move
            <Kbd>A</Kbd>
            accept
            <Kbd>Q</Kbd>
            query
            <Kbd>X</Kbd>
            escalate
          </p>
          </KeyHints>
        </Card>

        <Card className="overflow-hidden">
          <div className="p-6">
            <div className="flex flex-wrap items-center gap-2">
              <span className="numeric font-mono text-xs text-subtle">{selected.id}</span>
              <StatusPill
                status={selected.type === "missing" ? "missing" : "review"}
                label={TYPE_LABELS[selected.type]}
              />
              <span className="text-[0.8125rem] text-muted">{selected.label}</span>
              {selected.tier1 && <TierBadge tier={1} />}
              {selected.blocking && <StatusPill status="missing" label="Blocking" />}
              {raised && (
                <span className="numeric ml-auto text-xs text-subtle">Raised {formatDateTime(raised)}</span>
              )}
            </div>
            <h2 className="mt-2 text-lg leading-snug font-semibold text-ink">
              {selected.title}
            </h2>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg border border-line px-3 py-2.5">
                <SectionLabel>Where</SectionLabel>
                <p className="mt-0.5 text-ink-soft">{selected.where}</p>
              </div>
              <div className="rounded-lg border border-line px-3 py-2.5">
                <SectionLabel>Owner</SectionLabel>
                <p className="mt-0.5 flex items-center gap-1.5 text-ink-soft">
                  <Avatar name={selected.owner} />
                  {selected.owner}
                </p>
              </div>
            </div>
            <div className="mt-5">
              <SectionLabel>Evidence</SectionLabel>
              <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-snug text-ink-soft marker:text-stone">
                {selected.evidence.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
            <div className="mt-4 rounded-xl border border-accent/20 bg-accent-tint/50 px-4 py-3">
              <p className="flex items-center gap-2">
                <SectionLabel>Recommended action</SectionLabel>
                <ProvenanceChip
                  kind="suggested"
                  tip={selected.evidence[0] ?? selected.where}
                />
              </p>
              <p className="mt-1 text-sm font-medium text-ink">{selected.suggestion}</p>
            </div>
            <div className="mt-4 flex items-center gap-2">
              {selected.actions.includes("accept") && (
                <Button variant={primary === "accept" ? "primary" : "secondary"} disabled={Boolean(outcome)} onClick={() => act("accept")}>
                  <Check aria-hidden className="size-4" />
                  Accept
                </Button>
              )}
              {selected.actions.includes("query") && (
                <Button variant={primary === "query" ? "primary" : "secondary"} disabled={Boolean(outcome)} onClick={() => act("query")}>
                  <Send aria-hidden className="size-4" />
                  Draft query
                </Button>
              )}
              {selected.actions.includes("escalate") && (
                <Button variant={primary === "escalate" ? "primary" : "secondary"} disabled={Boolean(outcome)} onClick={() => act("escalate")}>
                  <ArrowUpRight aria-hidden className="size-4" />
                  Escalate to credit
                </Button>
              )}
              {outcome && <StatusPill status="approved" label={OUTCOMES[outcome]} />}
            </div>
            <div className="mt-4 border-t border-line pt-3">
              <SectionLabel>History</SectionLabel>
              <Timeline
                className="mt-2"
                entries={history}
                empty={raised ? `Raised ${formatDateTime(raised)} · not yet worked` : "Not yet worked"}
              />
            </div>
          </div>

          {matchDone && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mx-5 mb-5 rounded-lg bg-danger-tint p-4"
            >
              <p className="flex items-center gap-2 text-sm font-semibold text-danger">
                <BellRing aria-hidden className="size-4" />
                Borrowing base recalculated
              </p>
              <p className="numeric mt-1 text-sm">
                Excess of {formatUsd(run.system.excess)} takes availability from{" "}
                {formatUsd(earlier.system.availability)} to{" "}
                <span className="font-semibold">{formatUsd(run.system.availability)}</span>, below
                the Calderwood alert threshold of US$500,000.
              </p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-2"
                onClick={() => navigate("/validation")}
              >
                View bridge
              </Button>
            </motion.div>
          )}

          {drill ? (
            <div className="border-t border-line">
              <LoanDrill line={drill} />
            </div>
          ) : (
            selected.source && (
              <div className="border-t border-line p-5">
                <EvidencePanel citation={selected.source} documents={data.documents} />
              </div>
            )
          )}
        </Card>
      </div>

      <Dialog
        open={drafting}
        onOpenChange={setDrafting}
        title="Draft query"
        description={`To: ${DRAFTS[selected.id]?.to ?? selected.owner}`}
      >
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            work("queried", draft);
            setDrafting(false);
          }}
        >
          <textarea
            aria-label="Query text"
            rows={5}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="w-full rounded-lg border border-line px-3 py-2 text-sm leading-relaxed"
          />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDrafting(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!draft.trim()}>
              Log query
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
