import clsx from "clsx";
import type { ReactNode } from "react";
import { Tooltip } from "./Tooltip";
import {
  Bot,
  Calculator,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  Clock3,
  FunctionSquare,
  ShieldCheck,
  UserPen,
  type LucideIcon,
} from "lucide-react";

const tones = {
  neutral: "bg-sand text-muted",
  ok: "bg-ok-tint text-ok",
  warn: "bg-warn-tint text-warn",
  danger: "bg-danger-tint text-danger",
  info: "bg-info-tint text-info",
};

type Tone = keyof typeof tones;

function Pill({ tone, icon: Icon, label }: { tone: Tone; icon: LucideIcon; label: string }) {
  return (
    <span
      className={clsx(
        "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium whitespace-nowrap",
        tones[tone],
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      {label}
    </span>
  );
}

export type ReviewStatus = "approved" | "review" | "missing" | "open" | "pending";

const reviewStatuses: Record<ReviewStatus, { tone: Tone; icon: LucideIcon; label: string }> = {
  approved: { tone: "ok", icon: CheckCircle2, label: "Approved" },
  review: { tone: "warn", icon: Clock3, label: "Review" },
  missing: { tone: "danger", icon: CircleAlert, label: "Missing" },
  open: { tone: "info", icon: CircleAlert, label: "Open item" },
  pending: { tone: "neutral", icon: CircleDashed, label: "Not started" },
};

export function StatusPill({ status, label }: { status: ReviewStatus; label?: string }) {
  const config = reviewStatuses[status];
  return <Pill tone={config.tone} icon={config.icon} label={label ?? config.label} />;
}

export type Provenance = "ai" | "suggested" | "extracted" | "calculated" | "derived" | "edited" | "approved";

const provenances: Record<Provenance, { icon: LucideIcon; label: string }> = {
  ai: { icon: Bot, label: "AI drafted" },
  suggested: { icon: Bot, label: "Suggested" },
  extracted: { icon: Bot, label: "AI extracted" },
  calculated: { icon: Calculator, label: "Calculated" },
  derived: { icon: FunctionSquare, label: "Derived" },
  edited: { icon: UserPen, label: "Analyst edited" },
  approved: { icon: ShieldCheck, label: "Approved" },
};

/** Where a value came from. `tip` carries the source and its quote, on hover or focus. */
export function ProvenanceChip({ kind, tip, detail }: { kind: Provenance; tip?: ReactNode; detail?: string }) {
  const { icon: Icon, label } = provenances[kind];
  const chip = (
    <span
      tabIndex={tip ? 0 : undefined}
      className="inline-flex h-5 items-center gap-1 rounded border border-line bg-surface px-1.5 text-[0.6875rem] font-medium whitespace-nowrap text-muted"
    >
      <Icon aria-hidden className="size-3" />
      {label}
      {detail && <span className="font-normal text-muted">· {detail}</span>}
    </span>
  );
  return tip ? <Tooltip content={tip}>{chip}</Tooltip> : chip;
}

export type ConfidenceLevel = "high" | "medium" | "low";

const confidences: Record<ConfidenceLevel, { bars: number; label: string; bar: string }> = {
  high: { bars: 3, label: "High", bar: "bg-ok" },
  medium: { bars: 2, label: "Medium", bar: "bg-warn" },
  low: { bars: 1, label: "Low", bar: "bg-danger" },
};

export function Confidence({ level }: { level: ConfidenceLevel }) {
  const { bars, label, bar } = confidences[level];
  return (
    <span className="inline-flex items-center gap-2 text-xs font-medium text-muted">
      <span aria-hidden className="flex items-end gap-0.5">
        {[1, 2, 3].map((step) => (
          <span
            key={step}
            className={clsx("w-1 rounded-sm", step <= bars ? bar : "bg-line")}
            style={{ height: `${4 + step * 3}px` }}
          />
        ))}
      </span>
      {label}
    </span>
  );
}

export function Kbd({ children }: { children: string }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-line bg-surface px-1 font-sans text-[0.6875rem] font-medium text-muted">
      {children}
    </kbd>
  );
}

export function TierBadge({ tier }: { tier: 1 | 2 | 3 }) {
  return (
    <span
      className={clsx(
        "numeric inline-flex h-5 items-center rounded px-1.5 text-[0.6875rem] font-semibold whitespace-nowrap",
        tier === 1 ? "bg-ink text-white" : "bg-sand text-muted",
      )}
    >
      Tier {tier}
    </span>
  );
}
