/* Compact building blocks for the monitoring screens: page titles, panels, data tables,
 * people, record references, provenance chips and the activity timeline. */
import clsx from "clsx";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Gavel, Search, Sparkles } from "lucide-react";
import { useMemo, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from "react";
import { Tooltip } from "../components/ui/Tooltip";
import type { CycleAudit } from "./cycle";

const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const dateFmtLocal = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
const timeFmtUtc = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });

/** 22 Jun 2026, or 22 Jun 2026 14:05 when the value carries a time. */
export function when(value: string | null | undefined): string {
  if (!value) {
    return "–";
  }
  if (value.length <= 10) {
    return dateFmt.format(new Date(`${value}T00:00:00Z`));
  }
  // A time with no zone is the desk's own clock: show it as written.
  const zoned = value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value);
  const at = new Date(zoned ? value : `${value}Z`);
  return `${zoned ? dateFmtLocal.format(at) : dateFmt.format(at)} ${(zoned ? timeFmt : timeFmtUtc).format(at)}`;
}

export function money(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e6) {
    return `${sign}US$${(abs / 1e6).toFixed(2)}m`;
  }
  return `${sign}US$${Math.round(abs).toLocaleString("en-US")}`;
}

export function fmtUnit(value: number, unit: string): string {
  if (unit === "US$") {
    return money(value);
  }
  if (unit === "x") {
    return `${value.toFixed(2)}x`;
  }
  if (unit === "bps") {
    return `${Math.round(value)} bps`;
  }
  if (unit === "points") {
    return `${value.toFixed(2)} pts`;
  }
  return `${value.toFixed(2)}%`;
}

const WIDE = "(min-width: 1600px)";

/** True on wide screens, where tables can show their secondary columns. */
export function useWide(): boolean {
  return useSyncExternalStore(
    (notify) => {
      const query = window.matchMedia(WIDE);
      query.addEventListener("change", notify);
      return () => query.removeEventListener("change", notify);
    },
    () => window.matchMedia(WIDE).matches,
    () => true,
  );
}

export function PageTitle({ title, meta, actions }: { title: string; meta?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex min-h-9 items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-xl leading-tight font-semibold tracking-tight text-ink">{title}</h1>
        {meta && <p className="mt-1 truncate text-[0.8125rem] text-subtle">{meta}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ title, meta, actions, children, className, flush }: { title?: ReactNode; meta?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; flush?: boolean }) {
  return (
    <section className={clsx("rounded-xl border border-line bg-surface shadow-card", className)}>
      {(title || actions) && (
        <header className="flex min-h-11 items-center justify-between gap-3 border-b border-line px-4 py-2">
          <div className="flex min-w-0 items-baseline gap-2">
            {title && <h2 className="truncate text-sm font-semibold text-ink">{title}</h2>}
            {meta && <span className="truncate text-xs text-subtle">{meta}</span>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={flush ? undefined : "p-4"}>{children}</div>
    </section>
  );
}

export function Kpis({ items }: { items: { label: string; value: ReactNode; tone?: "ok" | "warn" | "danger"; onClick?: () => void }[] }) {
  const dot = { ok: "bg-ok", warn: "bg-warn", danger: "bg-danger" };
  // A figure must stay inside its tile. More than four tiles split into two even rows when the row
  // is narrow (under 64rem) or a figure is long (an amount to the cent), and a long figure steps
  // down a size; overflow-wrap is the last resort, never a spill past the border.
  const length = (value: ReactNode) => (typeof value === "string" || typeof value === "number" ? String(value).length : 0);
  const size = (value: ReactNode) => (length(value) > 13 ? "text-xl" : length(value) > 9 ? "text-[1.375rem]" : "text-2xl");
  const many = items.length > 4;
  const half = Math.ceil(items.length / 2);
  const wide = many && items.some((item) => length(item.value) > 12) ? half : items.length;
  const columns = (n: number) => `repeat(${n}, minmax(0, 1fr))`;
  return (
    <div className="mb-5 @container">
      <div
        className="grid grid-cols-(--kpi-narrow) gap-3 @5xl:grid-cols-(--kpi-wide)"
        style={{ "--kpi-narrow": columns(many ? half : items.length), "--kpi-wide": columns(wide) } as CSSProperties}
      >
        {items.map((item) => {
          const body = (
            <>
              <p className="flex items-start gap-1.5 text-xs leading-snug font-medium text-subtle">
                {item.tone && <span aria-hidden className={clsx("mt-1 size-1.5 shrink-0 rounded-full", dot[item.tone])} />}
                {item.label}
              </p>
              <p
                className={clsx(
                  "numeric mt-1.5 leading-tight font-semibold tracking-tight [overflow-wrap:anywhere]",
                  size(item.value),
                  item.tone === "danger" ? "text-danger" : item.tone === "warn" ? "text-warn" : "text-ink",
                )}
              >
                {item.value}
              </p>
            </>
          );
          const tile = "min-w-0 rounded-xl border border-line bg-surface px-4 py-3.5 text-left shadow-card";
          return item.onClick ? (
            <button key={item.label} type="button" onClick={item.onClick} className={clsx(tile, "cursor-pointer transition-colors hover:border-stone")}>
              {body}
            </button>
          ) : (
            <div key={item.label} className={tile}>
              {body}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const avatarTones = ["bg-[#e0e7ff] text-[#3730a3]", "bg-[#e0f2fe] text-[#075985]", "bg-[#dcfce7] text-[#166534]", "bg-[#fef3c7] text-[#92400e]", "bg-[#fce7f3] text-[#9d174d]", "bg-[#ede9fe] text-[#5b21b6]"];

export function initials(name: string): string {
  const words = name.replace(/[^A-Za-z ]/g, " ").split(/\s+/).filter(Boolean);
  return ((words[0]?.[0] ?? "") + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase();
}

export function Avatar({ name, size = "sm" }: { name: string; size?: "sm" | "md" }) {
  const tone = avatarTones[[...name].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % avatarTones.length];
  return (
    <span
      aria-hidden
      className={clsx("inline-flex shrink-0 items-center justify-center rounded-full font-semibold", tone, size === "sm" ? "size-5 text-[0.5625rem]" : "size-7 text-[0.6875rem]")}
    >
      {initials(name)}
    </span>
  );
}

export function Person({ name, sub }: { name: string; sub?: string }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <Avatar name={name} />
      <span className="min-w-0 truncate">
        {name}
        {sub && <span className="text-muted"> · {sub}</span>}
      </span>
    </span>
  );
}

export function RecordId({ children }: { children: ReactNode }) {
  return <span className="font-mono text-[0.6875rem] whitespace-nowrap text-muted">{children}</span>;
}

/** A model suggestion: a small chip, with the reason and any verified quote on hover. */
export function SuggestedChip({ by, detail }: { by: "AI" | "Rule"; detail?: ReactNode }) {
  const chip = (
    <span
      tabIndex={detail ? 0 : undefined}
      className={clsx(
        "inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-2 text-[0.6875rem] font-medium whitespace-nowrap",
        by === "AI" ? "bg-accent-tint text-accent-strong" : "bg-sand text-muted",
      )}
    >
      {by === "AI" ? <Sparkles aria-hidden className="size-3" /> : <Gavel aria-hidden className="size-3" />}
      {by === "AI" ? "Suggested" : "Rule"}
    </span>
  );
  return detail ? <Tooltip content={detail}>{chip}</Tooltip> : chip;
}

export type Tone = "ok" | "warn" | "danger" | "info" | "neutral";
const toneClass: Record<Tone, string> = {
  ok: "bg-ok-tint text-ok",
  warn: "bg-warn-tint text-warn",
  danger: "bg-danger-tint text-danger",
  info: "bg-info-tint text-info",
  neutral: "bg-sand text-muted",
};

const toneDot: Record<Tone, string> = { ok: "bg-ok", warn: "bg-warn", danger: "bg-danger", info: "bg-info", neutral: "bg-stone" };

export function Badge({ tone, children, icon }: { tone: Tone; children: ReactNode; icon?: ReactNode }) {
  return (
    <span className={clsx("inline-flex h-[1.375rem] shrink-0 items-center gap-1.5 rounded-full px-2 text-[0.6875rem] font-medium whitespace-nowrap", toneClass[tone])}>
      {icon ?? <span aria-hidden className={clsx("size-1.5 rounded-full", toneDot[tone])} />}
      {children}
    </span>
  );
}

/** Each event on a record, newest first, from the session's hash-chained log. */
export function Activity({ entries, origin }: { entries: CycleAudit[]; origin?: { at: string; text: string; by?: string }[] }) {
  const rows = [
    ...[...entries].reverse().map((e) => ({ at: e.at, by: e.actor, text: e.action, reason: e.reason, hash: e.hash })),
    ...(origin ?? []).map((o) => ({ at: o.at, by: o.by ?? "System", text: o.text, reason: null, hash: undefined })),
  ];
  if (!rows.length) {
    return <p className="text-xs text-muted">No activity.</p>;
  }
  return (
    <ol className="relative space-y-2 border-l border-line pl-3">
      {rows.map((row, index) => (
        <li key={`${row.at}-${index}`} className="relative text-xs">
          <span aria-hidden className="absolute top-1 -left-[1.03rem] size-2 rounded-full border border-line bg-surface" />
          <p className="flex flex-wrap items-baseline gap-x-2">
            <span className="numeric text-muted">{when(row.at)}</span>
            <span className="font-medium">{row.by}</span>
            {row.hash && <RecordId>#{row.hash.slice(0, 8)}</RecordId>}
          </p>
          <p className="text-ink">{row.text}</p>
          {row.reason && <p className="text-muted">“{row.reason}”</p>}
        </li>
      ))}
    </ol>
  );
}

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  sort?: (row: T) => string | number;
  align?: "left" | "right";
  className?: string;
}

export function SearchBox({ value, onChange, placeholder, label }: { value: string; onChange: (v: string) => void; placeholder: string; label: string }) {
  return (
    <label className="relative flex items-center">
      <Search aria-hidden className="pointer-events-none absolute left-2.5 size-3.5 text-subtle" />
      <input
        type="search"
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-8 w-60 rounded-lg border border-line bg-surface pr-2 pl-8 text-[0.8125rem] shadow-[0_1px_2px_rgb(16_24_40/0.05)] placeholder:text-subtle"
      />
    </label>
  );
}

export function FilterSelect<V extends string>({ label, value, options, onChange }: { label: string; value: V; options: { value: V; label: string }[]; onChange: (v: V) => void }) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value as V)} className="h-8 rounded-lg border border-line bg-surface px-2.5 text-[0.8125rem] text-ink-soft shadow-[0_1px_2px_rgb(16_24_40/0.05)]">
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/** A sortable, searchable, paginated table. Filters live in the toolbar the page passes in. */
export function DataTable<T>({
  rows,
  columns,
  rowKey,
  search,
  searchPlaceholder = "Search",
  toolbar,
  initialSort,
  pageSize = 25,
  onRowClick,
  selected,
  rowClassName,
  empty = "No records match.",
  title,
  initialQuery = "",
}: {
  initialQuery?: string;
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  search?: (row: T) => string;
  searchPlaceholder?: string;
  toolbar?: ReactNode;
  initialSort?: { key: string; dir: "asc" | "desc" };
  pageSize?: number;
  onRowClick?: (row: T) => void;
  selected?: string | null;
  rowClassName?: (row: T) => string | undefined;
  empty?: string;
  title?: ReactNode;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [sort, setSort] = useState(initialSort ?? null);
  const [page, setPage] = useState(0);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = q && search ? rows.filter((row) => search(row).toLowerCase().includes(q)) : rows;
    const column = sort && columns.find((c) => c.key === sort.key);
    if (column?.sort) {
      const get = column.sort;
      list = [...list].sort((a, b) => {
        const x = get(a);
        const y = get(b);
        const order = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
        return sort!.dir === "asc" ? order : -order;
      });
    }
    return list;
  }, [rows, query, search, sort, columns]);
  const pages = Math.max(1, Math.ceil(shown.length / pageSize));
  const current = Math.min(page, pages - 1);
  const slice = shown.slice(current * pageSize, current * pageSize + pageSize);
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-card">
      {(search || toolbar || title) && (
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
          {title && <h2 className="mr-2 text-sm font-semibold text-ink">{title}</h2>}
          {search && (
            <SearchBox
              value={query}
              onChange={(v) => {
                setQuery(v);
                setPage(0);
              }}
              placeholder={searchPlaceholder}
              label={searchPlaceholder}
            />
          )}
          {toolbar}
          <span className="numeric ml-auto text-xs text-subtle">
            {shown.length === rows.length ? `${rows.length} records` : `${shown.length} of ${rows.length}`}
          </span>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[0.8125rem]">
          <thead>
            <tr className="border-b border-line bg-canvas text-xs font-medium text-subtle">
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const Icon = active ? (sort!.dir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
                return (
                  <th key={c.key} scope="col" aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined} className={clsx("px-3 py-2.5 font-medium whitespace-nowrap first:pl-4 last:pr-4", c.align === "right" && "text-right")}>
                    {c.sort ? (
                      <button
                        type="button"
                        onClick={() => setSort(active && sort!.dir === "asc" ? { key: c.key, dir: "desc" } : { key: c.key, dir: "asc" })}
                        className={clsx("inline-flex cursor-pointer items-center gap-1 hover:text-ink", c.align === "right" && "flex-row-reverse")}
                      >
                        {c.header}
                        <Icon aria-hidden className={clsx("size-3", !active && "opacity-40")} />
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {slice.map((row) => {
              const key = rowKey(row);
              return (
                <tr
                  key={key}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  aria-selected={selected !== undefined ? selected === key : undefined}
                  className={clsx(
                    "border-b border-line/70 align-middle transition-colors last:border-0",
                    onRowClick && "cursor-pointer hover:bg-canvas",
                    selected === key && "bg-accent-tint/70 hover:bg-accent-tint",
                    rowClassName?.(row),
                  )}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={clsx("px-3 py-2.5 first:pl-4 last:pr-4", c.align === "right" && "text-right", c.className)}>
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
            {!slice.length && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-6 text-center text-xs text-muted">
                  {empty}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 border-t border-line px-4 py-2 text-xs text-subtle">
          <span className="numeric">
            {current * pageSize + 1}–{Math.min(shown.length, (current + 1) * pageSize)} of {shown.length}
          </span>
          <button type="button" aria-label="Previous page" disabled={current === 0} onClick={() => setPage(current - 1)} className="cursor-pointer rounded p-1 hover:bg-sand disabled:opacity-40">
            <ChevronLeft aria-hidden className="size-3.5" />
          </button>
          <button type="button" aria-label="Next page" disabled={current >= pages - 1} onClick={() => setPage(current + 1)} className="cursor-pointer rounded p-1 hover:bg-sand disabled:opacity-40">
            <ChevronRight aria-hidden className="size-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
