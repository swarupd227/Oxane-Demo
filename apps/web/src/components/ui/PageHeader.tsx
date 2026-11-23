import { ArrowRight, FileStack, FlaskConical } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { usePresenterMode } from "../../lib/presenter";
import { Button } from "./Button";

interface PageHeaderProps {
  title: string;
  /** Counts, dates and IDs for the record on screen. Never a sentence about the screen. */
  summary?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ title, summary, actions }: PageHeaderProps) {
  return (
    <div className="mb-5 flex min-h-9 items-end justify-between gap-6">
      <div className="min-w-0">
        <h1 className="text-xl leading-tight font-semibold tracking-tight text-ink">{title}</h1>
        {summary && <p className="numeric mt-1 truncate text-[0.8125rem] text-subtle">{summary}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/** The walkthrough's next-step button. Shown only in walkthrough mode. */
export function NextStep({ to, label, size = "md" }: { to: string; label: string; size?: "sm" | "md" | "lg" }) {
  const { enabled } = usePresenterMode();
  const navigate = useNavigate();
  if (!enabled) {
    return null;
  }
  return (
    <Button size={size} onClick={() => navigate(to)}>
      {label}
      <ArrowRight aria-hidden className="size-4" />
    </Button>
  );
}

/** Keyboard hints, shown only in walkthrough mode. */
export function KeyHints({ children }: { children: ReactNode }) {
  const { enabled } = usePresenterMode();
  return enabled ? <>{children}</> : null;
}

export function SeedNotice({ children }: { children: ReactNode }) {
  return (
    <p className="mb-4 flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-xs text-subtle">
      <FlaskConical aria-hidden className="size-3.5 shrink-0" />
      {children}
    </p>
  );
}

export function NeedsIntake() {
  return (
    <div className="grid h-72 place-items-center rounded-xl border border-dashed border-line bg-surface text-center">
      <div className="max-w-sm">
        <span aria-hidden className="mx-auto grid size-11 place-items-center rounded-full bg-accent-tint text-accent">
          <FileStack className="size-5" />
        </span>
        <p className="mt-3 text-sm font-semibold text-ink">No documents received yet</p>
        <p className="mt-1 text-[0.8125rem] text-subtle">Terms appear here once the deal pack is loaded and read.</p>
        <Link
          to="/intake"
          className="mt-4 inline-flex h-8 items-center rounded-lg bg-accent px-3 text-[0.8125rem] font-medium text-white shadow-[0_1px_2px_rgb(16_24_40/0.05)] hover:bg-accent-strong"
        >
          Go to documents
        </Link>
      </div>
    </div>
  );
}
