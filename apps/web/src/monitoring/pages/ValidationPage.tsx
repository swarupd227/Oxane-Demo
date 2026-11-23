import clsx from "clsx";
import { Ban, CheckCircle2, CircleSlash, FileSearch, Lock, Quote, TriangleAlert, Unlock } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { Badge, PageTitle, SuggestedChip } from "../ui";
import { Refusal, useCycle, useCycleAction, useCycleSession, type Feed, type FacilityId, type Source } from "../cycle";
import { FacilityTabs, SourcePanel } from "../parts";

const FAMILY_ORDER = ["missing_data", "duplicates", "reference_data", "data_types", "logical", "prior_period"];

const statusView = {
  passed: { label: "Passed", icon: CheckCircle2, className: "text-ok" },
  warning: { label: "Warning, logged", icon: TriangleAlert, className: "text-warn" },
  blocking: { label: "Blocked", icon: Ban, className: "text-danger" },
  "n/a": { label: "Field not in file", icon: CircleSlash, className: "text-muted" },
};

function Severity({ severity }: { severity: "blocking" | "warning" }) {
  return (
    <span
      className={clsx(
        "inline-flex h-5 items-center rounded px-1.5 text-[0.6875rem] font-semibold",
        severity === "blocking" ? "bg-danger-tint text-danger" : "bg-warn-tint text-warn",
      )}
    >
      {severity === "blocking" ? "Blocking" : "Warning"}
    </span>
  );
}

function ChangeTable({ feed }: { feed: Feed }) {
  if (!feed.prior_period.length) {
    return <p className="text-xs text-muted">No prior-period rules for this file.</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
          <th className="pb-1.5">Rule</th>
          <th className="pb-1.5 text-right">April</th>
          <th className="pb-1.5 text-right">May</th>
          <th className="pb-1.5 text-right">Change</th>
          <th className="pb-1.5 text-right">Limit</th>
        </tr>
      </thead>
      <tbody>
        {feed.prior_period.map((c) => {
          const money = c.metric === "pool_balance";
          const fmt = (v: number) => (money ? `US$${(v / 1e6).toFixed(2)}m` : v.toLocaleString("en-GB", { maximumFractionDigits: 2 }));
          return (
            <tr key={c.id} className={clsx("border-t border-sand", c.flagged && "bg-warn-tint/50")}>
              <td className="py-1.5 pr-2">
                <span className="font-medium">{c.label}</span>
                <span className="ml-1.5 text-xs text-muted">{c.id}</span>
              </td>
              <td className="numeric py-1.5 text-right">{fmt(c.prior)}</td>
              <td className="numeric py-1.5 text-right">{fmt(c.current)}</td>
              <td className={clsx("numeric py-1.5 text-right", c.flagged && "font-semibold text-warn")}>
                {c.change > 0 ? "+" : ""}
                {c.change.toFixed(2)}
                {c.basis === "pct" ? "%" : ""}
              </td>
              <td className="numeric py-1.5 pl-2 text-right text-muted">
                {c.limit}
                {c.basis === "pct" ? "%" : ""}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function ValidationPage() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const action = useCycleAction();
  const [tab, setTab] = useState<FacilityId>("northmoor");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<Source | null | undefined>(undefined);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const feeds = cycle.validation.feeds;
  const withFeeds = cycle.facilities.filter((f) => feeds.some((feed) => feed.facility === f.id));
  const feed = feeds.find((f) => f.facility === tab) ?? feeds[0];
  const blocked = feed.held && !session?.blocks[feed.facility];
  const released = session?.blocks[feed.facility];
  const failed = feed.rules.filter((r) => r.status === "warning" || r.status === "blocking");
  const explanation = feed.explanation;
  const familyRules = FAMILY_ORDER.filter((family) => family !== "prior_period").map((family) => ({
    family,
    name: feed.rules.find((r) => r.family === family)?.family_name ?? family,
    rules: feed.rules.filter((r) => r.family === family),
  }));
  const resolve = () => {
    setError(null);
    action.mutate(
      { type: "resolve-block", as: "analyst", payload: { facility: feed.facility, note } },
      {
        onSuccess: () => setNote(""),
        onError: (e) => setError(e instanceof Refusal ? e.message : "The resolution could not be saved."),
      },
    );
  };
  const cause = explanation ? explanation.cause.replace(/\{\{(\w+)\}\}/g, (_, key: string) => explanation.figures[key]?.replace("+", "") ?? key) : "";
  return (
    <>
      <PageTitle title="Validation" meta={`${cycle.cycle.label} · ${feeds.length} files · ${feeds.reduce((n, f) => n + f.rules.filter((r) => r.status !== "n/a").length, 0)} rule runs`} />
      <FacilityTabs
        facilities={withFeeds}
        value={tab}
        onChange={(id) => {
          setTab(id as FacilityId);
          setSource(undefined);
          setError(null);
        }}
        extra={(id) =>
          feeds.some((f) => f.facility === id && f.held) && !session?.blocks[id as FacilityId] ? <Lock aria-label="Load held" className="size-3.5 text-danger" /> : null
        }
      />
      {feed.held && (
        <div role="status" className={clsx("mb-3 rounded-lg px-3 py-2 text-[0.8125rem]", blocked ? "bg-danger-tint" : "bg-ok-tint")}>
          <p className={clsx("flex items-center gap-2 font-semibold", blocked ? "text-danger" : "text-ok")}>
            {blocked ? <Lock aria-hidden className="size-4" /> : <Unlock aria-hidden className="size-4" />}
            {blocked ? `Load held: blocking rule ${feed.resolution?.rule} failed` : `Load released by ${released?.by}`}
          </p>
          <p className="mt-1 text-ink">{feed.resolution?.proposed}</p>
          {released && <p className="mt-1 text-muted">Resolution: {released.note}</p>}
          {blocked && feed.resolution?.collapsible && (
            <div className="mt-3 flex items-center gap-2">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Resolution note"
                aria-label="Resolution note"
                className="h-9 flex-1 rounded-lg border border-line bg-surface px-3 text-sm"
              />
              <Button size="sm" disabled={!note.trim() || action.isPending} onClick={resolve}>
                Keep one row and release
              </Button>
            </div>
          )}
          {error && (
            <p role="alert" className="mt-2 text-danger">
              {error}
            </p>
          )}
          <p className="numeric mt-1.5 text-xs text-muted">
            {blocked
              ? `Rows in file ${feed.rows_in_file.toLocaleString("en-GB")} · to load ${feed.rows_loaded.toLocaleString("en-GB")} · reports provisional`
              : `${feed.rows_loaded.toLocaleString("en-GB")} of ${feed.rows_in_file.toLocaleString("en-GB")} rows loaded · ${released?.at ? released.at.slice(0, 16).replace("T", " ") : ""}`}
          </p>
        </div>
      )}
      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-3">
        <Card>
          <div className="flex items-center justify-between border-b border-line px-3 py-2">
            <p className="text-[0.8125rem] font-semibold">{feed.file}</p>
            <span className="text-xs text-muted">
              {feed.rules.filter((r) => r.status !== "n/a").length} run · {failed.length} not met · sha256 {feed.sha256.slice(0, 10)}
            </span>
          </div>
          <table className="w-full text-left text-sm">
            <tbody>
              {familyRules.map(({ family, name, rules }) => (
                <FamilyRows key={family} name={name} rules={rules} />
              ))}
            </tbody>
          </table>
        </Card>
        <div className="space-y-3 self-start">
          {feed.facility === "larkspur" && (
            <Card className="p-3">
              <SectionLabel>Daily feeds, {cycle.cycle.label}</SectionLabel>
              <ul className="mt-2 space-y-1 text-xs">
                {cycle.daily_feeds.feeds.map((f) => (
                  <li key={f.feed} className="flex items-center justify-between gap-2">
                    <span>{f.document}</span>
                    <span className="numeric">
                      {f.received}/{f.expected}
                      {f.missing.length > 0 && <span className="ml-1.5 font-semibold text-danger">{f.missing.length} missing</span>}
                      {f.late.length > 0 && <span className="ml-1.5 font-semibold text-warn">{f.late.length} late</span>}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">
                Price coverage checked daily against the positions held: {cycle.daily_feeds.coverage.filter((c) => c.unpriced).length} day without bids.{" "}
                <Link to="/monitoring/submissions?view=daily" className="font-medium text-info hover:underline">
                  Open daily feeds
                </Link>
              </p>
            </Card>
          )}
          {feed.facility === "ravenglass" && (
            <Card className="p-3">
              <SectionLabel>Obligor documents</SectionLabel>
              <p className="mt-2 text-xs">
                {cycle.tests.ravenglass.received} of {cycle.tests.ravenglass.obligors.length} obligors sent Q1 financials and a compliance certificate, each matched to a stored layout.
              </p>
              <p className="mt-1 text-xs text-muted">
                {cycle.tests.ravenglass.extraction.status === "recorded"
                  ? `${cycle.tests.ravenglass.extraction.verified} obligors read with every quote found on its page.`
                  : "Obligor reading not yet recorded: tests use this portfolio report's figures, checked by the rules here."}
              </p>
            </Card>
          )}
          <Card className="p-3">
            <SectionLabel>Change on prior period</SectionLabel>
            <div className="mt-2">
              <ChangeTable feed={feed} />
            </div>
          </Card>
          {explanation && (
            <Card className="p-3">
              <p className="flex items-center gap-2 text-[0.8125rem] font-semibold">
                <FileSearch aria-hidden className="size-4 text-muted" />
                Cause of change
              </p>
              <div className="mt-2 rounded-md bg-canvas p-2.5">
                <p className="flex items-center gap-1.5 text-xs">
                  <SuggestedChip by="AI" detail={explanation.document} />
                  {explanation.verified ? <Badge tone="ok">Quote verified</Badge> : <Badge tone="danger">Quote not found</Badge>}
                </p>
                <p className="mt-1 text-[0.8125rem]">{cause}</p>
                <button type="button" onClick={() => setSource(explanation.source)} className="mt-2 flex cursor-pointer items-start gap-1.5 text-left text-sm text-info hover:underline">
                  <Quote aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                  <span>"{explanation.quote}"</span>
                </button>
              </div>
            </Card>
          )}
          {(source !== undefined || explanation?.source) && <SourcePanel source={source === undefined ? explanation?.source : source} />}
        </div>
      </div>
    </>
  );
}

function FamilyRows({ name, rules }: { name: string; rules: Feed["rules"] }) {
  if (!rules.length) {
    return null;
  }
  return (
    <>
      <tr className="bg-canvas">
        <td colSpan={4} className="px-5 py-1.5 text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
          {name}
        </td>
      </tr>
      {rules.map((rule) => {
        const view = statusView[rule.status];
        const Icon = view.icon;
        return (
          <tr key={rule.id} className="border-t border-sand align-top">
            <td className="w-12 py-2 pl-5 font-mono text-xs text-muted">{rule.id}</td>
            <td className="py-2 pr-3">
              {rule.text}
              {rule.examples.length > 0 && (
                <p className="mt-0.5 text-xs text-muted">
                  {rule.examples
                    .slice(0, 3)
                    .map((e) => `${e.key}${e.value && e.value !== e.key ? ` (${e.value || "blank"})` : ""}, row ${e.row}`)
                    .join("; ")}
                  {rule.failed > 3 ? `; and ${rule.failed - 3} more` : ""}
                </p>
              )}
            </td>
            <td className="w-20 py-2 pr-3">
              <Severity severity={rule.severity} />
            </td>
            <td className={clsx("w-44 py-2 pr-5 text-xs font-medium whitespace-nowrap", view.className)}>
              <span className="inline-flex items-center gap-1">
                <Icon aria-hidden className="size-3.5" />
                {view.label}
                {rule.failed > 0 && <span className="numeric">({rule.failed})</span>}
              </span>
            </td>
          </tr>
        );
      })}
    </>
  );
}
