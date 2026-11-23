import { when, type Column } from "../monitoring/ui";
import { seconds, tokens, usd, type Registry, type Run } from "./api";
import { OutcomeBadge } from "./parts";

const stamp = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });

export function runColumns(
  registry: Registry,
  { names, clientName, showAgent }: { names: Map<string, string>; clientName: (id: string) => string; showAgent: boolean },
): Column<Run>[] {
  const columns: Column<Run>[] = [
    { key: "at", header: "Time", sort: (r) => r.at, render: (r) => <span className="numeric whitespace-nowrap text-muted" title={when(r.at)}>{stamp.format(new Date(r.at))}</span> },
    {
      key: "agent",
      header: "Agent",
      sort: (r) => names.get(r.agent ?? "") ?? "",
      render: (r) => <span className="block max-w-[9rem] truncate" title={names.get(r.agent ?? "") ?? r.task}>{names.get(r.agent ?? "") ?? r.task}</span>,
    },
    {
      key: "client",
      header: "Client / case",
      sort: (r) => `${clientName(r.client)} ${r.ref}`,
      render: (r) => (
        <span className="block whitespace-nowrap">
          <span className="block">{clientName(r.client).split(" ")[0]}</span>
          <span className="block font-mono text-[0.6875rem] text-muted">{r.ref || "–"}</span>
        </span>
      ),
    },
    {
      key: "subject",
      header: "Subject",
      render: (r) => (
        <span className="block min-w-0">
          <span className="block max-w-[19rem] truncate" title={r.subject}>
            {r.subject}
          </span>
          {r.note && (
            <span className="block max-w-[19rem] truncate text-[0.6875rem] text-muted" title={r.note}>
              {r.note}
            </span>
          )}
        </span>
      ),
    },
    { key: "outcome", header: "Outcome", sort: (r) => r.outcome, render: (r) => <OutcomeBadge outcome={r.outcome} labels={registry.outcomes} /> },
    { key: "tokens", header: "Tokens in / out", align: "right", sort: (r) => r.tokens_in + r.tokens_out, render: (r) => <span className="numeric whitespace-nowrap">{tokens(r.tokens_in)} / {tokens(r.tokens_out)}</span> },
    { key: "cost", header: "Cost", align: "right", sort: (r) => r.cost_usd, render: (r) => <span className="numeric">{usd(r.cost_usd)}</span> },
    { key: "duration", header: "Duration", align: "right", sort: (r) => r.duration_ms, render: (r) => <span className="numeric">{seconds(r.duration_ms)}</span> },
  ];
  return showAgent ? columns : columns.filter((c) => c.key !== "agent");
}
