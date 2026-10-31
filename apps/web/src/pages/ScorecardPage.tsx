import { useEffect, useState } from "react";
import { StatusPill } from "../components/ui/badges";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader, SeedNotice } from "../components/ui/PageHeader";
import { termStatus, useSession } from "../lib/session";
import { useWorkbench } from "../lib/workbench";

function elapsed(from: string, to: number): string {
  const minutes = Math.max(0, Math.round((to - new Date(from).getTime()) / 60_000));
  return `${minutes} min`;
}

interface Measure {
  name: string;
  formula: string;
  target: string;
  value: string | null;
}

export function ScorecardPage() {
  const { data } = useWorkbench();
  const { state } = useSession();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }

  const end = state.approvedAt ? new Date(state.approvedAt).getTime() : now;
  const approved = data.terms.filter((term) => termStatus(term, state) === "approved").length;
  const worked = Object.keys(state.exceptions).length;
  const processed = data.terms.length + data.rules.length;

  const measures: Measure[] = [
    {
      name: "Field-level accuracy, Tier 1",
      formula: "Correct values / fields extracted",
      target: "Every value correct after analyst review",
      value: null,
    },
    {
      name: "Field-level accuracy, Tier 2 and 3",
      formula: "Correct values / fields extracted",
      target: "Reported as measured",
      value: null,
    },
    {
      name: "Material errors and omissions",
      formula: "Tier 1 values wrong or missing before review",
      target: "Reported as measured, each listed",
      value: null,
    },
    {
      name: "Exceptions found",
      formula: "Planted exceptions found / 10",
      target: "10 of 10",
      value: null,
    },
    {
      name: "False items",
      formula: "Queue items that are not real problems",
      target: "3 or fewer",
      value: null,
    },
    {
      name: "Exception rate",
      formula: "Queue items / fields and rules processed",
      target: "Reported as measured",
      value: null,
    },
    {
      name: "Processing cost",
      formula: "Logged LLM and OCR usage for the pack",
      target: "Reported as measured",
      value: null,
    },
    {
      name: "Analyst effort",
      formula: "Items worked by an analyst in this session",
      target: "Reported as measured",
      value: `${approved} terms and ${worked} exceptions`,
    },
    {
      name: "Onboarding time",
      formula: "Pack upload to approved load file, this session",
      target: "Reported as measured",
      value: state.startedAt ? elapsed(state.startedAt, end) : "Not started",
    },
  ];

  return (
    <div>
      <PageHeader
        title="Scorecard"
        summary={`Oxane's success measures, each with its formula. ${processed} fields and rules in scope.`}
      />
      <SeedNotice>
        Seed data: no model has run yet, so accuracy cannot be claimed. These rows fill in from the
        real pipeline in phase 5.
      </SeedNotice>

      <Card className="overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
              <th className="py-2.5 pr-4 pl-5">Measure</th>
              <th className="py-2.5 pr-4">How it is calculated</th>
              <th className="py-2.5 pr-4">Demo target</th>
              <th className="py-2.5 pr-5">Result</th>
            </tr>
          </thead>
          <tbody>
            {measures.map((measure) => (
              <tr key={measure.name} className="border-b border-sand last:border-0">
                <td className="py-3 pr-4 pl-5 text-sm font-medium">{measure.name}</td>
                <td className="py-3 pr-4 text-[0.8125rem] text-muted">{measure.formula}</td>
                <td className="py-3 pr-4 text-[0.8125rem] text-muted">{measure.target}</td>
                <td className="numeric py-3 pr-5 text-sm font-semibold">
                  {measure.value ?? <StatusPill status="pending" label="Not measured yet" />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="mt-4">
        <SectionLabel>What this does not claim</SectionLabel>
        <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-muted">
          <li>No time saving is quoted. There is no Oxane baseline yet.</li>
          <li>These figures are for a synthetic pack, not Oxane's real deals.</li>
          <li>Double-pledging checks cover this pool only, not other lenders' data.</li>
        </ul>
      </div>
    </div>
  );
}
