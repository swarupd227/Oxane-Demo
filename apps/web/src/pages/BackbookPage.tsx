import { CheckCircle2, CircleAlert, Download } from "lucide-react";
import { ProvenanceChip, StatusPill } from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Card, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader } from "../components/ui/PageHeader";
import { caseworkFileUrl, useCasework, usd2, type BackbookDifference } from "../lib/casework";
import { useSession } from "../lib/session";

const KIND = {
  unknown_column: "Column not in stored mapping",
  blank_values: "Blank values",
  code_values: "Codes not in reference data",
};

function suggestionText(difference: BackbookDifference): string {
  const s = difference.suggestion;
  if (!s) {
    return "No suggestion";
  }
  if (difference.kind === "unknown_column") {
    return s.field
      ? `${difference.column} → ${s.field}${s.kind === "renamed_column" ? " (renamed)" : ""}`
      : `${difference.column} → raw data only`;
  }
  if (difference.kind === "blank_values") {
    return s.treat_blank_as === null ? "Exclude rows" : `Blank → ${s.treat_blank_as}`;
  }
  return s.code_map.map(([code, value]) => `${code} → ${value}`).join(", ");
}

export function BackbookPage() {
  const { state, dispatch } = useSession();
  const { data } = useCasework();

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }
  const deals = data.backbook;
  const rows = deals.reduce((sum, deal) => sum + deal.rows, 0);
  const loaded = deals.filter((deal) => deal.loaded).length;
  const exceptions = deals.reduce((sum, deal) => sum + deal.exceptions, 0);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Backbook load"
        summary={`Period 30 Apr 2026 · stored mapping: Bramble, ${deals[0]?.stored ?? 0} columns · ${deals.length} deals · ${rows.toLocaleString("en-US")} loans · ${exceptions} exceptions · ${loaded}/${deals.length} loaded`}
      />
      <div className="grid grid-cols-2 gap-4">
        {deals.map((deal) => (
          <Card key={deal.id} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs text-muted">{deal.deal_type}</p>
                <h2 className="truncate font-semibold">{deal.name}</h2>
              </div>
              <StatusPill
                status={deal.loaded ? "approved" : "review"}
                label={deal.loaded ? "Loaded" : `${deal.exceptions} exception${deal.exceptions === 1 ? "" : "s"}`}
              />
            </div>
            <dl className="numeric mt-3 grid grid-cols-4 gap-2 text-[0.8125rem]">
              <div>
                <dt className="text-xs text-muted">Loans</dt>
                <dd className="font-medium">{deal.rows}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Columns mapped</dt>
                <dd className="font-medium">
                  {deal.matched}/{deal.columns}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs text-muted">Pool balance</dt>
                <dd className="font-medium">US${usd2.format(deal.pool_balance)}</dd>
              </div>
            </dl>
            {deal.differences.length > 0 && (
              <ul className="mt-3 space-y-2">
                {deal.differences.map((difference) => (
                  <li key={difference.column} className="rounded-md bg-canvas px-3 py-2 text-[0.8125rem]">
                    <p className="flex items-center justify-between gap-2">
                      <span>
                        <span className="font-mono text-xs">{difference.column}</span>{" "}
                        <span className="text-muted">
                          · {KIND[difference.kind]}
                          {difference.rows ? ` · ${difference.rows} rows` : ""}
                        </span>
                      </span>
                      <ProvenanceChip kind="suggested" tip={difference.suggestion?.reason ?? "No suggestion"} />
                    </p>
                    <p className="mt-1 font-medium">{suggestionText(difference)}</p>
                    <p
                      className={`mt-1 flex items-start gap-1.5 text-xs ${difference.check.ok ? "text-ok" : "text-danger"}`}
                    >
                      {difference.check.ok ? (
                        <CheckCircle2 aria-hidden className="mt-px size-3.5 shrink-0" />
                      ) : (
                        <CircleAlert aria-hidden className="mt-px size-3.5 shrink-0" />
                      )}
                      {difference.check.evidence}
                    </p>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-3 flex items-center justify-between gap-2">
              <a
                href={caseworkFileUrl(deal.file)}
                className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink"
              >
                <Download aria-hidden className="size-3.5" />
                {deal.file}
              </a>
              {deal.can_accept && (
                <Button
                  size="sm"
                  disabled={state.actor !== "analyst"}
                  onClick={() => dispatch({ type: "accept-backbook", deal: deal.id })}
                >
                  Accept and load
                </Button>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
