import clsx from "clsx";
import { CheckCircle2, CircleAlert, FlaskConical } from "lucide-react";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { PageHeader } from "../../components/ui/PageHeader";
import { OUTCOMES, useCycleScorecard } from "../cycle";

export function CycleScorecardPage() {
  const client = useQueryClient();
  const { data, isPending } = useCycleScorecard();
  // Effort and turnaround change as the analyst works, so read them fresh on arrival.
  useEffect(() => {
    void client.invalidateQueries({ queryKey: ["cycle-scorecard"] });
  }, [client]);
  if (isPending || !data) {
    return <Skeleton className="h-96 w-full" />;
  }
  if (!data.available) {
    return <p className="text-muted">The cycle answer key is not available.</p>;
  }
  return (
    <>
      <PageHeader title="Scorecard" summary="The RFP's measures for use case 2, calculated from this cycle and this session against the answer key. Measured, not forecast." />
      <div className="grid grid-cols-3 gap-4">
        {data.measures.map((measure) => (
          <Card key={measure.name} className="p-5">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-semibold">{measure.name}</p>
              {measure.passed === true && <CheckCircle2 aria-label="Target met" className="size-5 text-ok" />}
              {measure.passed === false && <CircleAlert aria-label="Target missed" className="size-5 text-danger" />}
            </div>
            <p className={clsx("numeric mt-2 text-3xl font-semibold tracking-tight", measure.passed === false && "text-danger")}>{measure.value}</p>
            <p className="mt-2 text-xs text-muted">{measure.formula}</p>
            <p className="text-xs text-muted">Target: {measure.target}</p>
            {measure.details.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-xs">
                {measure.details.map((detail) => (
                  <li key={detail}>{detail}</li>
                ))}
              </ul>
            )}
          </Card>
        ))}
      </div>
      <Card className="mt-5">
        <div className="border-b border-line px-5 py-3">
          <SectionLabel>Planted issues and the outcome each should reach</SectionLabel>
        </div>
        <table className="w-full text-left text-sm">
          <tbody>
            {data.issues.map((issue) => (
              <tr key={issue.id} className="border-b border-sand last:border-0">
                <td className="numeric w-14 py-2 pl-5 font-semibold">{issue.id}</td>
                <td className="py-2 pr-3">{issue.summary}</td>
                <td className="py-2 pr-3 text-muted">{OUTCOMES[issue.expected].label}</td>
                <td className="py-2 pr-5 text-right">
                  {issue.found ? (
                    <span className="inline-flex items-center gap-1 font-medium text-ok">
                      <CheckCircle2 aria-hidden className="size-4" /> Found
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 font-medium text-danger">
                      <CircleAlert aria-hidden className="size-4" /> Missed
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <p className="mt-4 flex items-center gap-2 rounded-lg bg-sand px-3 py-2 text-[0.8125rem] text-muted">
        <FlaskConical aria-hidden className="size-4 shrink-0" />
        {data.caveat} We do not quote a percentage saving: Oxane has not shared a baseline.
      </p>
    </>
  );
}
