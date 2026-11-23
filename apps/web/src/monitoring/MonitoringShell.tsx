import clsx from "clsx";
import {
  ArrowLeft,
  ArrowRight,
  Bell,
  BellRing,
  Bot,
  Building2,
  CalendarRange,
  ClipboardCheck,
  FileInput,
  FileText,
  Gauge,
  Inbox,
  LayoutGrid,
  ListChecks,
  MessagesSquare,
  Presentation,
  RotateCw,
  Scale,
  Search,
  Settings,
  ShieldCheck,
  TableProperties,
  Car,
  Landmark,
  ListTodo,
  type LucideIcon,
} from "lucide-react";
import { DropdownMenu, Popover } from "radix-ui";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { PersonaMenu, useWorkBell } from "../components/shell/Persona";
import { cycleActor, MONITORING_ROLES, PERSONA_FOR_ACTOR, usePersona } from "../lib/persona";
import { Button } from "../components/ui/Button";
import { Skeleton } from "../components/ui/layout";
import { Tooltip } from "../components/ui/Tooltip";
import { ActorContext, useActor, useCycle, useCycleAction, useCycleReset, useCycleSession, type CycleActor } from "./cycle";
import { deskRows, notices, ScopeContext, useScope, type ClientScope } from "./desk";
import { HEADER, NavCount, NavIcon, NavSection, navItem, SidebarFrame } from "../components/shell/frame";
import { PresenterProvider, usePresenter } from "./presenter";
import { RecordId, when } from "./ui";
import { HINTS } from "./walkthrough";

/** The screens in the order a cycle is worked. Presenter mode walks them in this order. */
export const STEPS = [
  { path: "/monitoring", label: "Portfolio", icon: LayoutGrid },
  { path: "/monitoring/submissions", label: "Submissions", icon: Inbox },
  { path: "/monitoring/mapping", label: "Mapping", icon: TableProperties },
  { path: "/monitoring/validation", label: "Validation", icon: ShieldCheck },
  { path: "/monitoring/reconciliation", label: "Reconciliation", icon: Scale },
  { path: "/monitoring/terms", label: "Terms", icon: CalendarRange },
  { path: "/monitoring/covenants", label: "Covenants", icon: Gauge },
  { path: "/monitoring/collateral", label: "Collateral", icon: Car },
  { path: "/monitoring/triage", label: "Exceptions", icon: ListChecks },
  { path: "/monitoring/pack", label: "Reports", icon: FileText },
  { path: "/monitoring/monitor", label: "Alerts", icon: BellRing },
  { path: "/monitoring/status-call", label: "Status calls", icon: MessagesSquare },
  { path: "/monitoring/results", label: "Metrics", icon: ClipboardCheck },
];

const monthFmt = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });

/** The closed cycles before this one, newest first, worked out from its period end. */
export function priorPeriods(periodEnd: string, count: number): string[] {
  const end = new Date(`${periodEnd.slice(0, 10)}T00:00:00Z`);
  return Array.from({ length: count }, (_, i) =>
    monthFmt.format(new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - 1 - i, 1))),
  );
}

/* The sidebar groups the cycle's screens by the stage of the monitoring workflow. */
const NAV_GROUPS = [
  { label: "Overview", paths: ["/monitoring"] },
  { label: "Ingest", paths: ["/monitoring/submissions", "/monitoring/mapping", "/monitoring/validation", "/monitoring/reconciliation"] },
  { label: "Test", paths: ["/monitoring/terms", "/monitoring/covenants", "/monitoring/collateral"] },
  { label: "Resolve and report", paths: ["/monitoring/triage", "/monitoring/pack", "/monitoring/monitor", "/monitoring/status-call", "/monitoring/results"] },
];
const ALERT_PATHS = ["/monitoring/submissions", "/monitoring/validation"];

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
}

function Sidebar() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const role = usePersona().persona?.role;
  const counts = useMemo(() => {
    if (!cycle) {
      return {} as Record<string, { n: number; tone: string }>;
    }
    const open = cycle.findings.filter((f) => !f.rule_outcome && !session?.decisions[f.id]).length;
    const late = cycle.submissions.filter((s) => s.status === "late").length;
    const held = Object.values(session?.held ?? {}).filter(Boolean).length;
    const released = Object.keys(session?.packs ?? {}).length;
    return {
      "/monitoring/submissions": { n: late, tone: "bg-danger text-white" },
      "/monitoring/validation": { n: held, tone: "bg-danger text-white" },
      "/monitoring/triage": { n: open, tone: "bg-accent text-white" },
      "/monitoring/pack": { n: cycle.facilities.length - released, tone: "bg-sand text-muted" },
    } as Record<string, { n: number; tone: string }>;
  }, [cycle, session]);
  const link = (to: string, label: string, icon: LucideIcon, count?: { n: number; tone: string }, alert?: boolean) => (
    <NavLink key={to} to={to} end className={({ isActive }) => navItem(isActive)}>
      {({ isActive }) => (
        <>
          <NavIcon icon={icon} active={isActive} />
          <span className="truncate">{label}</span>
          <NavCount value={count?.n} active={isActive} alert={alert} />
        </>
      )}
    </NavLink>
  );
  const stepsByGroup = (paths: string[]) => STEPS.filter((step) => paths.includes(step.path));
  return (
    <SidebarFrame
      current="monitoring"
      footer={
        cycle && (
          <div className="px-2.5 py-1 text-[0.6875rem] text-subtle">
            <p className="font-medium text-muted">{cycle.desk}</p>
            <p className="numeric">Cycle {cycle.cycle.id}</p>
          </div>
        )
      }
    >
      <nav aria-label="Monitoring">
        {NAV_GROUPS.map((group) => (
          <NavSection key={group.label} label={group.label}>
            {stepsByGroup(group.paths).map((step) =>
              link(step.path, step.label, step.icon, counts[step.path], ALERT_PATHS.includes(step.path)),
            )}
          </NavSection>
        ))}
        <NavSection label="Workspace">
          {link("/work", "My work", ListTodo)}
          {link("/facilities", "Onboarded facilities", Landmark)}
          {role !== "client" && link("/monitoring/agents", "Agents", Bot)}
          {role === "admin" && link("/settings/ai-provider", "Settings", Settings)}
        </NavSection>
      </nav>
    </SidebarFrame>
  );
}

function Menu({ trigger, children, label, width = "w-80" }: { trigger: ReactNode; children: ReactNode; label: string; width?: string }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild aria-label={label}>
        {trigger}
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className={clsx("z-50 rounded-lg border border-line bg-surface p-1 shadow-overlay", width)}>
          {children}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

const itemClass = "flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-[0.8125rem] outline-none data-[highlighted]:bg-canvas";

function Notifications() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const { actor } = useActor();
  const navigate = useNavigate();
  const handoffs = useWorkBell();
  const items = [...handoffs, ...(cycle ? notices(cycle, session, actor) : [])];
  return (
    <Menu
      label={`Notifications, ${items.length}`}
      width="w-96"
      trigger={
        <button type="button" className="relative grid size-8 cursor-pointer place-items-center rounded-md text-muted hover:bg-sand hover:text-ink">
          <Bell aria-hidden className="size-4" />
          {items.length > 0 && <span className="numeric absolute -top-0.5 -right-0.5 min-w-4 rounded-full bg-danger px-1 text-[0.625rem] leading-4 font-semibold text-white">{items.length}</span>}
        </button>
      }
    >
      <DropdownMenu.Label className="px-2 py-1 text-xs font-semibold text-muted">Notifications</DropdownMenu.Label>
      <div className="max-h-96 overflow-y-auto">
        {items.map((n) => (
          <DropdownMenu.Item key={n.id} className={itemClass} onSelect={() => navigate(n.to)}>
            <span aria-hidden className={clsx("mt-1.5 size-1.5 shrink-0 rounded-full", n.tone === "danger" ? "bg-danger" : n.tone === "warn" ? "bg-warn" : "bg-info")} />
            <span className="min-w-0">
              <span className="block font-medium">{n.title}</span>
              <span className="block truncate text-xs text-muted">{n.detail}</span>
            </span>
          </DropdownMenu.Item>
        ))}
        {!items.length && <p className="px-2 py-3 text-xs text-muted">Nothing new.</p>}
      </div>
    </Menu>
  );
}

function GlobalSearch() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "/" && !isTyping(event.target)) {
        event.preventDefault();
        input.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const results = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!cycle || term.length < 2) {
      return [];
    }
    const has = (...parts: (string | undefined | null)[]) => parts.some((p) => p?.toLowerCase().includes(term));
    const facilities = deskRows(cycle, session)
      .filter((f) => has(f.name, f.id, f.asset_class, f.client_name, f.analyst))
      .slice(0, 6)
      .map((f) => ({ key: `f-${f.id}`, group: "Facilities", ref: f.asset_class, text: f.name, to: `/monitoring?facility=${f.id}` }));
    const findings = cycle.findings
      .filter((f) => has(f.ref, f.title, f.check, f.facility))
      .slice(0, 6)
      .map((f) => ({ key: `x-${f.id}`, group: "Exceptions", ref: f.ref, text: f.title, to: `/monitoring/triage?ref=${f.ref}` }));
    const subs = [...cycle.submissions, ...(cycle.book?.submissions ?? [])]
      .filter((s) => has(s.ref, s.label, s.file))
      .slice(0, 6)
      .map((s) => ({ key: `s-${s.ref}`, group: "Submissions", ref: s.ref, text: `${s.file ?? s.label}`, to: `/monitoring/submissions?q=${s.ref}` }));
    return [...facilities, ...findings, ...subs];
  }, [cycle, session, q]);
  const go = (to: string) => {
    setOpen(false);
    setQ("");
    navigate(to);
  };
  return (
    <Popover.Root open={open && results.length > 0} onOpenChange={setOpen}>
      <Popover.Anchor asChild>
        <label className="relative flex items-center">
          <Search aria-hidden className="pointer-events-none absolute left-2.5 size-3.5 text-muted" />
          <input
            ref={input}
            type="search"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOpen(true);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && results[0]) {
                go(results[0].to);
              }
              if (e.key === "Escape") {
                setOpen(false);
              }
            }}
            aria-label="Search facilities, exceptions and submissions"
            placeholder="Search facilities, exceptions, files"
            className="h-8 w-72 rounded-md border border-line bg-canvas pr-8 pl-8 text-xs placeholder:text-subtle focus:bg-surface"
          />
          <kbd className="pointer-events-none absolute right-2 rounded border border-line px-1 text-[0.625rem] text-muted">/</kbd>
        </label>
      </Popover.Anchor>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          onOpenAutoFocus={(e) => e.preventDefault()}
          className="z-50 w-[28rem] rounded-lg border border-line bg-surface p-1 shadow-overlay"
        >
          {["Facilities", "Exceptions", "Submissions"].map((group) => {
            const list = results.filter((r) => r.group === group);
            return list.length ? (
              <div key={group}>
                <p className="px-2 pt-1.5 pb-0.5 text-[0.6875rem] font-semibold text-muted">{group}</p>
                {list.map((r) => (
                  <button key={r.key} type="button" onClick={() => go(r.to)} className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-left text-[0.8125rem] hover:bg-canvas">
                    <span className="min-w-0 flex-1 truncate">{r.text}</span>
                    <RecordId>{r.ref}</RecordId>
                  </button>
                ))}
              </div>
            ) : null;
          })}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function Header({ onReset }: { onReset: () => void }) {
  const { data: cycle, isPending, isError, refetch } = useCycle();
  const { pathname } = useLocation();
  const { client, setClient } = useScope();
  const presenter = usePresenter();
  const page = STEPS.find((s) => s.path === pathname);
  return (
    <header className={HEADER}>
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-[0.8125rem]">
        <Link to="/monitoring" className="text-muted hover:text-ink">
          Monitoring
        </Link>
        {page && page.path !== "/monitoring" && (
          <>
            <span aria-hidden className="text-stone">/</span>
            <span aria-current="page" className="truncate font-medium">
              {page.label}
            </span>
          </>
        )}
      </nav>
      <div className="ml-2 flex items-center gap-1.5">
        <label className="flex items-center gap-1 rounded-md border border-line bg-surface pl-2 text-xs">
          <Building2 aria-hidden className="size-3.5 text-muted" />
          <select aria-label="Client" value={client} onChange={(e) => setClient(e.target.value as ClientScope)} className="h-7 cursor-pointer rounded-md bg-transparent pr-1 text-xs">
            <option value="all">All clients</option>
            {cycle?.clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 rounded-md border border-line bg-surface pl-2 text-xs">
          <CalendarRange aria-hidden className="size-3.5 text-muted" />
          <select aria-label="Cycle" defaultValue="current" className="h-7 cursor-pointer rounded-md bg-transparent pr-1 text-xs">
            <option value="current">{cycle ? `${cycle.cycle.label} · open` : "Cycle"}</option>
            {cycle &&
              priorPeriods(cycle.cycle.period_end, 2).map((label) => (
                <option key={label} disabled>
                  {label} · closed
                </option>
              ))}
          </select>
        </label>
        {cycle && <span className="hidden text-xs text-muted 2xl:inline">As of {when(cycle.cycle.as_of)}</span>}
      </div>
      {isPending && <Skeleton className="h-4 w-40" />}
      {isError && (
        <Button variant="secondary" size="sm" onClick={() => void refetch()}>
          <RotateCw aria-hidden className="size-3.5" />
          Retry
        </Button>
      )}
      <div className="ml-auto flex items-center gap-1.5">
        <GlobalSearch />
        <Tooltip content={presenter.on ? "Presenter mode on (Alt+P)" : "Presenter mode (Alt+P)"}>
          <button
            type="button"
            aria-pressed={presenter.on}
            aria-label="Presenter mode"
            onClick={presenter.toggle}
            className={clsx("grid size-8 cursor-pointer place-items-center rounded-md", presenter.on ? "bg-accent text-white" : "text-muted hover:bg-sand hover:text-ink")}
          >
            <Presentation aria-hidden className="size-4" />
          </button>
        </Tooltip>
        <Notifications />
        <Tooltip content={cycle?.llm_mode === "replay" ? "User acceptance environment. Model responses replayed." : "User acceptance environment."}>
          <span tabIndex={0} className="inline-flex h-6 items-center rounded border border-warn/40 bg-warn-tint px-1.5 text-[0.6875rem] font-semibold tracking-wide text-warn">
            UAT
          </span>
        </Tooltip>
        <PersonaMenu onReset={onReset} resetLabel="Reset session" />
      </div>
    </header>
  );
}

function PresenterBar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const index = STEPS.findIndex((s) => s.path === pathname);
  if (index < 0) {
    return null;
  }
  const prev = STEPS[index - 1];
  const next = STEPS[index + 1];
  return (
    <div className="flex items-center gap-3 border-b border-accent/60 bg-accent/10 px-4 py-1.5 text-xs">
      <ol className="flex items-center gap-1" aria-label="Walkthrough">
        {STEPS.map((s, i) => (
          <li key={s.path}>
            <Link
              to={s.path}
              aria-current={i === index ? "step" : undefined}
              className={clsx("numeric grid size-5 place-items-center rounded-full text-[0.625rem] font-semibold", i === index ? "bg-ink text-white" : i < index ? "bg-ink/20 text-ink" : "bg-surface text-muted")}
            >
              {i + 1}
            </Link>
          </li>
        ))}
      </ol>
      <p className="min-w-0 flex-1 truncate text-ink">{HINTS[STEPS[index].path]}</p>
      <div className="flex shrink-0 items-center gap-1">
        {prev && (
          <Button size="sm" variant="ghost" onClick={() => navigate(prev.path)}>
            <ArrowLeft aria-hidden className="size-3.5" />
            {prev.label}
          </Button>
        )}
        {next && (
          <Button size="sm" onClick={() => navigate(next.path)}>
            {next.label}
            <ArrowRight aria-hidden className="size-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}

function Frame() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const presenter = usePresenter();
  const { data: session } = useCycleSession();
  const action = useCycleAction();
  const reset = useCycleReset();
  useEffect(() => {
    const page = STEPS.find((s) => s.path === pathname);
    document.title = `${page?.label ?? "Monitoring"} · Monitoring · Oxane`;
  }, [pathname]);
  const doReset = () => {
    reset.mutate();
    navigate("/monitoring");
  };

  // The cycle opens when the analyst first looks at it, which starts the turnaround clock.
  useEffect(() => {
    if (session && !session.openedAt && !action.isPending) {
      action.mutate({ type: "open-cycle", as: "analyst" });
    }
  }, [session, action]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.altKey && event.key.toLowerCase() === "r") {
        event.preventDefault();
        reset.mutate();
        navigate("/monitoring");
        return;
      }
      if (event.altKey && event.key.toLowerCase() === "p") {
        event.preventDefault();
        presenter.toggle();
        return;
      }
      if (!presenter.on || isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      if (event.key === "[" || event.key === "]") {
        const current = STEPS.findIndex((step) => step.path === window.location.pathname);
        const next = STEPS[current + (event.key === "]" ? 1 : -1)];
        if (next) {
          navigate(next.path);
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, presenter, reset]);

  return (
    <div className="flex min-h-screen bg-canvas">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onReset={doReset} />
        {presenter.on && <PresenterBar />}
        <main key={pathname} className="w-full min-w-0 flex-1 px-8 pt-5 pb-6">
          <Outlet />
        </main>
        <footer className="mx-8 flex items-center gap-1.5 border-t border-line pt-3 pb-4 text-[0.6875rem] text-subtle">
          <FileInput aria-hidden className="size-3" />
          Synthetic data. Not connected to Panorama or client systems.
        </footer>
      </div>
    </div>
  );
}

export function MonitoringShell() {
  // The acting persona decides the cycle actor; the API checks it again.
  const { persona, setPersona } = usePersona();
  const actor: CycleActor = cycleActor(persona?.role);
  const setActor = (next: CycleActor) => {
    if (next !== actor) {
      setPersona(next === "analyst" ? PERSONA_FOR_ACTOR.monitoring : PERSONA_FOR_ACTOR[next]);
    }
  };
  const [client, setClient] = useState<ClientScope>("all");
  if (persona?.role === "client") {
    return <Navigate to="/portal" replace />;
  }
  if (persona && !MONITORING_ROLES.includes(persona.role)) {
    return <Navigate to="/work" replace />;
  }
  return (
    <PresenterProvider>
      <ActorContext.Provider value={{ actor, setActor }}>
        <ScopeContext.Provider value={{ client, setClient }}>
          <Frame />
        </ScopeContext.Provider>
      </ActorContext.Provider>
    </PresenterProvider>
  );
}
