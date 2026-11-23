/* The shell for My work, clients, new cases, live facilities and the client portal. */
import clsx from "clsx";
import { Building2, FolderKanban, Landmark, ListTodo, Settings, type LucideIcon } from "lucide-react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { useDealsStatus, useWork } from "../../lib/deals";
import { NAV_ROLES, usePersona, type Role } from "../../lib/persona";
import { Brand, CONTENT, HEADER, NavCount, NavIcon, navItem, SidebarFrame } from "./frame";
import { EnvironmentFooter } from "./AppShell";
import { EnvironmentLabel, NotificationBell, WalkthroughToggle } from "./HeaderControls";
import { PersonaMenu, useWorkBell } from "./Persona";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  roles: Role[];
}

const NAV: NavItem[] = [
  { to: "/work", label: "My work", icon: ListTodo, roles: NAV_ROLES["/work"] },
  { to: "/cases", label: "Onboarding cases", icon: FolderKanban, roles: NAV_ROLES["/cases"] },
  { to: "/facilities", label: "Facilities", icon: Landmark, roles: NAV_ROLES["/facilities"] },
  { to: "/clients", label: "Clients", icon: Building2, roles: NAV_ROLES["/clients"] },
  { to: "/settings/ai-provider", label: "Settings", icon: Settings, roles: NAV_ROLES["/settings/ai-provider"] },
];

export function visibleNav(role: Role | undefined): NavItem[] {
  return NAV.filter((item) => role && item.roles.includes(role));
}

function LiveState() {
  const { data } = useDealsStatus();
  if (!data) {
    return null;
  }
  let text = data.mode === "live" ? "Live AI" : data.mode === "stub" ? "Test model" : "AI replay";
  let tone = data.mode === "live" ? "border-ok/30 bg-ok-tint text-ok" : "border-line bg-surface text-muted";
  if (!data.access_configured) {
    text = "Uploads off";
  } else if (data.cap_reached) {
    text = "Daily AI limit reached";
    tone = "border-danger/40 bg-danger-tint text-danger";
  } else if (data.mode === "live" && data.key_ok === false) {
    // The key's last connection test failed (Settings › AI provider), so live calls will too.
    text = "Live AI · key failing";
    tone = "border-warn/40 bg-warn-tint text-warn";
  }
  return (
    <span role="status" title={`US$${data.spent_today_usd.toFixed(2)} of US$${data.cap_usd.toFixed(2)} live spend today`} className={clsx("inline-flex h-6 items-center gap-1.5 rounded-full border px-2 text-[0.6875rem] font-medium", tone)}>
      {text}
    </span>
  );
}

export function WorkspaceShell() {
  const { persona } = usePersona();
  const { pathname } = useLocation();
  const bell = useWorkBell();
  const { data: work } = useWork(Boolean(persona));
  const role = persona?.role;
  if (role === "client" && !pathname.startsWith("/portal")) {
    return <Navigate to="/portal" replace />;
  }
  const monitoringSide = pathname.startsWith("/facilities");
  const client = role === "client";
  const nav = (
    <nav aria-label="Workspace" className="space-y-0.5">
      {visibleNav(role).map((item) => {
        const active =
          pathname === item.to ||
          pathname.startsWith(`${item.to}/`) ||
          (item.to === "/cases" && pathname.startsWith("/deals/cases"));
        return (
          <NavLink key={item.to} to={item.to} className={navItem(active)}>
            <NavIcon icon={item.icon} active={active} />
            {item.label}
            {item.to === "/work" && <NavCount value={work?.waiting.length} active={active} />}
          </NavLink>
        );
      })}
    </nav>
  );
  return (
    <div className="flex min-h-screen">
      {!client && <SidebarFrame current={monitoringSide ? "monitoring" : "onboarding"}>{nav}</SidebarFrame>}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className={HEADER}>
          {client && <Brand />}
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            {!client && <LiveState />}
            <WalkthroughToggle />
            <NotificationBell items={bell} />
            <EnvironmentLabel />
            <PersonaMenu />
          </div>
        </header>
        <div className={CONTENT}>
          <main className="w-full max-w-[100rem] flex-1">
            <Outlet />
          </main>
          <EnvironmentFooter />
        </div>
      </div>
    </div>
  );
}
