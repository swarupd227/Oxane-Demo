import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CheckCircle2, CircleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Skeleton } from "../../components/ui/layout";
import {
  OUTCOMES,
  useCycle,
  useCycleScorecard,
  type CycleScorecard,
} from "../cycle";
import {
  Badge,
  DataTable,
  FilterSelect,
  PageTitle,
  Panel,
  RecordId,
  type Column,
} from "../ui";

interface MetricRow {
  key: string;
  metric: string;
  value: string;
  period: string;
  basis: string[];
  kind: "Measured" | "Assumed";
  target: string;
  passed: boolean | null;
}

/** Which period each measure covers. Session measures move as the analyst works. */
function periodOf(
  name: string,
  kind: MetricRow["kind"],
  cycleLabel: string,
): string {
  if (kind === "Assumed") {
    return "Baseline";
  }
  return /Hours|Turnaround/.test(name) ? "This session" : `${cycleLabel} cycle`;
}

function rowsOf(data: CycleScorecard, cycleLabel: string): MetricRow[] {
  return data.measures.flatMap((m) => [
    {
      key: `${m.name}-m`,
      metric: m.name,
      value: m.measured.value,
      period: periodOf(m.name, "Measured", cycleLabel),
      basis: m.measured.details,
      kind: "Measured" as const,
      target: m.target,
      passed: m.passed,
    },
    ...(m.assumed
      ? [
          {
            key: `${m.name}-a`,
            metric: m.name,
            value: m.assumed.value,
            period: periodOf(m.name, "Assumed", cycleLabel),
            basis: m.assumed.details,
            kind: "Assumed" as const,
            target: "",
            passed: null,
          },
        ]
      : []),
  ]);
}

export function CycleScorecardPage() {
  const client = useQueryClient();
  const { data: cycle } = useCycle();
  const { data, isPending } = useCycleScorecard();
  const [kind, setKind] = useState("all");
  // Effort and turnaround change as the analyst works, so read them fresh on arrival.
  useEffect(() => {
    void client.invalidateQueries({ queryKey: ["cycle-scorecard"] });
  }, [client]);
  if (isPending || !data) {
    return <Skeleton className="h-96 w-full" />;
  }
  if (!data.available) {
    return (
      <p className="text-sm text-muted">
        Metrics unavailable: test set not loaded.
      </p>
    );
  }
  const label = cycle?.cycle.label ?? "";
  const rows = rowsOf(data, label).filter(
    (r) => kind === "all" || r.kind === kind,
  );
  const columns: Column<MetricRow>[] = [
    {
      key: "metric",
      header: "Metric",
      sort: (r) => r.metric,
      render: (r) => (
        <span className="block max-w-72 font-medium">{r.metric}</span>
      ),
    },
    {
      key: "value",
      header: "Value",
      render: (r) => (
        <span
          className={clsx(
            "numeric inline-flex items-center gap-1.5 font-semibold whitespace-nowrap",
            r.passed === false && "text-danger",
          )}
        >
          {r.passed === true && (
            <CheckCircle2
              aria-label="Target met"
              className="size-3.5 text-ok"
            />
          )}
          {r.passed === false && (
            <CircleAlert aria-label="Target missed" className="size-3.5" />
          )}
          {r.value}
        </span>
      ),
    },
    {
      key: "kind",
      header: "Type",
      sort: (r) => r.kind,
      render: (r) => (
        <Badge tone={r.kind === "Measured" ? "info" : "neutral"}>
          {r.kind}
        </Badge>
      ),
    },
    {
      key: "period",
      header: "Period",
      sort: (r) => r.period,
      render: (r) => (
        <span className="whitespace-nowrap text-muted">{r.period}</span>
      ),
    },
    {
      key: "target",
      header: "Target",
      render: (r) => (
        <span className="text-xs text-muted">{r.target || "–"}</span>
      ),
    },
    {
      key: "basis",
      header: "Basis / method",
      render: (r) => (
        <ul className="max-w-[34rem] space-y-0.5 text-xs text-muted">
          {r.basis.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      ),
    },
  ];
  const found = data.issues.filter((i) => i.found).length;
  const raised = data.noise.filter((n) => n.raised).length;
  return (
    <>
      <PageTitle
        title="Metrics"
        meta={`${label} cycle · measured and assumed`}
      />
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(r) => r.key}
        search={(r) => `${r.metric} ${r.basis.join(" ")}`}
        searchPlaceholder="Filter metrics"
        toolbar={
          <FilterSelect
            label="Type"
            value={kind}
            onChange={setKind}
            options={[
              { value: "all", label: "Measured and assumed" },
              { value: "Measured", label: "Measured" },
              { value: "Assumed", label: "Assumed" },
            ]}
          />
        }
      />
      <div className="mt-3 grid grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-3">
        <Panel
          title="Control test set: planted issues"
          meta={`${found}/${data.issues.length} detected with expected outcome`}
          flush
        >
          <table className="w-full text-left text-[0.8125rem]">
            <tbody>
              {data.issues.map((issue) => (
                <tr
                  key={issue.id}
                  className="border-b border-sand last:border-0"
                >
                  <td className="w-12 px-3 py-1">
                    <RecordId>{issue.id}</RecordId>
                  </td>
                  <td className="py-1 pr-3">{issue.summary}</td>
                  <td className="py-1 pr-3 whitespace-nowrap text-xs text-muted">
                    {OUTCOMES[issue.expected].short}
                  </td>
                  <td className="py-1 pr-3 text-right">
                    {issue.found ? (
                      <Badge tone="ok">Detected</Badge>
                    ) : (
                      <Badge tone="danger">Missed</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <div className="space-y-3 self-start">
          <Panel
            title="Control test set: noise"
            meta={`${raised}/${data.noise.length} raised as alerts`}
            flush
          >
            <table className="w-full text-left text-[0.8125rem]">
              <tbody>
                {data.noise.map((n) => (
                  <tr key={n.id} className="border-b border-sand last:border-0">
                    <td className="w-12 px-3 py-1">
                      <RecordId>{n.id}</RecordId>
                    </td>
                    <td className="py-1 pr-3">{n.summary}</td>
                    <td className="py-1 pr-3 text-right">
                      {n.raised ? (
                        <Badge tone="danger">Raised</Badge>
                      ) : (
                        <Badge tone="ok">Logged</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
          {!!data.pending_recording?.length && (
            <Panel
              title="Model steps not yet recorded"
              meta={`${data.pending_recording.length} steps · code fallback ran`}
              flush
            >
              <table className="w-full text-left text-xs">
                <tbody>
                  {data.pending_recording.map((p, i) => (
                    <tr
                      key={`${p.task}-${i}`}
                      className="border-b border-sand last:border-0"
                    >
                      <td className="px-3 py-1 font-mono text-[0.6875rem] text-muted">
                        {p.task}
                      </td>
                      <td className="py-1 pr-3">{p.subject}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!!data.not_scored?.length && (
                <p className="border-t border-sand px-3 py-1.5 text-[0.6875rem] text-muted">
                  Not scored until recorded: {data.not_scored.join("; ")}.
                </p>
              )}
            </Panel>
          )}
        </div>
      </div>
      <p className="mt-2 text-[0.6875rem] text-muted">
        {data.caveat} {data.assumptions}
      </p>
    </>
  );
}
