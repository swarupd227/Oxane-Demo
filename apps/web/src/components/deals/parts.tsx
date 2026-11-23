/* Pieces the new-deal screens share: form fields with inline errors, action buttons that say why
 * they are disabled, activity and hand-offs. */
import clsx from "clsx";
import { useState, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { Link } from "react-router-dom";
import { ApiError, type History, type WorkItem } from "../../lib/deals";
import { Badge } from "../../monitoring/ui";
import { Button } from "../ui/Button";
import { Tooltip } from "../ui/Tooltip";

export function when(iso: string | null | undefined): string {
  if (!iso) {
    return "–";
  }
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function Field({ label, error, hint, children, id }: { label: string; error?: string; hint?: string; children: ReactNode; id: string }) {
  return (
    <div className="mb-3">
      <label htmlFor={id} className="block text-xs font-medium">
        {label}
      </label>
      <div className="mt-1">{children}</div>
      {hint && !error && <p className="mt-0.5 text-[0.6875rem] text-muted">{hint}</p>}
      {error && (
        <p id={`${id}-error`} role="alert" className="mt-0.5 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

const control = "h-9 w-full rounded-md border bg-surface px-2.5 text-sm";

export function TextInput({ invalid, ...props }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      {...props}
      aria-invalid={invalid || undefined}
      aria-describedby={invalid ? `${props.id}-error` : undefined}
      className={clsx(control, invalid ? "border-danger" : "border-line", props.className)}
    />
  );
}

export function Select({ invalid, children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <select {...props} aria-invalid={invalid || undefined} className={clsx(control, invalid ? "border-danger" : "border-line", props.className)}>
      {children}
    </select>
  );
}

/** Run an action; keep the API's message and its per-field errors for the form. */
export function useForm() {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    setMessage(null);
    setErrors({});
    try {
      return await fn();
    } catch (error) {
      if (error instanceof ApiError) {
        setErrors(error.fields);
        setMessage(error.message);
      } else {
        setMessage(error instanceof Error ? error.message : "Something went wrong");
      }
      return null;
    } finally {
      setBusy(false);
    }
  };
  return { errors, message, busy, run, clear: () => { setErrors({}); setMessage(null); } };
}

export function FormMessage({ message }: { message: string | null }) {
  if (!message) {
    return null;
  }
  return (
    <p role="alert" className="mb-3 rounded-md bg-danger-tint px-3 py-2 text-[0.8125rem] font-medium text-danger">
      {message}
    </p>
  );
}

/** A button that, when the acting persona cannot use it, is disabled and says why. */
export function ActionButton({ reason, children, onClick, variant = "primary", busy }: { reason?: string | null; children: ReactNode; onClick: () => void; variant?: "primary" | "secondary" | "ghost"; busy?: boolean }) {
  const button = (
    <Button size="sm" variant={variant} disabled={Boolean(reason) || busy} onClick={onClick} aria-disabled={Boolean(reason) || undefined}>
      {children}
    </Button>
  );
  if (!reason) {
    return button;
  }
  return (
    <Tooltip content={reason}>
      <span tabIndex={0} aria-label={`${typeof children === "string" ? children : "Action"}: ${reason}`}>
        {button}
      </span>
    </Tooltip>
  );
}

export function Activity({ history, work }: { history: History; work?: WorkItem[] }) {
  return (
    <div>
      <p className="mb-2 flex items-center gap-2 text-xs text-muted">
        {history.entries.length} events · hash chain {history.chain_intact ? <Badge tone="ok">intact</Badge> : <Badge tone="danger">broken</Badge>}
      </p>
      {work && work.some((w) => w.status === "open") && (
        <ul className="mb-3 space-y-1">
          {work
            .filter((w) => w.status === "open")
            .map((w) => (
              <li key={w.id} className="flex items-center gap-2 rounded-md bg-info-tint px-2 py-1 text-xs">
                <span className="font-mono text-[0.6875rem] text-muted">{w.ref}</span>
                <span className="min-w-0 flex-1 truncate">
                  Waiting on {w.assignee_name || w.role_label}: {w.title}
                </span>
                <span className={clsx("numeric", w.overdue && "font-semibold text-danger")}>{w.overdue ? "Overdue" : `${Math.round(w.age_hours)}h`}</span>
              </li>
            ))}
        </ul>
      )}
      <ol className="space-y-1.5 text-xs">
        {history.entries.map((e) => (
          <li key={`${e.hash}`} className="flex gap-2">
            <span className="numeric w-24 shrink-0 text-muted">{when(e.at)}</span>
            <span className="min-w-0 flex-1">
              <span className="font-medium">{e.actor}</span> · {e.action}
              {e.reason && <span className="block text-muted">{e.reason}</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function Tabs({ tabs, current, base }: { tabs: { id: string; label: string; count?: number | string }[]; current: string; base: string }) {
  return (
    <nav aria-label="Sections" className="mb-4 flex flex-wrap gap-1 border-b border-line">
      {tabs.map((t) => (
        <Link
          key={t.id}
          to={`${base}/${t.id}`}
          aria-current={current === t.id ? "page" : undefined}
          className={clsx(
            "-mb-px flex h-9 items-center gap-1.5 border-b-2 px-3 text-[0.8125rem]",
            current === t.id ? "border-ink font-semibold" : "border-transparent text-muted hover:text-ink",
          )}
        >
          {t.label}
          {t.count !== undefined && t.count !== 0 && t.count !== "" && <span className="numeric rounded bg-sand px-1.5 text-[0.6875rem]">{t.count}</span>}
        </Link>
      ))}
    </nav>
  );
}

export const STATUS_TONE: Record<string, "ok" | "warn" | "danger" | "info" | "neutral"> = {
  approved: "ok",
  absent: "neutral",
  proposed: "info",
  missing: "danger",
  open: "warn",
  accepted: "ok",
  resolved: "ok",
  with_client: "info",
  answered: "info",
  with_expert: "info",
  decided: "info",
};

export const EXC_LABEL: Record<string, string> = {
  open: "Open",
  accepted: "Accepted",
  resolved: "Resolved",
  with_client: "With client",
  answered: "Client answered",
  with_expert: "With expert",
  decided: "Expert decided",
};
