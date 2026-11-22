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
    <div className="mb-4 flex min-h-9 items-center justify-between gap-6">
      <div className="min-w-0">
        <h1 className="text-xl leading-tight font-semibold tracking-tight">{title}</h1>
        {summary && <p className="numeric mt-0.5 truncate text-[0.8125rem] text-muted">{summary}</p>}
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
    <p className="mb-3 flex items-center gap-2 rounded-md bg-sand px-3 py-1.5 text-xs text-muted">
      <FlaskConical aria-hidden className="size-3.5 shrink-0" />
      {children}
    </p>
  );
}

export function NeedsIntake() {
  return (
    <div className="grid h-64 place-items-center rounded-lg border border-dashed border-line text-center">
      <div>
        <FileStack aria-hidden className="mx-auto size-5 text-muted" />
        <p className="mt-2 text-sm font-medium">No documents received</p>
        <Link to="/intake" className="mt-1 inline-block text-[0.8125rem] text-info underline-offset-2 hover:underline">
          Open Documents
        </Link>
      </div>
    </div>
  );
}
