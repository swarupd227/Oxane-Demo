import clsx from "clsx";
import { CalendarRange } from "lucide-react";
import { useState } from "react";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { PageTitle } from "../ui";
import { formatDate } from "../../lib/format";
import { useCycle, type Source } from "../cycle";
import { SourcePanel } from "../parts";

const PERIODS = [
  { id: "may", label: "May 2026", end: "2026-05-31" },
  { id: "june", label: "June 2026", end: "2026-06-30" },
];
const START = Date.parse("2026-01-01");
const END = Date.parse("2026-07-31");
const AXIS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"];

function at(date: string): number {
  return ((Date.parse(date) - START) / (END - START)) * 100;
}

export function TermsTimelinePage() {
  const { data: cycle } = useCycle();
  const [period, setPeriod] = useState(PERIODS[0]);
  const [source, setSource] = useState<Source | null | undefined>(undefined);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const terms = cycle.terms.terms;
  const versionFor = (versions: (typeof terms)[number]["versions"]) =>
    [...versions].filter((v) => v.effective_from <= period.end).pop()!;
  const sunrise = cycle.tests.bramble.borrowing_base.sunrise;
  const dealer = terms.find((t) => t.name === "Dealer concentration limit");
  const dealerLimit = dealer ? parseFloat(versionFor(dealer.versions).value) : 5;
  const shown = source === undefined ? terms[0].versions.at(-1)?.source : source;
  return (
    <>
      <PageTitle title="Terms" meta="Bramble Auto Receivables I · effective-dated versions" />
      <div className="grid grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] gap-3">
        <div className="space-y-3">
          <Card className="p-3">
            <div className="flex items-center justify-between gap-4">
              <p className="flex items-center gap-2 text-[0.8125rem] font-semibold">
                <CalendarRange aria-hidden className="size-4 text-muted" />
                Reporting period
              </p>
              <div role="radiogroup" aria-label="Reporting period" className="flex gap-0.5 rounded-lg bg-sand p-0.5">
                {PERIODS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    role="radio"
                    aria-checked={p.id === period.id}
                    onClick={() => setPeriod(p)}
                    className={clsx("h-8 cursor-pointer rounded-md px-3 text-sm font-medium", p.id === period.id ? "bg-ink text-white" : "text-muted hover:text-ink")}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="relative mt-6">
              <div className="ml-48 flex border-b border-line pb-1">
                {AXIS.map((m) => (
                  <span key={m} className="flex-1 text-[0.6875rem] text-muted">
                    {m}
                  </span>
                ))}
              </div>
              <div className="pointer-events-none absolute top-0 bottom-0 left-48 right-0">
                <div className="absolute top-0 bottom-0 w-0.5 bg-accent transition-all duration-300" style={{ left: `${at(period.end)}%` }} aria-hidden />
              </div>
              <ul className="mt-2 space-y-3">
                {terms.map((term) => {
                  const current = versionFor(term.versions);
                  return (
                    <li key={term.name} className="flex items-center">
                      <div className="w-48 shrink-0 pr-3">
                        <p className="text-sm font-medium">{term.name}</p>
                        <p className="numeric text-xs text-muted">
                          {period.label}: <strong className="text-ink">{current.value}</strong>
                        </p>
                      </div>
                      <div className="relative h-9 flex-1">
                        {term.versions.map((version, index) => {
                          const next = term.versions[index + 1];
                          const left = Math.max(0, at(version.effective_from));
                          const right = next ? at(next.effective_from) : 100;
                          const active = version === current;
                          return (
                            <button
                              key={version.label}
                              type="button"
                              onClick={() => setSource(version.source)}
                              title={`${version.label}, from ${formatDate(version.effective_from)}`}
                              className={clsx(
                                "absolute top-0 flex h-9 cursor-pointer items-center overflow-hidden rounded-md border px-2 text-left text-xs font-medium transition-colors",
                                active ? "border-ink bg-ink text-white" : "border-line bg-surface text-muted hover:border-stone",
                              )}
                              style={{ left: `${left}%`, width: `calc(${right - left}% - 3px)` }}
                            >
                              <span className="numeric truncate">
                                {version.value} <span className={active ? "text-white/70" : "text-subtle"}>· {version.label}</span>
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          </Card>

          <Card className="p-3">
            <SectionLabel>Versions</SectionLabel>
            <table className="mt-3 w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs font-medium text-subtle">
                  <th className="py-2 pr-3">Term</th>
                  <th className="py-2 pr-3">May 2026</th>
                  <th className="py-2 pr-3">From 1 Jun 2026</th>
                  <th className="py-2">Clause</th>
                </tr>
              </thead>
              <tbody>
                {terms.map((term) => {
                  const last = term.versions.at(-1)!;
                  return (
                    <tr key={term.name} className="border-b border-sand last:border-0">
                      <td className="py-2 pr-3 font-medium">{term.name}</td>
                      <td className="numeric py-2 pr-3">{term.value_in_force}</td>
                      <td className={clsx("numeric py-2 pr-3", term.next_value !== term.value_in_force && "font-semibold")}>{term.next_value}</td>
                      <td className="py-2 text-xs">
                        <button type="button" onClick={() => setSource(last.source)} className="cursor-pointer text-info hover:underline">
                          {last.clause ?? last.label}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="numeric mt-2 rounded-md bg-canvas px-3 py-1.5 text-xs">
              Sunrise Motors {sunrise.share_pct.toFixed(2)}% of eligible pool · limit {dealerLimit}% ({period.label}) ·{" "}
              {sunrise.share_pct > dealerLimit ? <strong>excess US${Math.round(sunrise.excess).toLocaleString("en-US")} deducted</strong> : <strong>no excess</strong>}
            </p>
          </Card>
        </div>
        <div className="space-y-2">
          <SectionLabel>Clause</SectionLabel>
          <SourcePanel source={shown} tall emptyText="Select a version to see its clause." />
          {cycle.terms.periods_note && (
            <p className="rounded-lg bg-canvas px-3 py-2 text-xs text-muted">
              Amendment No. 2, earlier periods: <span className="text-ink">"{cycle.terms.periods_note}"</span>{" "}
              {cycle.terms.periods_source && (
                <button type="button" className="cursor-pointer font-medium text-info hover:underline" onClick={() => setSource(cycle.terms.periods_source)}>
                  Show
                </button>
              )}
            </p>
          )}
        </div>
      </div>
    </>
  );
}
