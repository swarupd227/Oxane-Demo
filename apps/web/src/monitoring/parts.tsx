/* Small pieces every monitoring screen shares. */
import clsx from "clsx";
import { FileText, ZoomIn, ZoomOut } from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { PdfPage } from "../components/evidence/PdfPage";
import { fileUrl, OUTCOMES, type Outcome, type Source } from "./cycle";

export function WorkbenchSwitch({ current }: { current: "onboarding" | "monitoring" }) {
  const item = (to: string, label: string, active: boolean) => (
    <NavLink
      to={to}
      aria-current={active ? "page" : undefined}
      className={clsx(
        "flex h-7 items-center rounded-md px-2.5 text-xs font-medium transition-colors",
        active ? "bg-ink text-white" : "text-muted hover:text-ink",
      )}
    >
      {label}
    </NavLink>
  );
  return (
    <nav aria-label="Workbench" className="flex items-center gap-0.5 rounded-lg bg-sand p-0.5">
      {item("/", "Onboarding", current === "onboarding")}
      {item("/monitoring", "Monitoring", current === "monitoring")}
    </nav>
  );
}

export function OutcomePill({ outcome, pending }: { outcome: Outcome | null; pending?: string }) {
  if (!outcome) {
    return (
      <span className="inline-flex h-6 items-center rounded-full border border-dashed border-stone px-2.5 text-xs font-medium whitespace-nowrap text-muted">
        {pending ?? "To decide"}
      </span>
    );
  }
  return (
    <span
      className={clsx(
        "inline-flex h-6 items-center rounded-full px-2.5 text-xs font-medium whitespace-nowrap",
        OUTCOMES[outcome].tone,
      )}
    >
      {OUTCOMES[outcome].label}
    </span>
  );
}

const facilityTones: Record<string, string> = {
  bramble: "bg-[#efe3d3] text-[#6b4a1f]",
  northmoor: "bg-[#dfe8ef] text-[#2f4b63]",
  kestrel: "bg-[#e6e2ef] text-[#4a3f6b]",
};

export function FacilityTag({ id, name }: { id: string; name: string }) {
  return (
    <span
      className={clsx(
        "inline-flex h-5 items-center rounded px-1.5 text-[0.6875rem] font-semibold whitespace-nowrap",
        facilityTones[id] ?? "bg-sand text-muted",
      )}
    >
      {name}
    </span>
  );
}

export function Stat({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: "ok" | "warn" | "danger" }) {
  return (
    <div>
      <p className="text-xs font-medium text-muted">{label}</p>
      <p
        className={clsx(
          "numeric mt-0.5 text-xl font-semibold tracking-tight",
          tone === "danger" && "text-danger",
          tone === "warn" && "text-warn",
          tone === "ok" && "text-ok",
        )}
      >
        {value}
      </p>
      {note && <p className="mt-0.5 text-xs text-muted">{note}</p>}
    </div>
  );
}

const ZOOMS = [1, 1.5, 2];

function title(document: string): string {
  return document.split("/").pop()!.replace(/\.pdf$/, "").replaceAll("_", " ");
}

/** A cited page from the cycle's documents, opened on the highlighted passage. */
export function SourcePanel({ source, emptyText, tall }: { source: Source | null | undefined; emptyText?: string; tall?: boolean }) {
  // Reports are tables, so a whole page width reads better than a zoomed clause.
  const [zoomIndex, setZoomIndex] = useState(0);
  if (!source) {
    return (
      <div className="grid min-h-40 place-items-center rounded-lg border border-dashed border-line p-6 text-center text-sm text-muted">
        <span>
          <FileText aria-hidden className="mx-auto mb-2 size-5" />
          {emptyText ?? "Select an item to see its source."}
        </span>
      </div>
    );
  }
  const zoomButton = "cursor-pointer rounded p-1 text-muted hover:bg-sand disabled:opacity-40";
  return (
    <div className="overflow-hidden rounded-lg border border-line" role="group" aria-label="Source document">
      <div className="flex items-center justify-between gap-3 border-b border-line bg-canvas px-3 py-1.5 text-xs font-medium text-muted">
        <span className="truncate">{source.label ?? title(source.document)}</span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="numeric">Page {source.page}</span>
          <button type="button" aria-label="Zoom out" disabled={zoomIndex === 0} onClick={() => setZoomIndex((i) => i - 1)} className={zoomButton}>
            <ZoomOut aria-hidden className="size-3.5" />
          </button>
          <button
            type="button"
            aria-label="Zoom in"
            disabled={zoomIndex === ZOOMS.length - 1}
            onClick={() => setZoomIndex((i) => i + 1)}
            className={zoomButton}
          >
            <ZoomIn aria-hidden className="size-3.5" />
          </button>
        </span>
      </div>
      <div
        data-evidence-scroll
        tabIndex={0}
        role="region"
        aria-label="Source page"
        className={clsx("overflow-auto", tall ? "max-h-[calc(100vh-17rem)] min-h-80" : "max-h-[calc(100vh-24rem)] min-h-64")}
      >
        <div style={{ width: `${ZOOMS[zoomIndex] * 100}%` }}>
          <PdfPage
            key={`${source.document}-${source.page}-${zoomIndex}`}
            url={fileUrl(source.document)}
            page={source.page}
            rects={source.rects}
            label={`${title(source.document)}, page ${source.page}, with the cited passage highlighted`}
          />
        </div>
      </div>
    </div>
  );
}

/** Monthly values against a limit, drawn as bars with the limit as a rule. */
export function TrendBars({
  values,
  limit,
  direction = "max",
  extra,
  format = (v: number) => `${v.toFixed(2)}%`,
}: {
  values: { month: string; value: number }[];
  limit: number;
  direction?: "max" | "min";
  extra?: { month: string; value: number; breached: boolean } | null;
  format?: (value: number) => string;
}) {
  const all = [...values, ...(extra ? [extra] : [])];
  const top = Math.max(limit * 1.25, ...all.map((v) => v.value * 1.1));
  const bad = (v: number) => (direction === "max" ? v > limit : v < limit);
  // Bars, labels and the limit share one plot area, so they share one scale.
  const pct = (value: number) => `${(value / top) * 100}%`;
  return (
    <div role="img" aria-label={`${all.map((v) => `${v.month} ${format(v.value)}`).join(", ")}; limit ${format(limit)}`}>
      <div className="relative mt-2 ml-16 h-32 border-b border-line">
        <div className="absolute inset-x-0 flex h-full gap-3 px-2">
          {all.map((v, index) => {
            const projected = extra && index === all.length - 1;
            return (
              <div key={v.month} className="relative h-full flex-1">
                <div
                  className={clsx(
                    "absolute bottom-0 left-1/2 w-full max-w-14 -translate-x-1/2 rounded-t transition-all duration-300",
                    projected && "border-2 border-dashed",
                    projected
                      ? bad(v.value)
                        ? "border-danger bg-danger-tint"
                        : "border-subtle bg-sand"
                      : bad(v.value)
                        ? "bg-danger"
                        : "bg-subtle",
                  )}
                  style={{ height: pct(v.value) }}
                />
                <span
                  className={clsx("numeric absolute inset-x-0 text-center text-xs font-semibold", projected ? (bad(v.value) ? "text-danger" : "text-ink") : "text-white")}
                  style={{ bottom: `calc(${pct(v.value)} - 1.375rem)` }}
                >
                  {format(v.value)}
                </span>
              </div>
            );
          })}
        </div>
        <div className="pointer-events-none absolute inset-x-0" style={{ bottom: pct(limit) }}>
          <div className="border-t-2 border-dashed border-ink/70" />
          <span className="numeric absolute -left-16 -bottom-2 w-14 text-right text-[0.6875rem] leading-tight font-semibold">Limit {format(limit)}</span>
        </div>
      </div>
      <div className="mt-1.5 ml-16 flex gap-3 px-2">
        {all.map((v, index) => (
          <span key={v.month} className="flex-1 text-center text-[0.6875rem] text-muted">
            {v.month.replace(" 2026", "")}
            {extra && index === all.length - 1 ? " (what-if)" : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

const cents = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Money to the cent, for reconciliations where the cents are the point. */
export function usd2(amount: number): string {
  return `${amount < 0 ? "-" : ""}US$${cents.format(Math.abs(amount))}`;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-sm text-muted">{children}</p>;
}
