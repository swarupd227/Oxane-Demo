import { ArrowRight, Info, RotateCw } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card, Money, SectionLabel, Skeleton } from "../components/ui/layout";
import { useCase, type Deal } from "../lib/api";
import { formatCount, formatDate, formatUsd, formatUsdShort } from "../lib/format";

function Fact({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      <p className="mt-1.5 text-[0.9375rem] font-medium">{value}</p>
      {detail && <p className="mt-0.5 text-[0.8125rem] leading-snug text-muted">{detail}</p>}
    </div>
  );
}

function DateLine({ dates }: { dates: Deal["dates"] }) {
  return (
    <ol className="grid grid-cols-4">
      {dates.map((item, index) => (
        <li key={item.label} className="relative pt-6 pr-4">
          <span
            aria-hidden
            className="absolute top-[0.3125rem] left-0 size-2.5 rounded-full border-2 border-ink bg-surface"
          />
          {index < dates.length - 1 && (
            <span aria-hidden className="absolute top-[0.5625rem] right-0 left-2.5 h-0.5 bg-line" />
          )}
          <p className="numeric text-sm font-semibold">{formatDate(item.date)}</p>
          <p className="mt-0.5 text-[0.8125rem] leading-snug text-muted">{item.label}</p>
        </li>
      ))}
    </ol>
  );
}

function DealCard({ deal }: { deal: Deal }) {
  const { facility, lender, borrower, pricing, oxane_role: role, analysts } = deal;
  const goLive = deal.case.target_go_live;
  const navigate = useNavigate();

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_24rem] gap-6">
      <Card className="p-10">
        <SectionLabel>{facility.type}</SectionLabel>
        <h1 className="mt-4 text-[2.75rem] leading-[1.1] font-semibold tracking-tight">
          {lender.short_name}
          <span className="text-subtle"> / </span>
          {borrower.short_name}
        </h1>
        <p className="mt-6 text-[3.5rem] leading-none font-semibold tracking-tight">
          <Money value={formatUsdShort(facility.limit_usd)} />
        </p>
        <p className="numeric mt-2 text-[0.9375rem] text-muted">
          {formatUsd(facility.limit_usd)} facility limit
        </p>

        <div className="mt-10 grid grid-cols-4 gap-x-8 gap-y-6 border-t border-line pt-8">
          <Fact label="Lender" value={lender.name} detail={lender.desk} />
          <Fact label="Borrower" value={borrower.name} detail={borrower.description} />
          <Fact
            label="Collateral"
            value={facility.collateral}
            detail={`About ${formatCount(facility.first_tape_loans)} loans in the first tape`}
          />
          <Fact label="Pricing" value={pricing.margin} detail={`${pricing.unused_fee} unused fee`} />
        </div>

        <div className="mt-10 border-t border-line pt-8">
          <DateLine dates={deal.dates} />
        </div>
      </Card>

      <div className="flex flex-col gap-6">
        <Card tone="inverse" className="flex-1 p-8">
          <p className="text-[0.6875rem] font-semibold tracking-[0.08em] text-stone uppercase">
            Oxane's role
          </p>
          <p className="mt-4 text-2xl leading-snug font-semibold">{role.title}</p>
          <p className="mt-3 text-[0.9375rem] leading-relaxed text-sand">{role.summary}</p>
        </Card>

        <Card className="space-y-5 p-6">
          <Fact label="Prepared by" value={analysts.preparer} />
          <Fact label="Approved by" value={analysts.approver} />
          <Fact label="Target go-live" value={goLive ? formatDate(goLive) : "To be confirmed"} />
        </Card>

        <Button size="lg" className="w-full justify-between" onClick={() => navigate("/intake")}>
          Start onboarding
          <ArrowRight aria-hidden className="size-4" />
        </Button>
      </div>
    </div>
  );
}

export function DealCardPage() {
  const { data, isPending, isError, refetch } = useCase();

  return (
    <div className="space-y-5">
      <p className="flex items-center gap-2 text-sm text-muted">
        <Info aria-hidden className="size-4 shrink-0" />
        All names, documents and data in this demo are invented. It is not connected to Panorama and
        uses no Oxane or client data.
      </p>
      {data && <DealCard deal={data.deal} />}
      {isPending && (
        <Card className="space-y-4 p-8" role="status" aria-label="Loading deal">
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-10 w-[32rem]" />
          <Skeleton className="h-10 w-40" />
          <Skeleton className="h-32 w-full" />
        </Card>
      )}
      {isError && !data && (
        <Card role="alert" className="p-8">
          <p className="font-medium">The deal could not be loaded.</p>
          <p className="mt-1 text-sm text-muted">
            Check that the API container is running, then try again.
          </p>
          <Button variant="secondary" className="mt-4" onClick={() => void refetch()}>
            <RotateCw aria-hidden className="size-4" />
            Try again
          </Button>
        </Card>
      )}
    </div>
  );
}
