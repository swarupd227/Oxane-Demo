import clsx from "clsx";
import { Bot, CalendarClock, Cog, MessageSquareText, Zap } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Badge, type Tone } from "../monitoring/ui";
import type { AgentKind, Outcome, TriggerKind } from "./api";

/** Where the console is mounted: under either workbench. */
export function useBase(): string {
  const { pathname } = useLocation();
  return pathname.startsWith("/monitoring") ? "/monitoring/agents" : "/agents";
}

export function KindBadge({ kind }: { kind: AgentKind }) {
  return kind === "model" ? (
    <Badge tone="info" icon={<Bot aria-hidden className="size-3" />}>
      Model
    </Badge>
  ) : (
    <Badge tone="neutral" icon={<Cog aria-hidden className="size-3" />}>
      No model
    </Badge>
  );
}

const OUTCOME_TONE: Record<Outcome, Tone> = {
  accepted: "ok",
  edited: "info",
  rejected: "danger",
  quote_check_failed: "danger",
  refused: "neutral",
  awaiting_review: "warn",
  pending_recording: "warn",
};

export function OutcomeBadge({ outcome, labels }: { outcome: Outcome; labels: Record<Outcome, string> }) {
  return <Badge tone={OUTCOME_TONE[outcome]}>{labels[outcome] ?? outcome}</Badge>;
}

const TRIGGER_ICON = { event: Zap, schedule: CalendarClock, request: MessageSquareText } as const;
const TRIGGER_WORD: Record<TriggerKind, string> = { event: "Event", schedule: "Schedule", request: "Request" };

export function Trigger({ kind, label, compact }: { kind: TriggerKind; label: string; compact?: boolean }) {
  const Icon = TRIGGER_ICON[kind];
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <Icon aria-label={TRIGGER_WORD[kind]} className="size-3.5 shrink-0 text-muted" />
      <span className={clsx("min-w-0", compact && "truncate")}>{label}</span>
    </span>
  );
}

export function Tabs() {
  const base = useBase();
  const { pathname } = useLocation();
  const tabs = [
    { to: base, label: "Agents", end: true },
    { to: `${base}/graph`, label: "Dependencies", end: true },
    { to: `${base}/coverage`, label: "Coverage", end: true },
    { to: `${base}/runs`, label: "Run log", end: true },
  ];
  const onDetail = !tabs.some((t) => t.to === pathname);
  return (
    <nav aria-label="Agents console" className="mb-3 flex items-center gap-1 border-b border-line">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) =>
            clsx(
              "-mb-px border-b-2 px-2.5 pb-1.5 text-[0.8125rem]",
              isActive || (onDetail && tab.to === base) ? "border-accent font-medium text-accent-strong" : "border-transparent text-muted hover:text-ink",
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}

export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return <Badge tone={tone}>{children}</Badge>;
}

export function Meter({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-muted">–</span>;
  }
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className="h-1.5 w-12 overflow-hidden rounded-full bg-sand">
        <span className="block h-full rounded-full bg-ok" style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      <span className="numeric">{Math.round(value * 100)}%</span>
    </span>
  );
}
