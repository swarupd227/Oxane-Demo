import clsx from "clsx";
import { FlaskConical, Radio, Rewind, RotateCw, Search } from "lucide-react";
import type { CaseStatus, CaseView, LlmMode } from "../../lib/api";
import { useCase } from "../../lib/api";
import { formatUsdShort } from "../../lib/format";
import { Kbd } from "../ui/badges";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/layout";
import { Tooltip } from "../ui/Tooltip";

const caseStatuses: Record<CaseStatus, { label: string; className: string }> = {
  awaiting_pack: { label: "Awaiting pack", className: "bg-sand text-muted" },
  in_review: { label: "In review", className: "bg-warn-tint text-warn" },
  approved: { label: "Approved", className: "bg-ok-tint text-ok" },
  approved_with_open_items: { label: "Approved with open items", className: "bg-info-tint text-info" },
};

const modes: Record<LlmMode, { label: string; hint: string; icon: typeof Radio }> = {
  replay: {
    label: "Replay",
    hint: "Results come from a recorded run. No model is being called.",
    icon: Rewind,
  },
  record: {
    label: "Recording",
    hint: "The model is being called and its responses saved.",
    icon: Radio,
  },
  live: { label: "Live", hint: "The model is being called now.", icon: Radio },
};

function DealIdentity({ data }: { data: CaseView }) {
  const { deal } = data;
  const status = caseStatuses[data.status];
  return (
    <>
      <div className="min-w-0">
        <p className="truncate text-[0.9375rem] leading-tight font-semibold">
          {deal.lender.short_name} / {deal.borrower.short_name}
        </p>
        <p className="numeric mt-0.5 truncate text-[0.8125rem] leading-tight text-muted">
          {formatUsdShort(deal.facility.limit_usd)} {deal.facility.short_type}
          <span aria-hidden className="mx-1.5 text-stone">
            |
          </span>
          Onboarding case {data.number}
        </p>
      </div>
      <span
        className={clsx(
          "inline-flex h-7 shrink-0 items-center rounded-full px-3 text-[0.8125rem] font-medium",
          status.className,
        )}
      >
        {status.label}
      </span>
    </>
  );
}

function ModeLabel({ mode }: { mode: LlmMode }) {
  const { label, hint, icon: Icon } = modes[mode];
  return (
    <Tooltip content={hint}>
      <span
        tabIndex={0}
        className="inline-flex h-7 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 text-xs font-medium text-muted"
      >
        <Icon aria-hidden className="size-3.5" />
        {label}
      </span>
    </Tooltip>
  );
}

export function DealBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { data, isPending, isError, refetch, isFetching } = useCase();

  return (
    <div className="flex h-16 items-center gap-6 border-b border-line bg-surface px-6">
      <div className="flex shrink-0 items-center gap-2.5 pr-6">
        <span aria-hidden className="size-5 rounded-[5px] bg-ink">
          <span className="ml-[5px] block h-full w-[5px] bg-accent" />
        </span>
        <span className="text-sm font-semibold tracking-tight">Onboarding Workbench</span>
      </div>

      <div className="flex min-w-0 flex-1 items-center gap-4 border-l border-line pl-6">
        {data && <DealIdentity data={data} />}
        {isPending && (
          <div className="space-y-1.5" role="status" aria-label="Loading deal">
            <Skeleton className="h-4 w-72" />
            <Skeleton className="h-3.5 w-56" />
          </div>
        )}
        {isError && !data && (
          <div role="alert" className="flex items-center gap-3 text-sm">
            <span className="text-danger">The case service is not responding.</span>
            <Button
              variant="secondary"
              size="sm"
              disabled={isFetching}
              onClick={() => void refetch()}
            >
              <RotateCw aria-hidden className="size-3.5" />
              Retry
            </Button>
          </div>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <Tooltip content="All documents and data are invented for this demo. Not connected to Panorama.">
          <span
            tabIndex={0}
            className="inline-flex h-7 items-center gap-1.5 rounded-md bg-ink px-2.5 text-xs font-medium text-white"
          >
            <FlaskConical aria-hidden className="size-3.5 text-accent" />
            Synthetic data
          </span>
        </Tooltip>
        {data && <ModeLabel mode={data.llm_mode} />}
        <Button variant="ghost" size="sm" onClick={onOpenPalette} aria-label="Open command menu">
          <Search aria-hidden className="size-4" />
          <Kbd>Ctrl</Kbd>
          <Kbd>K</Kbd>
        </Button>
      </div>
    </div>
  );
}
