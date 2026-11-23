import clsx from "clsx";
import {
  CheckCircle2,
  Columns3,
  Database,
  Fingerprint,
  Lock,
  Replace,
} from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import {
  useCycle,
  useCycleAction,
  useCycleSession,
  type FacilityId,
} from "../cycle";
import { FacilityTag, NoAiBadge } from "../parts";
import { useScope } from "../desk";
import { PageTitle, SuggestedChip } from "../ui";
import { MappingLibrary } from "./MappingLibrary";
import { ReuseView } from "./ReuseView";

const ENTITY_ORDER = [
  "portfolio",
  "facility",
  "loan",
  "test",
  "stratification",
];

export function MappingPage() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const action = useCycleAction();
  const [selected, setSelected] = useState<FacilityId>("bramble");
  const [params, setParams] = useSearchParams();
  const { client } = useScope();
  const view = params.get("view") === "library" ? "library" : params.get("view") === "reuse" ? "reuse" : "files";
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const feeds = cycle.mapping.feeds;
  const feed = feeds.find((f) => f.facility === selected) ?? feeds[0];
  const facility = cycle.facilities.find((f) => f.id === feed.facility)!;
  const layout = cycle.layout;
  return (
    <>
      <PageTitle
        title="Mapping"
        meta={`${cycle.cycle.label} · ${feeds.length} files · ${cycle.mapping.library.length} stored layouts`}
      />
      <div
        role="tablist"
        aria-label="Mapping view"
        className="mb-3 flex gap-1 border-b border-line"
      >
        {(["files", "library", "reuse"] as const).map((v) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={view === v}
            onClick={() =>
              setParams(v === "files" ? {} : { view: v }, { replace: true })
            }
            className={clsx(
              "-mb-px h-9 cursor-pointer border-b-2 px-3 text-[0.8125rem] font-medium",
              view === v
                ? "border-accent text-accent-strong"
                : "border-transparent text-muted hover:text-ink",
            )}
          >
            {v === "files" ? "This cycle's files" : v === "library" ? "Layout library" : "Reuse by bank and sender"}
          </button>
        ))}
      </div>
      {view === "library" && <MappingLibrary cycle={cycle} client={client} />}
      {view === "reuse" && <ReuseView client={client} />}
      {view === "files" && (
        <div className="grid grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-3">
          <div className="space-y-3">
            <Card>
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-line text-xs font-medium text-subtle">
                    <th className="py-2.5 pr-3 pl-5">File</th>
                    <th className="py-2.5 pr-3">Client memory</th>
                    <th className="py-2.5 pr-3">Layout</th>
                    <th className="py-2.5 pr-3 text-right">From memory</th>
                    <th className="py-2.5 pr-5">Suggestions</th>
                  </tr>
                </thead>
                <tbody>
                  {feeds.map((f) => {
                    const fac = cycle.facilities.find(
                      (x) => x.id === f.facility,
                    )!;
                    return (
                      <tr
                        key={f.file}
                        onClick={() => setSelected(f.facility)}
                        aria-selected={f.facility === feed.facility}
                        className={clsx(
                          "cursor-pointer border-b border-sand last:border-0 hover:bg-canvas",
                          f.facility === feed.facility && "bg-canvas",
                        )}
                      >
                        <td className="py-2.5 pr-3 pl-5">
                          <span className="flex items-center gap-1.5">
                            <FacilityTag
                              id={f.facility}
                              name={fac.name.split(" ")[0]}
                            />
                            <span className="truncate text-sm">{f.file}</span>
                          </span>
                        </td>
                        <td className="py-2.5 pr-3 text-sm">
                          {fac.client_name
                            .replace(" plc", "")
                            .replace(" N.A.", "")}
                        </td>
                        <td className="py-2.5 pr-3 text-sm">
                          {f.layout === "unchanged" ? (
                            <span className="inline-flex items-center gap-1 text-ok">
                              <CheckCircle2 aria-hidden className="size-3.5" />{" "}
                              Unchanged
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-warn">
                              <Columns3 aria-hidden className="size-3.5" />{" "}
                              {f.columns_total - f.from_memory} new columns
                            </span>
                          )}
                        </td>
                        <td className="numeric py-2.5 pr-3 text-right text-sm">
                          {f.from_memory} of {f.columns_total}
                        </td>
                        <td className="py-2.5 pr-5 text-sm">
                          {fac.ai_permitted ? (
                            f.ai_used ? (
                              `${f.columns_total - f.from_memory} columns`
                            ) : (
                              "–"
                            )
                          ) : (
                            <NoAiBadge compact />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>

            <Card className="p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <SectionLabel>{feed.file}</SectionLabel>
                  <p className="mt-0.5 text-[0.8125rem] font-semibold">
                    Standard model
                  </p>
                </div>
                <span className="flex items-center gap-1.5 rounded-md bg-sand px-2.5 py-1 text-xs text-muted">
                  <Fingerprint aria-hidden className="size-3.5" />
                  Raw file · {feed.rows.toLocaleString("en-GB")} rows · sha256{" "}
                  {feed.sha256.slice(0, 10)}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-5 gap-2">
                {ENTITY_ORDER.map((entity) => (
                  <div
                    key={entity}
                    className="rounded-lg border border-line px-3 py-2"
                  >
                    <p className="text-xs font-semibold capitalize">{entity}</p>
                    <p className="numeric text-base font-semibold">
                      {feed.entities[entity] ?? 0}
                    </p>
                  </div>
                ))}
              </div>
              <div className="mt-3 max-h-80 overflow-auto rounded-lg border border-line">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-canvas">
                    <tr className="text-xs font-medium text-subtle">
                      <th className="py-2 pr-3 pl-3">Source column</th>
                      <th className="py-2 pr-3">Master field</th>
                      <th className="py-2 pr-3">Standard model</th>
                    </tr>
                  </thead>
                  <tbody>
                    {feed.fields.map((f) => (
                      <tr
                        key={f.column}
                        className={clsx(
                          "border-t border-sand",
                          f.new && "bg-warn-tint/40",
                        )}
                      >
                        <td className="py-1.5 pr-3 pl-3 font-mono text-xs">
                          {f.column}
                        </td>
                        <td className="py-1.5 pr-3 font-mono text-xs">
                          {f.master_field}
                          {f.new && (
                            <span className="ml-2 font-sans text-[0.6875rem] font-semibold text-warn">
                              New
                            </span>
                          )}
                        </td>
                        <td className="py-1.5 pr-3 text-xs capitalize">
                          {f.entity}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {feed.overrides.length > 0 && (
                <div className="mt-4 rounded-lg border-2 border-info/40 p-3">
                  <p className="flex items-center gap-1.5 text-sm font-semibold">
                    <Replace aria-hidden className="size-4 text-info" />
                    Client-specific master field
                  </p>
                  {feed.overrides.map((o) => (
                    <p key={o.field} className="mt-1 text-sm">
                      <code className="font-mono text-xs">{o.field}</code>:
                      platform default{" "}
                      <strong>{o.default.replace("_", " ")}</strong>,{" "}
                      {facility.client_name} uses{" "}
                      <strong>{o.override.replace("_", " ")}</strong>.{" "}
                      {o.reason}.
                    </p>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <div className="space-y-3 self-start">
            <Card className="p-3">
              <p className="flex items-center gap-2 text-[0.8125rem] font-semibold">
                <Columns3 aria-hidden className="size-4 text-muted" />
                Layout change · {layout.file}
              </p>
              <p className="numeric mt-0.5 text-xs text-muted">
                From stored mapping {layout.from_memory}/{layout.columns_total}{" "}
                · new {layout.new_columns.length}
              </p>
              <ul className="mt-2 space-y-2">
                {layout.new_columns.map((column) => (
                  <li
                    key={column.column}
                    className="rounded-md border border-line p-2.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <code className="font-mono text-sm font-semibold">
                        {column.column}
                      </code>
                      <span className="inline-flex h-5 items-center rounded bg-sand px-1.5 text-[0.6875rem] font-medium text-muted">
                        Logged
                      </span>
                    </div>
                    <p className="mt-1.5 flex items-start gap-1.5 text-xs">
                      <SuggestedChip by="AI" />
                      <span>
                        {column.field ? `Maps to ${column.field}. ` : ""}
                        {column.reason}
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      Values: {column.values.join(", ")} · {column.outcome}
                    </p>
                  </li>
                ))}
              </ul>
              <div className="mt-2 flex items-center justify-between gap-3">
                <SectionLabel>
                  {session?.layoutConfirmed
                    ? "Confirmed"
                    : "Awaiting confirmation"}
                </SectionLabel>
                {session?.layoutConfirmed ? (
                  <span className="inline-flex items-center gap-1.5 text-sm font-medium text-ok">
                    <CheckCircle2 aria-hidden className="size-4" />
                    Confirmed
                  </span>
                ) : (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={action.isPending}
                    onClick={() => action.mutate({ type: "confirm-layout" })}
                  >
                    Confirm mapping
                  </Button>
                )}
              </div>
            </Card>
            <Card className="p-3">
              <p className="flex items-center gap-2 text-[0.8125rem] font-semibold">
                <Lock aria-hidden className="size-4 text-muted" />
                Mapping memory
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3">
                {cycle.mapping.memories.map((memory) => {
                  const client = cycle.clients.find(
                    (c) => c.id === memory.client,
                  )!;
                  return (
                    <div
                      key={memory.client}
                      className="rounded-lg border border-line p-3"
                    >
                      <p className="flex items-center gap-1.5 text-sm font-semibold">
                        <Database aria-hidden className="size-3.5 text-muted" />
                        {memory.name}
                      </p>
                      {!client.ai_permitted && (
                        <p className="mt-1">
                          <NoAiBadge compact />
                        </p>
                      )}
                      <ul className="mt-2 space-y-1 text-xs">
                        {memory.layouts.map((l) => (
                          <li
                            key={l.facility}
                            className="flex items-center justify-between gap-2"
                          >
                            <span className="truncate">
                              {
                                cycle.facilities
                                  .find((f) => f.id === l.facility)
                                  ?.name.split(" ")[0]
                              }
                              : {l.kind}
                            </span>
                            <span className="numeric shrink-0 text-muted">
                              {l.columns ? `${l.columns} columns` : "–"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
