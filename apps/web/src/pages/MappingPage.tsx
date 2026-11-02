import { ArrowRight, CalendarClock, Check } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Confidence, ProvenanceChip, StatusPill } from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader, SeedNotice } from "../components/ui/PageHeader";
import { useSession } from "../lib/session";
import { useWorkbench, type Requirement } from "../lib/workbench";

function RequirementRow({ item }: { item: Requirement }) {
  return (
    <li className="border-b border-sand py-2.5 last:border-0">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{item.name}</span>
        {item.status === "derived" && <ProvenanceChip kind="derived" />}
        {item.status === "calculated" && <ProvenanceChip kind="calculated" />}
        {item.status === "met" && <StatusPill status="approved" label="Mapped" />}
      </div>
      <p className="mt-0.5 text-[0.8125rem] leading-snug text-muted">{item.detail}</p>
    </li>
  );
}

export function MappingPage() {
  const { data } = useWorkbench();
  const { state, dispatch } = useSession();
  const navigate = useNavigate();

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }

  const { rows, requirements, dates } = data.mapping;
  const review = rows.filter((row) => row.confidence !== "high").length;
  const isAccepted = (column: string) =>
    state.mappingAccepted || state.acceptedColumns.includes(column);
  const remaining = rows.filter((row) => !isAccepted(row.column)).length;

  return (
    <div>
      <PageHeader
        title="Data mapping"
        summary={`${rows.length} tape columns mapped to platform fields. ${review} are below high confidence. ${rows.length - remaining} accepted.`}
        actions={
          state.mappingAccepted ? (
            <Button size="lg" onClick={() => navigate("/validation")}>
              View validation
              <ArrowRight aria-hidden className="size-4" />
            </Button>
          ) : (
            <Button size="lg" onClick={() => dispatch({ type: "accept-mapping" })}>
              <Check aria-hidden className="size-4" />
              Accept remaining ({remaining})
            </Button>
          )
        }
      />
      {data.seed && (
        <SeedNotice>Reference data: mapping is from the reference set.</SeedNotice>
      )}

      <div className="grid grid-cols-[minmax(0,1fr)_24rem] items-start gap-5">
        <Card className="overflow-hidden">
          <div
            tabIndex={0}
            role="region"
            aria-label="Tape column mapping"
            className="max-h-[calc(100vh-19rem)] overflow-y-auto"
          >
            <table className="w-full text-left">
              <thead className="sticky top-0 z-10 bg-surface">
                <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
                  <th className="py-2 pr-4 pl-5">Tape column</th>
                  <th className="py-2 pr-4">Platform field</th>
                  <th className="py-2 pr-4">Sample</th>
                  <th className="py-2 pr-4">Confidence</th>
                  <th className="py-2 pr-5">
                    <span className="sr-only">Decision</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.column} className="border-b border-sand align-top last:border-0">
                    <td className="py-2 pr-4 pl-5 font-mono text-[0.8125rem]">{row.column}</td>
                    <td className="py-2 pr-4">
                      <span className="font-mono text-[0.8125rem]">{row.field}</span>
                      {row.note && (
                        <p className="mt-0.5 text-xs text-muted">{row.note}</p>
                      )}
                    </td>
                    <td className="numeric max-w-44 truncate py-2 pr-4 text-[0.8125rem] text-muted">
                      {row.sample || "Empty"}
                    </td>
                    <td className="py-2 pr-4">
                      <Confidence level={row.confidence} />
                    </td>
                    <td className="py-1.5 pr-5 text-right">
                      {isAccepted(row.column) ? (
                        <StatusPill status="approved" label="Accepted" />
                      ) : (
                        <Button
                          variant="secondary"
                          size="sm"
                          aria-label={`Accept ${row.column}`}
                          onClick={() => dispatch({ type: "accept-column", column: row.column })}
                        >
                          Accept
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="sticky top-32 space-y-4">
          <Card className="p-5">
            <h2 className="font-semibold">Lender requirements</h2>
            <p className="text-[0.8125rem] text-muted">Reporting fields required by Calderwood Bank plc.</p>
            <ul className="mt-2">
              {requirements.map((item) => (
                <RequirementRow key={item.name} item={item} />
              ))}
            </ul>
          </Card>
          <Card className="p-5">
            <div className="flex items-center gap-2">
              <CalendarClock aria-hidden className="size-4 text-muted" />
              <SectionLabel>Date formats resolved</SectionLabel>
            </div>
            <p className="numeric mt-2 text-2xl font-semibold tracking-tight">{dates.mixed_rows} rows</p>
            <p className="mt-1 text-[0.8125rem] leading-snug text-muted">
              Mixed MM/DD and DD/MM. {dates.method}. {dates.uncertain} {dates.uncertain === 1 ? "row remains" : "rows remain"}{" "}
              unresolved.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
