import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronRight, CircleAlert } from "lucide-react";
import { Button } from "../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader, SeedNotice } from "../components/ui/PageHeader";
import { useSession } from "../lib/session";

interface Measure {
  name: string;
  formula: string;
  target: string;
  value: string;
  details: string[];
  passed: boolean | null;
}

interface Scorecard {
  available: boolean;
  measures: Measure[];
  caveat?: string;
}

function Row({ measure }: { measure: Measure }) {
  return (
    <details className="group border-b border-sand last:border-0">
      <summary className="grid cursor-pointer list-none grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.1fr)] items-center gap-4 px-5 py-3 hover:bg-canvas">
        <span className="flex items-center gap-2 text-sm font-medium">
          <ChevronRight
            aria-hidden
            className="size-3.5 shrink-0 text-muted transition-transform group-open:rotate-90"
          />
          {measure.name}
        </span>
        <span className="text-[0.8125rem] text-muted">{measure.target}</span>
        <span className="numeric flex items-center gap-2 text-sm font-semibold">
          {measure.passed === true && (
            <CheckCircle2 aria-label="Target met" className="size-4 shrink-0 text-ok" />
          )}
          {measure.passed === false && (
            <CircleAlert aria-label="Target missed" className="size-4 shrink-0 text-danger" />
          )}
          {measure.value}
        </span>
      </summary>
      <div className="bg-canvas px-5 py-3 pl-11 text-[0.8125rem]">
        <p>
          <span className="font-medium">How it is calculated:</span> {measure.formula}.
        </p>
        {measure.details.length > 0 && (
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-muted">
            {measure.details.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}
      </div>
    </details>
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
      <Card role="alert" className="p-5">
        <p className="font-medium">The scorecard could not be calculated.</p>
        <Button variant="secondary" className="mt-3" onClick={() => void refetch()}>
          Try again
        </Button>
      </Card>
    );
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }

  return (
    <div>
      <PageHeader
        title="Scorecard"
        summary="Oxane's success measures, scored against the answer key. Open a row for its formula."
      />
      {data.available ? (
        <SeedNotice>{data.caveat}</SeedNotice>
      ) : (
        <SeedNotice>Seed data: no model has run yet, so nothing can be scored.</SeedNotice>
      )}

      {data.available && (
        <Card className="overflow-hidden">
          <div className="grid grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.1fr)] gap-4 border-b border-line px-5 py-2.5 text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
            <span className="pl-5">Measure</span>
            <span>Demo target</span>
            <span>Result</span>
          </div>
          {data.measures.map((measure) => (
            <Row key={measure.name} measure={measure} />
          ))}
        </Card>
      )}

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
