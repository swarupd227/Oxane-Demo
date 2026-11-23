/* The shell for My work, clients, new cases, live facilities and the client portal. */
import clsx from "clsx";
import { Building2, FolderKanban, Landmark, ListTodo, Settings, type LucideIcon } from "lucide-react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { useDealsStatus, useWork } from "../../lib/deals";
import { MONITORING_ROLES, ONBOARDING_ROLES, usePersona, type Role } from "../../lib/persona";
import { WorkbenchSwitch } from "../../monitoring/parts";
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
  { to: "/work", label: "My work", icon: ListTodo, roles: ["onboarding_analyst", "expert", "qc", "reviewer", "monitoring_analyst", "head", "admin"] },
  { to: "/cases", label: "Onboarding cases", icon: FolderKanban, roles: ONBOARDING_ROLES },
  { to: "/facilities", label: "Facilities", icon: Landmark, roles: MONITORING_ROLES },
  { to: "/clients", label: "Clients", icon: Building2, roles: ["admin", "onboarding_analyst", "reviewer", "head"] },
  { to: "/settings/ai-provider", label: "Settings", icon: Settings, roles: ["admin"] },
];

export function visibleNav(role: Role | undefined): NavItem[] {
  return NAV.filter((item) => role && item.roles.includes(role));
}

function LiveState() {
  const { data } = useDealsStatus();
  const { accessCode } = usePersona();
  if (!data) {
    return null;
  }
  let text = data.mode === "live" ? "Live AI" : data.mode === "stub" ? "Test model" : "Recorded AI";
  let tone = "border-line text-muted";
  if (!data.access_configured) {
    text = "Uploads off";
  } else if (data.cap_reached) {
    text = "Daily AI limit reached";
    tone = "border-danger/40 bg-danger-tint text-danger";
  } else if (!accessCode) {
    text = "Access code needed";
    tone = "border-warn/40 bg-warn-tint text-warn";
  }
  return (
    <span role="status" title={`US$${data.spent_today_usd.toFixed(2)} of US$${data.cap_usd.toFixed(2)} live spend today`} className={clsx("inline-flex h-6 items-center rounded border px-1.5 text-[0.6875rem] font-semibold", tone)}>
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
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-line bg-surface px-4">
        <div className="flex shrink-0 items-center gap-2 pr-1">
          <span aria-hidden className="size-5 rounded-[5px] bg-ink">
            <span className="ml-[5px] block h-full w-[5px] bg-accent" />
          </span>
          <span className="text-sm font-semibold tracking-tight">Oxane</span>
        </div>
        {role !== "client" && <WorkbenchSwitch current={monitoringSide ? "monitoring" : "onboarding"} />}
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          {role !== "client" && <LiveState />}
          <WalkthroughToggle />
          <NotificationBell items={bell} />
          <EnvironmentLabel />
          <PersonaMenu />
        </div>
      </header>
      <div className="flex flex-1">
        {role !== "client" && (
          <aside className="sticky top-12 hidden h-[calc(100vh-3rem)] w-56 shrink-0 flex-col overflow-y-auto border-r border-line bg-surface px-2 py-3 lg:flex">
            <nav aria-label="Workspace" className="space-y-0.5">
              {visibleNav(role).map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    clsx(
                      "flex h-8 items-center gap-2 rounded-md px-2 text-[0.8125rem] whitespace-nowrap",
                      isActive || pathname.startsWith(`${item.to}/`) || (item.to === "/cases" && pathname.startsWith("/deals/cases"))
                        ? "bg-sand font-semibold text-ink"
                        : "text-muted hover:bg-sand/60 hover:text-ink",
                    )
                  }
                >
                  <item.icon aria-hidden className="size-4 shrink-0" />
                  {item.label}
                  {item.to === "/work" && work && work.waiting.length > 0 && (
                    <span className="numeric ml-auto rounded bg-sand px-1.5 text-[0.6875rem] font-medium text-muted">{work.waiting.length}</span>
                  )}
                </NavLink>
              ))}
            </nav>
          </aside>
        )}
        <div className="flex min-w-0 flex-1 flex-col px-6 pt-4">
          <main className="w-full max-w-[100rem] flex-1">
            <Outlet />
          </main>
          <EnvironmentFooter />
        </div>
      </div>
    </div>
  );
}
