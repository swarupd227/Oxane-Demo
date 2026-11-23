/* Expected-document schedules by facility, and the CLO daily feeds day by day. */
import clsx from "clsx";
import { useMemo, useState } from "react";
import { Tooltip } from "../../components/ui/Tooltip";
import type { Cycle, DailyFeed, ScheduleLine } from "../cycle";
import { deskRows } from "../desk";
import { Badge, DataTable, FilterSelect, Panel, when, type Column, type Tone } from "../ui";

export const SCHEDULE_STATUS: Record<ScheduleLine["status"], { label: string; tone: Tone }> = {
  complete: { label: "Complete", tone: "ok" },
  late: { label: "Received late", tone: "warn" },
  missing: { label: "Outstanding", tone: "danger" },
  not_due: { label: "Not due this cycle", tone: "neutral" },
  not_applicable: { label: "Not applicable", tone: "neutral" },
  summary_only: { label: "Summary only", tone: "neutral" },
};

interface Row extends ScheduleLine {
  key: string;
  facility: string;
  facilityName: string;
  template: string;
  client: string;
}

export function ScheduleTable({ cycle, client, facility }: { cycle: Cycle; client: string; facility?: string }) {
  const names = useMemo(() => Object.fromEntries(deskRows(cycle, undefined).map((f) => [f.id, { name: f.name, client: f.client }])), [cycle]);
  const [frequency, setFrequency] = useState("all");
  const [status, setStatus] = useState("all");
  const rows: Row[] = cycle.schedules
    .filter((s) => (facility ? s.facility === facility : client === "all" || names[s.facility]?.client === client))
    .flatMap((s) =>
      s.lines.map((line) => ({ ...line, key: `${s.facility}-${line.document}`, facility: s.facility, facilityName: names[s.facility]?.name ?? s.facility, template: s.template, client: names[s.facility]?.client ?? "" })),
    )
    .filter((r) => (frequency === "all" || r.frequency === frequency) && (status === "all" || r.status === status));
  const columns: Column<Row>[] = [
    ...(facility ? [] : [{ key: "facility", header: "Facility", sort: (r: Row) => r.facilityName, render: (r: Row) => <span className="whitespace-nowrap">{r.facilityName}</span> }]),
    { key: "template", header: "Template", sort: (r) => r.template, render: (r) => <span className="whitespace-nowrap text-muted">{r.template}</span> },
    { key: "document", header: "Document", sort: (r) => r.document, render: (r) => <span className="font-medium">{r.document}</span> },
    { key: "format", header: "Format", render: (r) => <span className="font-mono text-xs">{r.format}</span> },
    { key: "frequency", header: "Frequency", sort: (r) => r.frequency, render: (r) => r.frequency },
    { key: "channel", header: "Channel", sort: (r) => r.channel, render: (r) => r.channel },
    { key: "due", header: "Due", render: (r) => <span className="text-xs">{r.due}</span> },
    { key: "internal", header: "Internal deadline", render: (r) => <span className="text-xs text-muted">{r.internal === "same" ? "As due" : r.internal}</span> },
    {
      key: "cycle",
      header: "This cycle",
      align: "right",
      sort: (r) => r.expected,
      render: (r) => (r.expected ? <span className="numeric">{r.received}/{r.expected}</span> : <span className="text-muted">–</span>),
    },
    {
      key: "status",
      header: "Status",
      sort: (r) => ["missing", "late", "complete", "not_due", "summary_only", "not_applicable"].indexOf(r.status),
      render: (r) => (
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <Badge tone={SCHEDULE_STATUS[r.status].tone}>{SCHEDULE_STATUS[r.status].label}</Badge>
          {r.note && r.status !== "not_due" && (
            <Tooltip content={r.note}>
              <span tabIndex={0} className="cursor-help text-xs text-muted underline decoration-dotted">
                note
              </span>
            </Tooltip>
          )}
        </span>
      ),
    },
  ];
  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(r) => r.key}
      search={(r) => `${r.facilityName} ${r.document} ${r.template} ${r.channel}`}
      searchPlaceholder="Filter schedules"
      pageSize={facility ? 10 : 40}
      initialSort={{ key: "status", dir: "asc" }}
      rowClassName={(r) => (r.status === "missing" ? "bg-danger-tint/40" : undefined)}
      toolbar={
        <>
          <FilterSelect label="Frequency" value={frequency} onChange={setFrequency} options={[{ value: "all", label: "All frequencies" }, ...["Daily", "Monthly", "Quarterly", "Ad hoc"].map((f) => ({ value: f, label: f }))]} />
          <FilterSelect label="Schedule status" value={status} onChange={setStatus} options={[{ value: "all", label: "All statuses" }, ...Object.entries(SCHEDULE_STATUS).map(([value, v]) => ({ value, label: v.label }))]} />
        </>
      }
    />
  );
}

const CELL: Record<DailyFeed["days"][number]["status"], string> = {
  on_time: "bg-ok/70",
  late: "bg-warn",
  missing: "bg-danger",
};

export function DailyFeeds({ cycle }: { cycle: Cycle }) {
  const daily = cycle.daily_feeds;
  const name = cycle.facilities.find((f) => f.id === daily.facility)?.name ?? daily.facility;
  const days = daily.feeds[0]?.days.map((d) => d.as_of) ?? [];
  const exceptions = daily.feeds.flatMap((f) => f.days.filter((d) => d.status !== "on_time").map((d) => ({ ...d, feed: f })));
  return (
    <div className="space-y-3">
      <Panel title={`${name}: daily feeds, ${cycle.cycle.label}`} meta={`${daily.received} of ${daily.expected} deliveries · ${daily.business_days} business days`}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[0.6875rem] font-semibold text-muted">
                <th className="pr-3 pb-1 text-left">Feed</th>
                {days.map((d) => (
                  <th key={d} className="numeric px-0.5 pb-1 text-center font-medium">
                    {Number(d.slice(8))}
                  </th>
                ))}
                <th className="pb-1 pl-3 text-right">Received</th>
              </tr>
            </thead>
            <tbody>
              {daily.feeds.map((f) => (
                <tr key={f.feed}>
                  <td className="py-1 pr-3 whitespace-nowrap">
                    <span className="font-medium">{f.document}</span>
                    <span className="block text-[0.6875rem] text-muted">
                      {f.channel} · {f.due}
                    </span>
                  </td>
                  {f.days.map((d) => (
                    <td key={d.as_of} className="px-0.5 py-1 text-center">
                      <Tooltip content={`${when(d.as_of)}: ${d.status === "missing" ? "not received" : `received ${d.received_at?.replace("T", " ")}${d.minutes_late ? `, ${d.minutes_late} min late` : ""}`} · deadline ${d.deadline.replace("T", " ")}`}>
                        <span tabIndex={0} aria-label={`${f.document}, ${when(d.as_of)}: ${d.status.replace("_", " ")}`} className={clsx("mx-auto block size-4 cursor-help rounded-sm", CELL[d.status])} />
                      </Tooltip>
                    </td>
                  ))}
                  <td className="numeric py-1 pl-3 text-right">
                    {f.received}/{f.expected}
                  </td>
                </tr>
              ))}
              <tr className="border-t border-sand">
                <td className="py-1 pr-3 text-[0.6875rem] text-muted">Positions without a bid</td>
                {daily.coverage.map((c) => (
                  <td key={c.as_of} className={clsx("numeric px-0.5 py-1 text-center text-[0.6875rem]", c.unpriced ? "font-semibold text-danger" : "text-muted")}>
                    {c.unpriced || "0"}
                  </td>
                ))}
                <td />
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-2 flex items-center gap-3 text-[0.6875rem] text-muted">
          <span className="inline-flex items-center gap-1"><span className="size-2.5 rounded-sm bg-ok/70" /> On time</span>
          <span className="inline-flex items-center gap-1"><span className="size-2.5 rounded-sm bg-warn" /> Late</span>
          <span className="inline-flex items-center gap-1"><span className="size-2.5 rounded-sm bg-danger" /> Not received</span>
        </p>
      </Panel>
      <div className="grid grid-cols-2 gap-3">
        <Panel title="Exceptions" meta={`${exceptions.length}`}>
          <ul className="space-y-1.5 text-xs">
            {exceptions.map((e) => (
              <li key={`${e.feed.feed}-${e.as_of}`} className="flex items-start justify-between gap-2">
                <span>
                  <span className="font-medium">{e.feed.document}</span>, {when(e.as_of)}
                  <span className="block text-muted">{e.status === "missing" ? `Not received by ${e.deadline.replace("T", " ")}; no resend` : `Received ${e.received_at?.replace("T", " ")}, ${Math.floor(e.minutes_late / 60)} h ${e.minutes_late % 60} min after the deadline; ${e.rows} rows`}</span>
                </span>
                <Badge tone={e.status === "missing" ? "danger" : "warn"}>{e.status === "missing" ? "Query" : "Logged"}</Badge>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Rating changes from the daily feed" meta={`${daily.rating_changes.length}`}>
          <ul className="space-y-1 text-xs">
            {daily.rating_changes.map((r) => (
              <li key={`${r.loanx}-${r.agency}`} className="flex justify-between gap-2">
                <span>
                  {when(r.as_of)} · <span className="font-medium">{r.issuer}</span> <span className="font-mono text-muted">{r.loanx}</span>
                </span>
                <span className="font-mono">
                  {r.agency} {r.previous} → {r.current}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[0.6875rem] text-muted">Matches the 29 May collateral report's ratings, which the CCC test uses.</p>
        </Panel>
      </div>
    </div>
  );
}
