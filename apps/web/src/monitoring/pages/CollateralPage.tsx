import clsx from "clsx";
import { ArrowRight, Car, CheckCircle2, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { PageHeader } from "../../components/ui/PageHeader";
import { formatCount } from "../../lib/format";
import { useCycle } from "../cycle";
import { FacilityTag, usd2 } from "../parts";

const FIELDS: [string, (h: Record<string, unknown>) => string][] = [
  ["Loan", (h) => String(h.loan_id)],
  ["Vehicle", (h) => String(h.vehicle)],
  ["Status", (h) => String(h.status).toLowerCase()],
  ["Balance", (h) => usd2(Number(h.current_balance))],
  ["Originated, as on tape", (h) => String(h.origination_date)],
  ["Dealer", (h) => String(h.dealer_name)],
  ["Obligor state", (h) => String(h.obligor_state)],
  ["Days past due", (h) => String(h.days_past_due)],
];

export function CollateralPage() {
  const { data: cycle } = useCycle();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const c = cycle.collateral;
  const names = Object.fromEntries(cycle.facilities.map((f) => [f.id, f.name]));
  return (
    <>
      <PageHeader
        title="Duplicate collateral"
        summary="Every VIN on the May tapes, checked within each pool and across the lender's facilities. A car can secure only one loan."
        actions={
          <Button onClick={() => navigate("/monitoring/triage")}>
            Triage
            <ArrowRight aria-hidden className="size-4" />
          </Button>
        }
      />
      <div className="mb-5 grid grid-cols-4 gap-3">
        {Object.entries(c.checked).map(([id, count]) => (
          <Card key={id} className="px-4 py-3">
            <p className="text-xs text-muted">{names[id]}</p>
            <p className="numeric text-lg font-semibold">{formatCount(count)} live loans</p>
          </Card>
        ))}
        <Card className="px-4 py-3">
          <p className="text-xs text-muted">Within one pool</p>
          <p className="flex items-center gap-1.5 text-lg font-semibold text-ok">
            <CheckCircle2 aria-hidden className="size-4" />
            {c.within.length} shared VINs
          </p>
        </Card>
        <Card className={clsx("px-4 py-3", c.across.length && "border-danger")}>
          <p className="text-xs text-muted">Across facilities</p>
          <p className={clsx("flex items-center gap-1.5 text-lg font-semibold", c.across.length ? "text-danger" : "text-ok")}>
            <ShieldAlert aria-hidden className="size-4" />
            {c.across.length} shared VIN
          </p>
        </Card>
      </div>
      {c.across.map((shared) => (
        <Card key={shared.vin} className="p-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="flex items-center gap-2 font-semibold">
                <Car aria-hidden className="size-4 text-muted" />
                VIN <code className="font-mono">{shared.vin}</code>
              </p>
              <p className="mt-1 text-sm text-muted">
                Pledged in {shared.holdings.map((h) => names[h.facility]).join(" and ")}. The same car may have been pledged twice, or a title has been reused.
              </p>
            </div>
            <Button onClick={() => setOpen((value) => !value)} variant={open ? "secondary" : "primary"}>
              {open ? "Hide tape rows" : "Open both tape rows"}
            </Button>
          </div>
          {open && (
            <div className="mt-5 grid grid-cols-2 gap-4">
              {shared.holdings.map((holding) => (
                <div key={holding.loan_id} className="rounded-lg border border-line">
                  <div className="flex items-center justify-between border-b border-line bg-canvas px-4 py-2">
                    <FacilityTag id={holding.facility} name={names[holding.facility]} />
                    <span className="text-xs text-muted">May 2026 tape</span>
                  </div>
                  <dl className="grid grid-cols-[8rem_1fr] gap-y-1.5 px-4 py-3 text-sm">
                    {FIELDS.map(([label, read]) => (
                      <div key={label} className="contents">
                        <dt className="text-muted">{label}</dt>
                        <dd className={clsx("numeric", label === "Vehicle" && "font-semibold")}>{read(holding as unknown as Record<string, unknown>)}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </div>
          )}
        </Card>
      ))}
      <div className="mt-4">
        <SectionLabel>Scope: {c.scope}. Checks across lenders depend on data rights that are not agreed.</SectionLabel>
      </div>
    </>
  );
}
