import clsx from "clsx";
import {
  Cloud,
  FolderLock,
  Mail,
  Plug,
  Recycle,
  Server,
  Upload,
} from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Dialog } from "../../components/ui/Dialog";
import { Skeleton } from "../../components/ui/layout";
import { useCycle, type Submission } from "../cycle";
import { allSubmissions, deskRows, useScope } from "../desk";
import {
  Badge,
  DataTable,
  FilterSelect,
  Kpis,
  PageTitle,
  Panel,
  RecordId,
  useWide,
  when,
  type Column,
  type Tone,
} from "../ui";
import { DailyFeeds, ScheduleTable } from "./Schedules";

const VIEWS = [
  { id: "files", label: "Files" },
  { id: "schedules", label: "Schedules" },
  { id: "daily", label: "Daily feeds" },
] as const;

const statusView: Record<
  Submission["status"],
  { label: string; tone: Tone; rank: number }
> = {
  late: { label: "Overdue", tone: "danger", rank: 0 },
  awaited: { label: "Awaited", tone: "neutral", rank: 1 },
  received_late: { label: "Received late", tone: "warn", rank: 2 },
  reused: { label: "Prior period reused", tone: "info", rank: 3 },
  received: { label: "Received", tone: "ok", rank: 4 },
};

const channelIcon = {
  Email: Mail,
  SFTP: Server,
  API: Plug,
  "Data room": FolderLock,
  Upload: Upload,
};

const deadlineView = {
  met: { label: "Met", className: "text-ok" },
  at_risk: { label: "Due today", className: "text-warn font-semibold" },
  missed: { label: "Missed", className: "text-danger font-semibold" },
};

function ChaseDialog({
  submission,
  onClose,
}: {
  submission: Submission | null;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={!!submission}
      onOpenChange={(open) => !open && onClose()}
      title={submission ? `${submission.ref} · chase log` : "Chase log"}
      description={
        submission
          ? `${submission.label}, due ${when(submission.due)}`
          : undefined
      }
    >
      <ol className="space-y-2">
        {submission?.chase.map((step) => (
          <li
            key={step.at}
            className="rounded-md border border-line p-2.5 text-sm"
          >
            <p className="flex items-center justify-between gap-2 font-medium">
              <span className="flex items-center gap-1.5">
                <Mail aria-hidden className="size-3.5 text-muted" />
                {step.action}
              </span>
              <span className="numeric text-xs text-muted">
                {when(step.at)}
              </span>
            </p>
            <p className="mt-0.5 text-xs text-muted">To: {step.to}</p>
            <p className="mt-1 text-[0.8125rem]">{step.text}</p>
          </li>
        ))}
      </ol>
    </Dialog>
  );
}

export function SubmissionsPage() {
  const { data: cycle } = useCycle();
  const { client } = useScope();
  const [params, setParams] = useSearchParams();
  const [chase, setChase] = useState<Submission | null>(null);
  const [status, setStatus] = useState("all");
  const [channel, setChannel] = useState("all");
  const wide = useWide();
  const view = params.get("view") ?? "files";
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const names = Object.fromEntries(
    deskRows(cycle, undefined).map((f) => [f.id, f.name]),
  );
  const scoped = allSubmissions(cycle).filter(
    (s) => client === "all" || s.client === client,
  );
  const rows = scoped.filter(
    (s) =>
      (status === "all" || s.status === status) &&
      (channel === "all" || s.channel === channel),
  );
  const reused = scoped.filter((s) => s.reused);
  const columns: Column<Submission>[] = [
    {
      key: "ref",
      header: "Ref",
      sort: (s) => s.ref,
      render: (s) => <RecordId>{s.ref}</RecordId>,
    },
    {
      key: "facility",
      header: "Facility",
      sort: (s) => names[s.facility] ?? s.facility,
      render: (s) => (
        <span className="whitespace-nowrap">{names[s.facility]}</span>
      ),
    },
    {
      key: "doc",
      header: "Document",
      sort: (s) => s.label,
      render: (s) => (
        <span className="block max-w-64">
          {s.label}
          {s.file && (
            <span className="block truncate font-mono text-[0.6875rem] text-muted">
              {s.file}
            </span>
          )}
        </span>
      ),
    },
    {
      key: "channel",
      header: "Channel",
      sort: (s) => s.channel,
      render: (s) => {
        const Icon = channelIcon[s.channel] ?? Cloud;
        return (
          <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
            <Icon aria-hidden className="size-3.5 text-muted" />
            {s.channel}
          </span>
        );
      },
    },
    {
      key: "due",
      header: "Due",
      sort: (s) => s.due,
      render: (s) => (
        <span className="numeric whitespace-nowrap text-muted">
          {when(s.due)}
        </span>
      ),
    },
    {
      key: "deadline",
      header: "Internal",
      sort: (s) => s.internal_deadline,
      render: (s) => (
        <span className="numeric block whitespace-nowrap">
          {when(s.internal_deadline)}
          <span
            className={clsx(
              "block text-[0.6875rem]",
              deadlineView[s.deadline_status].className,
            )}
          >
            {deadlineView[s.deadline_status].label}
          </span>
        </span>
      ),
    },
    {
      key: "received",
      header: "Received",
      sort: (s) => s.received ?? "",
      render: (s) => (
        <span className="numeric whitespace-nowrap">
          {s.received ? when(s.received) : "–"}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      sort: (s) => statusView[s.status].rank,
      render: (s) => (
        <span className="inline-flex items-center gap-2 whitespace-nowrap">
          <Badge tone={statusView[s.status].tone}>
            {statusView[s.status].label}
          </Badge>
          {s.chase.length > 0 && (
            <button
              type="button"
              onClick={() => setChase(s)}
              className="cursor-pointer text-xs font-medium text-info hover:underline"
            >
              {s.chase.length} chases
            </button>
          )}
        </span>
      ),
    },
  ];
  return (
    <>
      <PageTitle
        title="Submissions"
        meta={`${cycle.cycle.label} · as of ${when(cycle.cycle.as_of)}`}
      />
      <div
        role="tablist"
        aria-label="Submissions view"
        className="mb-3 flex gap-1 border-b border-line"
      >
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            role="tab"
            aria-selected={view === v.id}
            onClick={() =>
              setParams(v.id === "files" ? {} : { view: v.id }, {
                replace: true,
              })
            }
            className={clsx(
              "-mb-px h-9 cursor-pointer border-b-2 px-3 text-[0.8125rem] font-medium",
              view === v.id
                ? "border-accent text-accent-strong"
                : "border-transparent text-muted hover:text-ink",
            )}
          >
            {v.label}
            {v.id === "daily" &&
              cycle.daily_feeds.feeds.some((f) => f.missing.length) && (
                <span className="numeric ml-1.5 rounded-full bg-danger px-1.5 text-[0.6875rem] text-white">
                  {cycle.daily_feeds.feeds.reduce(
                    (n, f) => n + f.missing.length + f.late.length,
                    0,
                  )}
                </span>
              )}
          </button>
        ))}
      </div>
      {view === "schedules" && <ScheduleTable cycle={cycle} client={client} />}
      {view === "daily" && <DailyFeeds cycle={cycle} />}
      {view === "files" && (
        <>
          <Kpis
            items={[
              { label: "Expected", value: scoped.length },
              {
                label: "Received",
                value: scoped.filter((s) => s.received).length,
              },
              {
                label: "Received late",
                value: scoped.filter((s) => s.status === "received_late")
                  .length,
                tone: "warn",
              },
              {
                label: "Overdue",
                value: scoped.filter((s) => s.status === "late").length,
                tone: scoped.some((s) => s.status === "late") ? "danger" : "ok",
              },
              { label: "Reused", value: reused.length },
              {
                label: "Deadline missed",
                value: scoped.filter((s) => s.deadline_status === "missed")
                  .length,
              },
            ]}
          />
          <div
            className={
              wide ? "grid grid-cols-[minmax(0,1fr)_20rem] gap-3" : "space-y-3"
            }
          >
            <DataTable
              rows={rows}
              columns={columns}
              rowKey={(s) => s.ref}
              search={(s) =>
                `${s.ref} ${names[s.facility]} ${s.label} ${s.file ?? ""} ${s.channel}`
              }
              searchPlaceholder="Filter submissions"
              initialQuery={params.get("q") ?? ""}
              initialSort={{ key: "status", dir: "asc" }}
              rowClassName={(s) =>
                s.status === "late" ? "bg-danger-tint/40" : undefined
              }
              toolbar={
                <>
                  <FilterSelect
                    label="Status"
                    value={status}
                    onChange={setStatus}
                    options={[
                      { value: "all", label: "All statuses" },
                      ...Object.entries(statusView).map(([value, v]) => ({
                        value,
                        label: v.label,
                      })),
                    ]}
                  />
                  <FilterSelect
                    label="Channel"
                    value={channel}
                    onChange={setChannel}
                    options={[
                      { value: "all", label: "All channels" },
                      ...Object.keys(channelIcon).map((c) => ({
                        value: c,
                        label: c,
                      })),
                    ]}
                  />
                </>
              }
            />
            <div
              className={
                wide ? "space-y-3 self-start" : "grid grid-cols-2 gap-3"
              }
            >
              {reused.map((s) => (
                <Panel
                  key={s.ref}
                  title={
                    <span className="inline-flex items-center gap-1.5">
                      <Recycle aria-hidden className="size-3.5 text-info" />
                      Prior-period reuse
                    </span>
                  }
                  meta={s.ref}
                >
                  <p className="text-[0.8125rem] font-medium">
                    {names[s.facility]}: {s.label}
                  </p>
                  <p className="mt-0.5 text-xs text-muted">{s.reused?.note}.</p>
                  <p className="mt-1.5 text-xs">
                    <span className="font-medium">Consent:</span>{" "}
                    {s.reused?.consent}
                  </p>
                </Panel>
              ))}
              <Panel title="By channel">
                <ul className="space-y-1 text-xs">
                  {Object.entries(
                    scoped.reduce<Record<string, number>>(
                      (acc, s) => ({
                        ...acc,
                        [s.channel]: (acc[s.channel] ?? 0) + 1,
                      }),
                      {},
                    ),
                  ).map(([name, count]) => {
                    const Icon =
                      channelIcon[name as Submission["channel"]] ?? Cloud;
                    return (
                      <li
                        key={name}
                        className="flex items-center justify-between"
                      >
                        <span className="flex items-center gap-1.5">
                          <Icon aria-hidden className="size-3.5 text-muted" />
                          {name}
                        </span>
                        <span className="numeric font-semibold">{count}</span>
                      </li>
                    );
                  })}
                </ul>
              </Panel>
            </div>
          </div>
        </>
      )}
      <ChaseDialog submission={chase} onClose={() => setChase(null)} />
    </>
  );
}
