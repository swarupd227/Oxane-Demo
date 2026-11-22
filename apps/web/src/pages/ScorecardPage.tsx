import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { CheckCircle2, CircleAlert } from "lucide-react";
import { Fragment } from "react";
import { Button } from "../components/ui/Button";
import { Card, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader, SeedNotice } from "../components/ui/PageHeader";
import { useCases } from "../lib/cases";
import { formatDate, formatUsdShort } from "../lib/format";
import { useSession } from "../lib/session";

interface Measure {
  name: string;
  formula: string;
  target: string;
  value: string;
  details: string[];
  passed: boolean | null;
}

interface BriefMeasure {
  name: string;
  measured: { value: string; details: string[] };
  assumed: { value: string | null; details: string[] } | null;
  passed: boolean | null;
}

interface Scorecard {
  available: boolean;
  measures: Measure[];
  caveat?: string;
  brief?: { measures: BriefMeasure[]; assumptions: string } | null;
}

const PERIOD = "Case 0412 · Apr 2026";
const head = "py-1.5 pr-3 text-[0.6875rem] font-semibold tracking-[0.04em] text-muted uppercase whitespace-nowrap";

function Status({ passed }: { passed: boolean | null }) {
  if (passed === true) {
    return <CheckCircle2 aria-label="Met" className="size-3.5 shrink-0 text-ok" />;
  }
  if (passed === false) {
    return <CircleAlert aria-label="Not met" className="size-3.5 shrink-0 text-danger" />;
  }
  return <span className="size-3.5 shrink-0" />;
}

function Basis({ lines }: { lines: string[] }) {
  if (lines.length === 0) {
    return <span className="text-subtle">-</span>;
  }
  return (
    <ul className="space-y-0.5">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

function Kind({ kind }: { kind: "Measured" | "Assumed" }) {
  return (
    <span
      className={clsx(
        "inline-flex h-5 items-center rounded px-1.5 text-[0.6875rem] font-medium",
        kind === "Measured" ? "bg-ok-tint text-ok" : "bg-sand text-muted",
      )}
    >
      {kind}
    </span>
  );
}

function Pipeline() {
  const { data } = useCases();
  if (!data) {
    return null;
  }
  const s = data.summary;
  const rows: [string, string, string][] = [
    ["Cases in pipeline", String(s.cases), `${s.clients} clients`],
    ...data.stages.map((stage): [string, string, string] => [`Cases at ${stage}`, String(s.by_stage[stage]), "Current stage"]),
    ["Open exceptions", String(s.open_exceptions), "Sum over cases"],
    ["Queries with clients", String(s.queries_with_client), "Sent, not answered"],
    ["QC variances open", String(s.qc_variances_open), "Genuine variances without a resolution"],
    ["Pool balance onboarding or live", formatUsdShort(s.pool_balance), "Sum of first-tape balances"],
  ];
  return (
    <Card className="overflow-hidden">
      <h2 className="border-b border-line px-4 py-2 text-sm font-semibold">
        Pipeline <span className="font-normal text-muted">· as of {formatDate(data.as_of)}</span>
      </h2>
      <table className="w-full text-left text-[0.8125rem]">
        <thead>
          <tr className="border-b border-line">
            <th className={clsx(head, "pl-4")}>Metric</th>
            <th className={clsx(head, "text-right")}>Value</th>
            <th className={clsx(head, "pr-4")}>Basis</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, value, basis]) => (
            <tr key={name} className="border-b border-sand last:border-0">
              <td className="py-1.5 pr-3 pl-4">{name}</td>
              <td className="numeric py-1.5 pr-3 text-right font-semibold">{value}</td>
              <td className="py-1.5 pr-4 text-muted">{basis}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export function ScorecardPage() {
  const { state } = useSession();
  const { data, isError, refetch } = useQuery({
    queryKey: ["scorecard", state.audit.length],
    queryFn: async (): Promise<Scorecard> => {
      const response = await fetch("/api/scorecard");
      if (!response.ok) {
        throw new Error(`Scorecard request failed with ${response.status}`);
      }
      return response.json();
    },
    enabled: state.intakeDone,
  });

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (isError) {
    return (
      <Card role="alert" className="p-4">
        <p className="text-sm font-medium">The scorecard could not be calculated.</p>
        <Button variant="secondary" size="sm" className="mt-3" onClick={() => void refetch()}>
          Try again
        </Button>
      </Card>
    );
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Metrics" summary={`${PERIOD} · period ending 30 Apr 2026`} />
      {!data.available && <SeedNotice>No extraction run for this case.</SeedNotice>}

      {data.available && data.brief && (
        <Card className="overflow-hidden">
          <h2 className="border-b border-line px-4 py-2 text-sm font-semibold">Onboarding measures</h2>
          <table className="w-full text-left text-[0.8125rem]">
            <thead>
              <tr className="border-b border-line">
                <th className={clsx(head, "w-[24%] pl-4")}>Metric</th>
                <th className={clsx(head, "w-[24%]")}>Value</th>
                <th className={head}>Type</th>
                <th className={head}>Period</th>
                <th className={clsx(head, "pr-4")}>Basis / method</th>
              </tr>
            </thead>
            <tbody>
              {data.brief.measures.map((measure) => (
                <Fragment key={measure.name}>
                  <tr className={clsx("align-top", !measure.assumed?.value && "border-b border-sand")}>
                    <td className="py-1.5 pr-3 pl-4 font-medium" rowSpan={measure.assumed?.value ? 2 : 1}>
                      {measure.name}
                    </td>
                    <td className="numeric py-1.5 pr-3 font-semibold">
                      <span className="flex items-start gap-1.5">
                        <Status passed={measure.passed} />
                        {measure.measured.value}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3">
                      <Kind kind="Measured" />
                    </td>
                    <td className="py-1.5 pr-3 whitespace-nowrap text-muted">{PERIOD}</td>
                    <td className="py-1.5 pr-4 text-muted">
                      <Basis lines={measure.measured.details} />
                    </td>
                  </tr>
                  {measure.assumed?.value && (
                    <tr className="border-b border-sand align-top">
                      <td className="numeric py-1.5 pr-3">
                        <span className="flex items-start gap-1.5">
                          <span className="size-3.5 shrink-0" />
                          {measure.assumed.value}
                        </span>
                      </td>
                      <td className="py-1.5 pr-3">
                        <Kind kind="Assumed" />
                      </td>
                      <td className="py-1.5 pr-3 whitespace-nowrap text-muted">Per onboarding</td>
                      <td className="py-1.5 pr-4 text-muted">
                        <Basis lines={measure.assumed.details} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          <p className="border-t border-line px-4 py-1.5 text-xs text-muted">Assumed basis: {data.brief.assumptions}</p>
        </Card>
      )}

      {data.available && (
        <Card className="overflow-hidden">
          <h2 className="border-b border-line px-4 py-2 text-sm font-semibold">Extraction and review</h2>
          <table className="w-full text-left text-[0.8125rem]">
            <thead>
              <tr className="border-b border-line">
                <th className={clsx(head, "w-[24%] pl-4")}>Metric</th>
                <th className={clsx(head, "w-[24%]")}>Value</th>
                <th className={head}>Target</th>
                <th className={clsx(head, "pr-4")}>Method</th>
              </tr>
            </thead>
            <tbody>
              {data.measures.map((measure) => (
                <tr key={measure.name} className="border-b border-sand align-top last:border-0">
                  <td className="py-1.5 pr-3 pl-4 font-medium">{measure.name}</td>
                  <td className="numeric py-1.5 pr-3 font-semibold">
                    <span className="flex items-start gap-1.5">
                      <Status passed={measure.passed} />
                      {measure.value}
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 text-muted">{measure.target}</td>
                  <td className="py-1.5 pr-4 text-muted">
                    <Basis lines={[measure.formula, ...measure.details]} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.caveat && <p className="border-t border-line px-4 py-1.5 text-xs text-muted">{data.caveat}</p>}
        </Card>
      )}

      <Pipeline />
    </div>
  );
}
