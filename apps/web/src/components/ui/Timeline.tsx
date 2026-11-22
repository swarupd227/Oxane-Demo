import clsx from "clsx";
import { ShieldCheck, ShieldX } from "lucide-react";
import { formatDateTime } from "../../lib/format";
import { useSession, type AuditEntry } from "../../lib/session";
import { Avatar } from "./Avatar";

/** Audit entries that touched one record, newest first. */
export function useHistory(refs: string[]): AuditEntry[] {
  const { state } = useSession();
  const wanted = new Set(refs);
  return state.audit.filter((entry) => entry.refs?.some((ref) => wanted.has(ref))).reverse();
}

/** The hash-chained event log, as a record's activity timeline. */
export function Timeline({
  entries,
  empty = "No activity",
  showChain = false,
  className,
}: {
  entries: AuditEntry[];
  empty?: string;
  showChain?: boolean;
  className?: string;
}) {
  const { state } = useSession();
  return (
    <div className={className}>
      {showChain && (
        <p
          className={clsx(
            "mb-2 flex items-center gap-1.5 text-xs font-medium",
            state.chainIntact ? "text-ok" : "text-danger",
          )}
        >
          {state.chainIntact ? (
            <ShieldCheck aria-hidden className="size-3.5" />
          ) : (
            <ShieldX aria-hidden className="size-3.5" />
          )}
          {state.chainIntact ? "Hash chain verified" : "Hash chain broken"}
          <span className="font-mono font-normal text-muted">{state.chainHead.slice(0, 12)}</span>
        </p>
      )}
      {entries.length === 0 ? (
        <p className="text-xs text-muted">{empty}</p>
      ) : (
        <ol className="relative space-y-2.5 before:absolute before:top-1 before:bottom-1 before:left-3 before:w-px before:bg-line">
          {entries.map((entry, index) => (
            <li key={`${entry.seq ?? entry.at}-${index}`} className="relative flex gap-2.5">
              <Avatar name={entry.actor} className="relative z-10 ring-2 ring-surface" />
              <div className="min-w-0 flex-1 text-[0.8125rem] leading-snug">
                <p>
                  <span className="font-medium">{entry.actor}</span>{" "}
                  <span className="text-muted">{entry.action}</span>
                </p>
                {entry.reason && <p className="mt-0.5 text-muted">“{entry.reason}”</p>}
                <p className="numeric mt-0.5 flex flex-wrap gap-x-2 text-[0.6875rem] text-muted">
                  <span>{formatDateTime(entry.at)}</span>
                  {entry.seq !== undefined && <span>#{entry.seq}</span>}
                  {entry.hash && <span className="font-mono">{entry.hash.slice(0, 8)}</span>}
                  {entry.earlier && <span>Carried over</span>}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
