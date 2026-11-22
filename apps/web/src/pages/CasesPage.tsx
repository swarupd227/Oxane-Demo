import clsx from "clsx";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar } from "../components/ui/Avatar";
import { Card, Skeleton } from "../components/ui/layout";
import { PageHeader } from "../components/ui/PageHeader";
import { casePath, ownerName, STAGE_TONES, useCases, type CaseSummary, type Stage } from "../lib/cases";
import { formatDate, formatUsdShort } from "../lib/format";

export function StagePill({ stage }: { stage: Stage }) {
  return (
    <span className={clsx("inline-flex h-5 items-center rounded px-1.5 text-[0.6875rem] font-medium whitespace-nowrap", STAGE_TONES[stage])}>
      {stage}
    </span>
  );
}

function Ratio({ done, total }: { done: number; total: number }) {
  if (!total) {
    return <span className="text-muted">-</span>;
  }
  return (
    <span className={clsx(done === total ? "text-muted" : "text-ink")}>
      {done}/{total}
    </span>
  );
}

function Num({ value, warn }: { value: number; warn?: boolean }) {
  return value ? <span className={clsx("font-medium", warn && "text-warn")}>{value}</span> : <span className="text-muted">0</span>;
}

const head = "py-2 pr-3 text-[0.6875rem] font-semibold tracking-[0.04em] text-muted uppercase whitespace-nowrap";

export function CasesPage() {
  const { data, isError, refetch } = useCases();
  const navigate = useNavigate();
  const [stage, setStage] = useState<Stage | "all">("all");
  const [text, setText] = useState("");

  const rows = useMemo(
    () =>
      (data?.cases ?? []).filter(
        (item) =>
          (stage === "all" || item.stage === stage) &&
          `${item.number} ${item.client} ${item.facility} ${item.deal_type}`.toLowerCase().includes(text.toLowerCase()),
      ),
    [data, stage, text],
  );

  if (isError) {
    return (
      <Card role="alert" className="p-4 text-sm">
        The case list could not be loaded.{" "}
        <button type="button" className="cursor-pointer font-medium underline" onClick={() => void refetch()}>
          Try again
        </button>
      </Card>
    );
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }
  const s = data.summary;

  return (
    <div>
      <PageHeader
        title="Onboarding cases"
        summary={`${s.cases} cases · ${s.clients} clients · ${s.open_exceptions} open exceptions · ${s.queries_with_client} queries with clients · as of ${formatDate(data.as_of)}`}
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div role="tablist" aria-label="Stage" className="flex items-center gap-1 rounded-md bg-sand p-0.5">
          {(["all", ...data.stages] as const).map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={stage === item}
              onClick={() => setStage(item)}
              className={clsx(
                "flex h-7 cursor-pointer items-center gap-1.5 rounded px-2.5 text-xs font-medium",
                stage === item ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink",
              )}
            >
              {item === "all" ? "All" : item}
              <span className="numeric text-[0.6875rem] text-muted">
                {item === "all" ? s.cases : s.by_stage[item]}
              </span>
            </button>
          ))}
        </div>
        <label className="ml-auto flex h-8 w-72 items-center gap-2 rounded-md border border-line bg-surface px-2.5 text-[0.8125rem]">
          <Search aria-hidden className="size-3.5 text-muted" />
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Filter by case, client or facility"
            aria-label="Filter cases"
            className="w-full bg-transparent outline-none focus-visible:shadow-none"
          />
        </label>
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full text-left text-[0.8125rem]">
          <thead>
            <tr className="border-b border-line">
              <th className={clsx(head, "pl-4")}>Case</th>
              <th className={head}>Facility</th>
              <th className={head}>Client</th>
              <th className={head}>Deal type</th>
              <th className={head}>Stage</th>
              <th className={head}>Owner</th>
              <th className={clsx(head, "hidden text-right 2xl:table-cell")}>In stage</th>
              <th className={clsx(head, "text-right")}>Docs</th>
              <th className={clsx(head, "text-right")}>Terms</th>
              <th className={clsx(head, "text-right")}>Exceptions</th>
              <th className={clsx(head, "text-right")}>Queries</th>
              <th className={clsx(head, "text-right")}>Pool balance</th>
              <th className={clsx(head, "hidden pr-4 2xl:table-cell")}>Activity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item: CaseSummary) => (
              <tr
                key={item.number}
                onClick={() => navigate(casePath(item))}
                className={clsx(
                  "cursor-pointer border-b border-sand last:border-0 hover:bg-canvas",
                  item.active && "bg-accent/10",
                )}
              >
                <td className="numeric py-2 pr-3 pl-4 font-mono text-xs font-semibold whitespace-nowrap">
                  <a
                    href={casePath(item)}
                    onClick={(event) => {
                      event.preventDefault();
                      navigate(casePath(item));
                    }}
                    className="hover:underline"
                  >
                    {item.number}
                  </a>
                </td>
                <td className="max-w-60 py-2 pr-3">
                  <span className="block truncate font-medium">{item.facility}</span>
                  {item.parent && <span className="block text-[0.6875rem] text-muted">Backbook · case {item.parent}</span>}
                </td>
                <td className="max-w-36 truncate py-2 pr-3 text-muted" title={item.client}>{item.client}</td>
                <td className="py-2 pr-3 whitespace-nowrap">{item.deal_type}</td>
                <td className="py-2 pr-3">
                  <StagePill stage={item.stage} />
                </td>
                <td className="py-2 pr-3">
                  <Avatar name={ownerName(data, item.owner)} />
                </td>
                <td className="numeric hidden py-2 pr-3 text-right 2xl:table-cell">
                  {item.business_days_in_stage ?? <span className="text-muted">-</span>}
                </td>
                <td className="numeric py-2 pr-3 text-right">
                  <Ratio done={item.documents.received} total={item.documents.expected} />
                </td>
                <td className="numeric py-2 pr-3 text-right">
                  <Ratio done={item.terms.approved} total={item.terms.total} />
                </td>
                <td className="numeric py-2 pr-3 text-right">
                  <Num value={item.exceptions.open} warn />
                </td>
                <td className="numeric py-2 pr-3 text-right">
                  <Num value={item.queries.with_client} />
                </td>
                <td className="numeric py-2 pr-3 text-right whitespace-nowrap">
                  {item.pool_balance === null ? <span className="text-muted">-</span> : formatUsdShort(item.pool_balance)}
                </td>
                <td className="numeric hidden py-2 pr-4 whitespace-nowrap text-muted 2xl:table-cell">
                  {item.last_activity ? formatDate(item.last_activity.slice(0, 10)) : "-"}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={13} className="py-8 text-center text-muted">
                  No cases match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
