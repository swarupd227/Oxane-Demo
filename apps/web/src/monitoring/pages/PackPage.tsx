import clsx from "clsx";
import { CheckCircle2, Circle, Code2, FileSpreadsheet, Lock, Send, ShieldCheck, Sparkles, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { Tooltip } from "../../components/ui/Tooltip";
import { Refusal, useActor, useCycle, useCycleAction, useCycleSession, workbookUrl, type FacilityId, type QcLine, type Source } from "../cycle";
import { deskRows, REPORT_LABEL, useScope, type DeskRow } from "../desk";
import { FacilityTabs, FacilityTag, Filled, SourcePanel } from "../parts";
import { Activity, Avatar, Badge, DataTable, PageTitle, Person, RecordId, when, type Column, type Tone } from "../ui";

const REPORT_TONE: Record<DeskRow["report"]["status"], Tone> = { released: "ok", in_review: "info", preparing: "neutral", provisional: "warn", held: "danger" };

function Queue({ onOpen }: { onOpen: (id: FacilityId) => void }) {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const { client } = useScope();
  if (!cycle) {
    return null;
  }
  const rows = deskRows(cycle, session).filter((r) => client === "all" || r.client === client);
  const columns: Column<DeskRow>[] = [
    { key: "name", header: "Facility", sort: (r) => r.name, render: (r) => <span className="font-medium">{r.name}</span> },
    { key: "client", header: "Client", sort: (r) => r.client_name, render: (r) => <span className="text-muted">{r.client_name}</span> },
    { key: "period", header: "Period", sort: (r) => r.period, render: (r) => r.period },
    { key: "analyst", header: "Preparer", sort: (r) => r.analyst, render: (r) => <Person name={r.analyst} /> },
    { key: "status", header: "Status", sort: (r) => r.report.status, render: (r) => <Badge tone={REPORT_TONE[r.report.status]}>{REPORT_LABEL[r.report.status]}</Badge> },
    { key: "levels", header: "Sign-off", sort: (r) => r.report.done / r.report.levels, render: (r) => <span className="numeric">{r.report.done}/{r.report.levels}</span> },
    { key: "last", header: "Last action", sort: (r) => r.report.at ?? "", render: (r) => (r.report.by ? <span className="whitespace-nowrap text-xs"><span className="numeric text-muted">{when(r.report.at)}</span> · {r.report.by}</span> : <span className="text-muted">–</span>) },
  ];
  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(r) => r.id}
      search={(r) => `${r.name} ${r.client_name} ${r.analyst}`}
      searchPlaceholder="Filter reports"
      initialSort={{ key: "status", dir: "desc" }}
      onRowClick={(r) => r.worked && onOpen(r.id as FacilityId)}
      rowClassName={(r) => (r.worked ? undefined : "cursor-default")}
    />
  );
}

function show(value: QcLine["platform"], unit: string): string {
  if (value === null || value === "") {
    return "blank";
  }
  if (typeof value === "string") {
    return value;
  }
  if (unit === "US$") {
    return value.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return String(value);
}

function QcCard({ facility }: { facility: FacilityId }) {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const action = useCycleAction();
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (!cycle) {
    return null;
  }
  const qc = cycle.qc[facility];
  const resolved = session?.qcResolved[facility] ?? {};
  return (
    <Card>
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <p className="text-[0.8125rem] font-semibold">Independent QC comparison <span className="font-normal text-muted">· {qc.file}</span></p>
        <span className="text-xs text-muted">
          {qc.agrees} agree · {qc.presentation} presentation · {qc.genuine.length} genuine
        </span>
      </div>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-xs font-medium text-subtle">
            <th className="py-2 pr-3 pl-5">Line</th>
            <th className="py-2 pr-3 text-right">Platform</th>
            <th className="py-2 pr-3 text-right">QC workbook</th>
            <th className="py-2 pr-5">Class</th>
          </tr>
        </thead>
        <tbody>
          {qc.lines.map((line) => (
            <tr key={line.line} className={clsx("border-t border-sand", line.class === "genuine" && "bg-danger-tint/40")}>
              <td className="py-1.5 pr-3 pl-5">{line.line}</td>
              <td className="numeric py-1.5 pr-3 text-right">{show(line.platform, line.unit)}</td>
              <td className="numeric py-1.5 pr-3 text-right">{show(line.qc, line.unit)}</td>
              <td
                className={clsx(
                  "py-1.5 pr-5 text-xs font-medium",
                  line.class === "genuine" ? "text-danger" : line.class === "agrees" ? "text-ok" : "text-muted",
                )}
              >
                {line.label}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {qc.genuine.length > 0 && (
        <div className="border-t border-line px-5 py-3 text-sm">
          {qc.genuine.map((line) =>
            resolved[line] ? (
              <p key={line} className="flex items-start gap-1.5 text-ok">
                <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0" />
                <span className="text-ink">
                  {line}: {resolved[line].note}
                </span>
              </p>
            ) : (
              <div key={line}>
                <p className="flex items-center gap-1.5 font-medium text-danger">
                  <TriangleAlert aria-hidden className="size-4" />
                  {line}: genuine variance, unresolved
                </p>
                <div className="mt-2 flex gap-2">
                  <input
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    aria-label="QC resolution"
                    placeholder="Resolution note"
                    className="h-9 flex-1 rounded-lg border border-line px-3 text-sm"
                  />
                  <Button
                    size="sm"
                    disabled={!note.trim() || action.isPending}
                    onClick={() => {
                      setError(null);
                      action.mutate(
                        { type: "resolve-qc", as: "analyst", payload: { facility, line, note } },
                        { onSuccess: () => setNote(""), onError: (e) => setError(e instanceof Refusal ? e.message : "Could not save.") },
                      );
                    }}
                  >
                    Record resolution
                  </Button>
                </div>
              </div>
            ),
          )}
          {error && <p className="mt-1 text-danger">{error}</p>}

        </div>
      )}
    </Card>
  );
}

export function PackPage() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const { actor } = useActor();
  const action = useCycleAction();
  const [tab, setTab] = useState<FacilityId | "queue">("bramble");
  const [source, setSource] = useState<Source | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const tabs = (
    <div role="tablist" aria-label="Report" className="mb-3 flex items-center gap-1 border-b border-line">
      <button
        type="button"
        role="tab"
        aria-selected={tab === "queue"}
        onClick={() => setTab("queue")}
        className={`-mb-px flex h-9 cursor-pointer items-center border-b-2 px-3 text-[0.8125rem] font-medium ${tab === "queue" ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink"}`}
      >
        All reports
      </button>
      <span aria-hidden className="mx-1 h-4 w-px bg-line" />
      <div className="min-w-0 flex-1">
        <FacilityTabs
          facilities={cycle.facilities}
          value={tab}
          onChange={(id) => {
            setTab(id as FacilityId);
            setSource(undefined);
            setError(null);
          }}
          extra={(id) => (session?.packs[id as FacilityId] ? <CheckCircle2 aria-label="Released" className="size-3.5 text-ok" /> : null)}
        />
      </div>
    </div>
  );
  if (tab === "queue") {
    return (
      <>
        <PageTitle title="Reports" meta={cycle.cycle.label} />
        {tabs}
        <Queue onOpen={setTab} />
      </>
    );
  }
  const me = cycle.team?.[actor];
  const pack = cycle.packs.find((p) => p.facility === tab)!;
  const facility = cycle.facilities.find((f) => f.id === tab)!;
  const released = session?.packs[tab];
  const approvals = session?.approvals[tab] ?? [];
  const levels = session?.levels[tab] ?? [];
  const pending = session?.pending[tab] ?? [];
  const clean = pack.unknown_placeholders.length === 0 && pack.numbers_in_text.length === 0;
  const blockers = [
    ...(pending.length ? [`${pending.length} open exception${pending.length === 1 ? "" : "s"}`] : []),
    ...(session?.held[tab] ? ["Load held by blocking check"] : []),
    ...(session?.qcOpen[tab]?.length ? ["QC variance unresolved"] : []),
  ];
  const approve = () => {
    setError(null);
    action.mutate({ type: "approve-pack", payload: { facility: tab as FacilityId } }, { onError: (e) => setError(e instanceof Refusal ? e.message : "The approval could not be saved.") });
  };
  const firstSourced = Object.values(pack.figures).find((f) => f.source)?.source ?? null;
  const sourced = Object.values(pack.figures).filter((f) => f.source).length;
  const preparer = cycle.clients.find((c) => c.id === facility.client)!.contact.name;
  const audit = (session?.audit ?? []).filter((a) => a.subject === tab || cycle.findings.some((f) => f.id === a.subject && f.facility.split(",").includes(tab)));
  return (
    <>
      <PageTitle title="Reports" meta={`${facility.name} · ${cycle.cycle.label}`} />
      {tabs}
      <div className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] gap-3">
        <div className="space-y-3">
          <Card className="p-4">
            <div className="flex items-start justify-between gap-4 border-b border-sand pb-2.5">
              <div>
                <SectionLabel>Monthly monitoring pack · {cycle.cycle.label}</SectionLabel>
                <h2 className="mt-0.5 text-base font-semibold">{facility.name}</h2>
                <p className="mt-0.5 flex items-center gap-2 text-xs text-muted">
                  <FacilityTag id={facility.id} name={facility.asset_class} />
                  {facility.role} · {facility.client_name}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {released ? (
                  <Badge tone="ok" icon={<Send aria-hidden className="size-3" />}>
                    Released
                  </Badge>
                ) : (
                  <Badge tone="warn" icon={<Lock aria-hidden className="size-3" />}>
                    Provisional
                  </Badge>
                )}
                {pack.pending_recording ? (
                  <Tooltip content="Written from the code template: the drafting step for this facility has not been recorded yet.">
                    <span tabIndex={0}>
                      <Badge tone="warn" icon={<Code2 aria-hidden className="size-3" />}>
                        Template · draft pending
                      </Badge>
                    </span>
                  </Tooltip>
                ) : pack.ai === false ? (
                  <Badge tone="neutral" icon={<Code2 aria-hidden className="size-3" />}>
                    Template
                  </Badge>
                ) : (
                  <Badge tone="info" icon={<Sparkles aria-hidden className="size-3" />}>
                    Drafted
                  </Badge>
                )}
              </div>
            </div>
            <p className="mt-3 text-[0.875rem] leading-relaxed font-medium">
              <Filled text={pack.summary} figures={pack.figures} onSource={setSource} />
            </p>
            {pack.sections.map((section) => (
              <section key={section.heading} className="mt-3">
                <h3 className="text-[0.8125rem] font-semibold">{section.heading}</h3>
                <p className="mt-0.5 text-[0.8125rem] leading-relaxed">
                  <Filled text={section.text} figures={pack.figures} onSource={setSource} />
                </p>
              </section>
            ))}
          </Card>
          <QcCard facility={tab} />
        </div>

        <div className="space-y-3 self-start">
          <Card className="p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="flex items-center gap-2 text-[0.8125rem] font-semibold">
                <FileSpreadsheet aria-hidden className="size-4 text-ok" />
                Lender workbook
                <span className="font-normal text-muted">· Inputs, Calculation, QC</span>
              </p>
              <a href={workbookUrl(tab)} className="inline-flex h-7 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 text-xs font-medium hover:border-stone" download>
                Download .xlsx
              </a>
            </div>
            <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
              <div>
                <dt className="text-muted">Figures</dt>
                <dd className="numeric font-semibold">{Object.keys(pack.figures).length}</dd>
              </div>
              <div>
                <dt className="text-muted">Linked to source</dt>
                <dd className="numeric font-semibold">{sourced}</dd>
              </div>
              <div>
                <dt className="text-muted">Number check</dt>
                <dd className={clsx("flex items-center gap-1 font-semibold", clean ? "text-ok" : "text-danger")}>
                  <ShieldCheck aria-hidden className="size-3.5" />
                  {clean ? "Passed" : [...pack.numbers_in_text, ...pack.unknown_placeholders].join(", ")}
                </dd>
              </div>
            </dl>
          </Card>
          <Card className="p-3">
            <div className="flex items-center justify-between">
              <SectionLabel>Sign-off · {facility.client_name}</SectionLabel>
              <RecordId>
                RPT-{cycle.cycle.id.replace("M-", "")}-{facility.id.slice(0, 3).toUpperCase()}
              </RecordId>
            </div>
            <ol className="mt-2 space-y-1 text-[0.8125rem]">
              <li className="flex items-center gap-2">
                {approvals.length || !pending.length ? <CheckCircle2 aria-hidden className="size-4 text-ok" /> : <Circle aria-hidden className="size-4 text-stone" />}
                <span className="w-14 text-xs text-muted">Level 1</span>
                <Person name={preparer} sub="Preparer" />
              </li>
              {levels.map((level) => {
                const done = approvals.find((a) => a.level === level.level);
                const signer = cycle.team?.[level.actor];
                return (
                  <li key={level.level} className="flex items-center gap-2">
                    {done ? <CheckCircle2 aria-hidden className="size-4 text-ok" /> : <Circle aria-hidden className="size-4 text-stone" />}
                    <span className="w-14 text-xs text-muted">Level {level.level}</span>
                    <Person name={signer?.name ?? level.title} sub={level.title} />
                    {done && <span className="numeric ml-auto text-xs text-muted">{when(done.at)}</span>}
                  </li>
                );
              })}
            </ol>
            {released ? (
              <p className="mt-2 flex items-center gap-2 text-xs font-medium text-ok">
                <Lock aria-hidden className="size-3.5" />
                Released {when(released.at)}
              </p>
            ) : (
              <>
                {blockers.length > 0 && (
                  <ul className="mt-2 space-y-0.5 text-xs text-warn">
                    {blockers.map((b) => (
                      <li key={b} className="flex items-center gap-1">
                        <TriangleAlert aria-hidden className="size-3" />
                        {b}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-2.5 flex items-center justify-between gap-3 border-t border-sand pt-2.5">
                  <span className="flex items-center gap-1.5 text-xs text-muted">
                    <Avatar name={me?.name ?? actor} />
                    {me?.name} · {me?.title}
                  </span>
                  <Button size="sm" onClick={approve} disabled={action.isPending}>
                    <Send aria-hidden className="size-3.5" />
                    Approve
                  </Button>
                </div>
                {error && (
                  <p role="alert" className="mt-1.5 text-xs text-danger">
                    {error}
                  </p>
                )}
              </>
            )}
          </Card>
          <SourcePanel source={source === undefined ? firstSourced : source} emptyText="Calculated figure; no source page." />
          <Card className="p-3">
            <div className="flex items-center justify-between">
              <SectionLabel>Activity</SectionLabel>
              <span className={clsx("text-[0.6875rem]", session?.chainIntact ? "text-ok" : "text-danger")}>
                {session?.chainIntact ? "Chain verified" : "Chain broken"} · <span className="font-mono">{session?.chainHead.slice(0, 10)}</span>
              </span>
            </div>
            <div className="mt-2 max-h-56 overflow-auto">
              <Activity entries={audit} />
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
