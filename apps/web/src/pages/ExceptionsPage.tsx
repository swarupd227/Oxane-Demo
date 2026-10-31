import clsx from "clsx";
import { ArrowRight, ArrowUpRight, BellRing, Check, Lightbulb, Send } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { EvidencePanel } from "../components/evidence/EvidencePanel";
import { StatusPill, TierBadge, Kbd } from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader, SeedNotice } from "../components/ui/PageHeader";
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
          "relative block w-full cursor-pointer border-b border-sand px-4 py-3 text-left transition-colors duration-75",
          selected ? "bg-sand" : "hover:bg-canvas",
        )}
      >
        {selected && <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-accent" />}
        <div className="flex items-center justify-between gap-2">
          <span className="numeric text-xs font-semibold text-muted">
            {item.id} · {TYPE_LABELS[item.type]} · {item.label}
          </span>
          {outcome && <StatusPill status="approved" label={OUTCOMES[outcome]} />}
        </div>
        <p className={clsx("mt-1 text-sm leading-snug", outcome ? "text-muted" : "font-medium")}>
          {item.title}
        </p>
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
    body: "Your April certificate tests 60 days past due. Schedule 1, paragraph 1 says 30. Please reissue it. The 41 affected loans are attached.",
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
  const [selectedId, setSelectedId] = useState("X4");
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState("");
  const run = useValidationRun(state.dealerMatched, state.ran).data;
  const earlier = useValidationRun(false, state.ran).data;

  const items = data?.exceptions ?? [];
  const selected = items.find((item) => item.id === selectedId) ?? items[0];

  function work(outcome: ExceptionOutcome, note: string) {
    dispatch({ type: "work-exception", id: selected.id, outcome, note });
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
  const drill = run?.pool_bridge.lines.find((line) => line.rule_id === selected.drill);
  const matchDone = selected.recalculates && outcome === "accepted" && earlier && run;

  return (
    <div>
      <PageHeader
        title="Exception queue"
        summary={`${open.length} open of ${items.length}. Missing, conflicting and ambiguous items, each with its evidence.`}
        actions={
          <Button size="lg" onClick={() => navigate("/approve")}>
            Go to approval
            <ArrowRight aria-hidden className="size-4" />
          </Button>
        }
      />
      <SeedNotice>
        Seed data: this queue comes from the answer key. Loans and recalculations are real engine
        results.
      </SeedNotice>

      <div className="grid grid-cols-[26rem_minmax(0,1fr)] items-start gap-5">
        <Card className="sticky top-32 overflow-hidden">
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
        </Card>

        <Card className="overflow-hidden">
          <div className="p-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="numeric text-xs font-semibold text-muted">{selected.id}</span>
              <StatusPill
                status={selected.type === "missing" ? "missing" : "review"}
                label={TYPE_LABELS[selected.type]}
              />
              <span className="text-[0.8125rem] text-muted">{selected.label}</span>
              {selected.tier1 && <TierBadge tier={1} />}
            </div>
            <h2 className="mt-2 text-xl leading-snug font-semibold tracking-tight">
              {selected.title}
            </h2>
            <div className="mt-3 grid grid-cols-2 gap-4 text-sm">
              <div>
                <SectionLabel>Where</SectionLabel>
                <p className="mt-0.5">{selected.where}</p>
              </div>
              <div>
                <SectionLabel>Owner</SectionLabel>
                <p className="mt-0.5">{selected.owner}</p>
              </div>
            </div>
            <div className="mt-4">
              <SectionLabel>Evidence</SectionLabel>
              <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-snug">
                {selected.evidence.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
            <div className="mt-4 flex items-start gap-3 rounded-lg bg-canvas p-3">
              <Lightbulb aria-hidden className="mt-0.5 size-4 shrink-0 text-muted" />
              <div>
                <SectionLabel>Suggested action</SectionLabel>
                <p className="mt-0.5 text-sm font-medium">{selected.suggestion}</p>
              </div>
            </div>
            <div className="mt-4 flex items-center gap-2">
              {selected.actions.includes("accept") && (
                <Button disabled={Boolean(outcome)} onClick={() => act("accept")}>
                  <Check aria-hidden className="size-4" />
                  Accept
                </Button>
              )}
              {selected.actions.includes("query") && (
                <Button disabled={Boolean(outcome)} onClick={() => act("query")}>
                  <Send aria-hidden className="size-4" />
                  Draft query
                </Button>
              )}
              {selected.actions.includes("escalate") && (
                <Button disabled={Boolean(outcome)} onClick={() => act("escalate")}>
                  <ArrowUpRight aria-hidden className="size-4" />
                  Escalate to credit
                </Button>
              )}
              {outcome && <StatusPill status="approved" label={OUTCOMES[outcome]} />}
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
                Calderwood's US$500,000 alert.
              </p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-2"
                onClick={() => navigate("/validation")}
              >
                See the bridge
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
        description={`To: ${DRAFTS[selected.id]?.to ?? selected.owner}. Nothing is sent from this demo.`}
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
