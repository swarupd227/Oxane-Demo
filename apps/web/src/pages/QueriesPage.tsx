import clsx from "clsx";
import { Clock3, Inbox, Send } from "lucide-react";
import { ProvenanceChip, StatusPill } from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader } from "../components/ui/PageHeader";
import { Avatar } from "../components/ui/Avatar";
import { Timeline, useHistory } from "../components/ui/Timeline";
import { useSearchParams } from "react-router-dom";
import { formatStamp, useCasework, type TrackedQuery } from "../lib/casework";
import { useSession } from "../lib/session";

const PILL: Record<TrackedQuery["status"], { status: "pending" | "open" | "review" | "approved"; label: string }> = {
  drafted: { status: "pending", label: "Drafted" },
  "with client": { status: "open", label: "With the client" },
  answered: { status: "review", label: "Answered" },
  closed: { status: "approved", label: "Closed" },
};

function hours(value: number): string {
  return `${value.toFixed(1)} h`;
}

function QueryCard({ query, focused }: { query: TrackedQuery; focused: boolean }) {
  const { dispatch, state } = useSession();
  const preparer = state.actor === "analyst";
  const history = useHistory([query.id]);
  return (
    <Card id={query.id} className={clsx("p-4", focused && "ring-2 ring-accent")}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="numeric flex items-center gap-1.5 text-xs font-semibold text-muted">
            <span className="font-mono text-ink">{query.id}</span> · {query.source} ·
            <Avatar name={query.to} />
            <span className="truncate font-normal">{query.to}</span>
            {query.blocking && <span className="text-danger">· blocking</span>}
          </p>
          <h3 className="mt-0.5 font-medium">{query.subject}</h3>
        </div>
        <StatusPill {...PILL[query.status]} />
      </div>
      <p className="mt-2 text-[0.8125rem] leading-relaxed">{query.text}</p>
      {query.figures && (
        <p className="mt-1.5">
          <ProvenanceChip
            kind="ai"
            detail={`${Object.keys(query.figures).length} figures by code`}
            tip={Object.values(query.figures).map((figure) => `${figure.value}: ${figure.means}`).join(" · ")}
          />
        </p>
      )}
      {query.answer && (
        <div className="mt-2 rounded-md bg-canvas px-3 py-2 text-[0.8125rem]">
          <p>
            <span className="font-medium">Answer, {formatStamp(query.answered)}:</span>{" "}
            {query.answer}
          </p>
          {query.resolution && (
            <p className="mt-1 text-muted">Configuration: {query.resolution}</p>
          )}
        </div>
      )}
      <div className="mt-3 flex items-center justify-between gap-4 text-xs text-muted">
        <span className="numeric flex flex-wrap gap-x-4 gap-y-1">
          <span>Raised {formatStamp(query.raised)}</span>
          {query.sent && <span>Sent {formatStamp(query.sent)}</span>}
          {query.closed && <span>Closed {formatStamp(query.closed)}</span>}
          <span>Analyst {hours(query.analyst_hours)}</span>
          <span>Waiting on client {hours(query.waiting_hours)}</span>
        </span>
        <span className="flex shrink-0 gap-2">
          {query.status === "drafted" && (
            <Button
              size="sm"
              disabled={!preparer}
              onClick={() => dispatch({ type: "send-query", ids: [query.id] })}
            >
              <Send aria-hidden className="size-3.5" />
              Send
            </Button>
          )}
          {query.answer_waiting && (
            <Button
              size="sm"
              variant="secondary"
              disabled={!preparer}
              onClick={() => dispatch({ type: "record-answer", ids: [query.id] })}
            >
              <Inbox aria-hidden className="size-3.5" />
              Record answer
            </Button>
          )}
        </span>
      </div>
      {history.length > 0 && (
        <details className="mt-2 border-t border-line pt-2">
          <summary className="cursor-pointer text-xs font-medium text-muted">History ({history.length})</summary>
          <Timeline className="mt-2" entries={history} />
        </details>
      )}
    </Card>
  );
}

export function QueriesPage() {
  const { state, dispatch } = useSession();
  const { data } = useCasework();
  const [params] = useSearchParams();
  const focus = params.get("id");

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }
  const t = data.tracker;
  const drafted = t.queries.filter((q) => q.status === "drafted");
  const waitingAnswers = t.queries.filter((q) => q.answer_waiting);
  const analystShare = t.elapsed_hours ? (t.analyst_hours / t.elapsed_hours) * 100 : 0;
  const perQueryAnalyst = t.queries.reduce((sum, q) => sum + q.analyst_hours, 0);
  const perQueryWaiting = t.queries.reduce((sum, q) => sum + q.waiting_hours, 0);
  const longest = t.queries
    .filter((q) => q.status === "with client")
    .sort((a, b) => b.waiting_hours - a.waiting_hours)[0];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Query tracker"
        summary={`Case 0412 · ${t.queries.length} queries · ${t.open_with_client} with client · ${t.drafted} drafted`}
        actions={
          state.actor === "analyst" && (drafted.length > 0 || waitingAnswers.length > 0) ? (
            <>
              {drafted.length > 0 && (
                <Button
                  onClick={() => dispatch({ type: "send-query", ids: drafted.map((q) => q.id) })}
                >
                  <Send aria-hidden className="size-4" />
                  Send {drafted.length} drafted
                </Button>
              )}
              {waitingAnswers.length > 0 && (
                <Button
                  variant="secondary"
                  onClick={() =>
                    dispatch({ type: "record-answer", ids: waitingAnswers.map((q) => q.id) })
                  }
                >
                  <Inbox aria-hidden className="size-4" />
                  Record {waitingAnswers.length} answers
                </Button>
              )}
            </>
          ) : undefined
        }
      />

      <Card className="p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <SectionLabel>Elapsed, pack received to now</SectionLabel>
            <p className="numeric mt-0.5 text-lg font-semibold">
              {hours(t.elapsed_hours)}{" "}
              <span className="text-sm font-normal text-muted">business hours</span>
            </p>
          </div>
          <p className="numeric flex items-center gap-1.5 text-xs text-muted">
            <Clock3 aria-hidden className="size-3.5" />
            {formatStamp(t.pack_received)} to {formatStamp(t.clock)} · business hours 09:00-17:30
          </p>
        </div>
        <div className="mt-3 flex h-7 overflow-hidden rounded-md text-xs font-medium" aria-hidden>
          <div className="flex items-center bg-accent px-2 text-white" style={{ width: `${analystShare}%` }}>
            {analystShare > 12 && "Analyst"}
          </div>
          <div className="flex flex-1 items-center bg-warn-tint px-2 text-warn">
            Waiting on client
          </div>
        </div>
        <dl className="numeric mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-[0.8125rem] lg:grid-cols-4">
          <div>
            <dt className="text-muted">Analyst time</dt>
            <dd className="font-semibold">{hours(t.analyst_hours)}</dd>
          </div>
          <div>
            <dt className="text-muted">Client waiting time</dt>
            <dd className="font-semibold">{hours(t.client_waiting_hours)}</dd>
          </div>
          <div>
            <dt className="text-muted">Analyst handling, sum of queries</dt>
            <dd className="font-semibold">{hours(perQueryAnalyst)}</dd>
          </div>
          <div>
            <dt className="text-muted">Client waiting, sum of queries</dt>
            <dd className="font-semibold">{hours(perQueryWaiting)}</dd>
          </div>
        </dl>
        <p className="mt-2 text-xs text-muted">
          {longest && `Longest open: ${longest.id} · ${longest.to} · sent ${formatStamp(longest.sent)}`}
        </p>
      </Card>

      <div className={clsx("grid grid-cols-2 gap-3")}>
        {t.queries.map((query) => (
          <QueryCard key={query.id} query={query} focused={query.id === focus} />
        ))}
      </div>
    </div>
  );
}
