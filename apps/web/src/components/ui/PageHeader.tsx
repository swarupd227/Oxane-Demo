import { FlaskConical } from "lucide-react";
import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  summary?: string;
  actions?: ReactNode;
}

export function PageHeader({ title, summary, actions }: PageHeaderProps) {
  return (
    <div className="mb-5 flex items-end justify-between gap-6">
      <div className="min-w-0">
        <h1 className="text-[1.625rem] leading-tight font-semibold tracking-tight">{title}</h1>
        {summary && <p className="mt-1 text-[0.9375rem] text-muted">{summary}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SeedNotice({ children }: { children: ReactNode }) {
  return (
    <p className="mb-4 flex items-center gap-2 rounded-lg bg-sand px-3 py-2 text-[0.8125rem] text-muted">
      <FlaskConical aria-hidden className="size-4 shrink-0" />
      {children}
    </p>
  );
}

export function NeedsIntake() {
  return (
    <div className="grid h-72 place-items-center rounded-xl border border-dashed border-line text-center">
      <div>
        <p className="font-medium">No document pack yet</p>
        <p className="mt-1 text-sm text-muted">Upload the pack on the Intake step to begin.</p>
      </div>
    </div>
  );
}
