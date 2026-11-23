/* The frame every workbench shares: brand, workbench switch, navigation items and the header bar. */
import clsx from "clsx";
import { FolderKanban, LayoutGrid, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { MONITORING_ROLES, ONBOARDING_ROLES, useRole } from "../../lib/persona";

export const HEADER = "sticky top-0 z-30 flex h-12 shrink-0 items-center gap-3 border-b border-line bg-surface/90 px-6 backdrop-blur";
export const CONTENT = "flex min-w-0 flex-1 flex-col px-8 pt-5";

export function Brand() {
  return (
    <div className="flex items-center gap-2">
      <span aria-hidden className="grid size-6 place-items-center rounded-md bg-accent">
        <span className="h-3 w-1 rounded-full bg-white" />
      </span>
      <span className="text-[0.9375rem] font-semibold tracking-tight text-ink">Oxane</span>
    </div>
  );
}

export function WorkbenchSwitch({ current, shared = false }: { current: "onboarding" | "monitoring"; shared?: boolean }) {
  // Each role sees the workbenches it uses; with only one, there is nothing to switch.
  const role = useRole();
  const items = [
    { to: "/cases", label: "Onboarding", id: "onboarding", shown: !role || ONBOARDING_ROLES.includes(role) },
    { to: "/monitoring", label: "Monitoring", id: "monitoring", shown: !role || MONITORING_ROLES.includes(role) },
  ].filter((item) => item.shown);
  if (items.length === 1) {
    // One workbench: a plain way back to it from the shared pages, rather than a switch.
    const only = items[0];
    if (!shared && current === only.id) {
      return null;
    }
    return (
      <NavLink to={only.to} className={navItem(false)}>
        <NavIcon icon={only.id === "monitoring" ? LayoutGrid : FolderKanban} active={false} />
        {only.label} workbench
      </NavLink>
    );
  }
  if (items.length < 2) {
    return null;
  }
  return (
    <nav aria-label="Workbench" className="flex w-full items-center gap-0.5 rounded-lg bg-sand p-0.5">
      {items.map((item) => {
        const active = current === item.id;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            aria-current={active ? "page" : undefined}
            className={clsx(
              "flex h-7 flex-1 items-center justify-center rounded-md text-xs font-medium transition-colors",
              active ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink",
            )}
          >
            {item.label}
          </NavLink>
        );
      })}
    </nav>
  );
}

export function navItem(active: boolean, nested = false) {
  return clsx(
    "group flex items-center gap-2.5 rounded-md px-2.5 text-[0.8125rem] whitespace-nowrap transition-colors",
    nested ? "h-7" : "h-8",
    active ? "bg-accent-tint font-medium text-accent-strong" : "text-muted hover:bg-sand hover:text-ink",
  );
}

export function NavIcon({ icon: Icon, active }: { icon: LucideIcon; active: boolean }) {
  return (
    <Icon
      aria-hidden
      className={clsx("size-4 shrink-0", active ? "text-accent" : "text-subtle group-hover:text-muted")}
    />
  );
}

export function NavCount({
  value,
  active,
  alert,
}: {
  value?: string | number;
  active?: boolean;
  alert?: boolean;
}) {
  if (value === undefined || value === "" || value === 0 || value === "0") {
    return null;
  }
  return (
    <span
      className={clsx(
        "numeric ml-auto min-w-5 rounded-full px-1.5 text-center text-[0.6875rem] leading-[1.125rem] font-medium",
        alert ? "bg-danger-tint text-danger" : active ? "bg-surface text-accent-strong" : "bg-sand text-muted",
      )}
    >
      {value}
    </span>
  );
}

export function NavSection({ label, children, className }: { label?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={clsx("pt-4 first:pt-0", className)}>
      {label && <p className="px-2.5 pb-1 text-[0.6875rem] font-medium text-subtle">{label}</p>}
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

/** The full-height sidebar: brand and workbench switch on top, navigation, then a footer. */
export function SidebarFrame({
  current,
  shared = false,
  children,
  footer,
}: {
  current?: "onboarding" | "monitoring";
  /** My work, clients, facilities and settings belong to no single workbench. */
  shared?: boolean;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-surface lg:flex">
      <div className="space-y-3 px-3 pt-3 pb-3">
        <Brand />
        {current && <WorkbenchSwitch current={current} shared={shared} />}
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-3">{children}</div>
      {footer && <div className="border-t border-line px-2 py-2">{footer}</div>}
    </aside>
  );
}
