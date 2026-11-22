import clsx from "clsx";
import {
  ArrowLeft,
  ArrowRight,
  Bell,
  BellRing,
  Building2,
  CalendarRange,
  ChevronDown,
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
  ShieldCheck,
  TableProperties,
  Car,
} from "lucide-react";
import { DropdownMenu, Popover } from "radix-ui";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Skeleton } from "../components/ui/layout";
import { Tooltip } from "../components/ui/Tooltip";
import { ActorContext, useActor, useCycle, useCycleAction, useCycleReset, useCycleSession, type CycleActor } from "./cycle";
import { deskRows, notices, ScopeContext, useScope, type ClientScope } from "./desk";
import { WorkbenchSwitch } from "./parts";
import { PresenterProvider, usePresenter } from "./presenter";
import { Avatar, RecordId, when } from "./ui";

/** The screens in the order a cycle is worked. Presenter mode walks them in this order. */
export const STEPS = [
  { path: "/monitoring", label: "Portfolio", icon: LayoutGrid, hint: "Whole book for the cycle. Four facilities carry this month's issues; the rest are routine." },
  { path: "/monitoring/submissions", label: "Submissions", icon: Inbox, hint: "Northmoor's servicer report is overdue and already escalated. Bramble's dealer list reused under consent." },
  { path: "/monitoring/mapping", label: "Mapping", icon: TableProperties, hint: "Stored mapping reused; only Bramble's two new columns needed a suggestion. Confirm it." },
  { path: "/monitoring/validation", label: "Validation", icon: ShieldCheck, hint: "Northmoor's duplicate row blocks the load. Record the resolution to release it." },
  { path: "/monitoring/reconciliation", label: "Reconciliation", icon: Scale, hint: "Bramble roll-forward gap traced to 27 loans; charge-offs differ on 9." },
  { path: "/monitoring/terms", label: "Terms", icon: CalendarRange, hint: "Switch to June: Amendment No. 2 changes the dealer limit." },
  { path: "/monitoring/covenants", label: "Covenants", icon: Gauge, hint: "Run the June what-if on Northmoor. Larkspur CCC excess at market value." },
  { path: "/monitoring/collateral", label: "Collateral", icon: Car, hint: "One VIN in both Bramble and Northmoor. Open both rows." },
  { path: "/monitoring/triage", label: "Exceptions", icon: ListChecks, hint: "Accept or change each suggestion; a change needs a reason." },
  { path: "/monitoring/pack", label: "Reports", icon: FileText, hint: "Resolve the QC variance, then switch user to approve. Thornbury needs three levels." },
  { path: "/monitoring/monitor", label: "Alerts", icon: BellRing, hint: "Headroom across the book. Pick a client request to draft an alert rule." },
  { path: "/monitoring/status-call", label: "Status calls", icon: MessagesSquare, hint: "Weekly brief per client contact. Thornbury's is a code template." },
  { path: "/monitoring/results", label: "Metrics", icon: ClipboardCheck, hint: "Measured against assumed, with the test-set results." },
];

const ACTORS: CycleActor[] = ["analyst", "approver", "senior", "client"];

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
}

function Sidebar() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
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
      "/monitoring/triage": { n: open, tone: "bg-ink text-white" },
      "/monitoring/pack": { n: cycle.facilities.length - released, tone: "bg-sand text-muted" },
    } as Record<string, { n: number; tone: string }>;
  }, [cycle, session]);
  return (
    <aside className="sticky top-0 flex h-screen w-52 shrink-0 flex-col border-r border-line bg-surface">
      <div className="flex h-12 items-center gap-2 border-b border-line px-3">
        <span aria-hidden className="size-5 rounded-[5px] bg-ink">
          <span className="ml-[5px] block h-full w-[5px] bg-accent" />
        </span>
        <span className="text-sm font-semibold tracking-tight">Oxane</span>
      </div>
      <div className="border-b border-line px-3 py-2 [&_nav]:w-full [&_nav>a]:flex-1 [&_nav>a]:justify-center">
        <WorkbenchSwitch current="monitoring" />
      </div>
      <nav aria-label="Monitoring" className="flex-1 overflow-y-auto px-2 py-2">
        <ul className="space-y-0.5">
          {STEPS.map((step) => {
            const Icon = step.icon;
            const count = counts[step.path];
            return (
              <li key={step.path}>
                <NavLink
                  to={step.path}
                  end
                  className={({ isActive }) =>
                    clsx(
                      "flex h-8 items-center gap-2 rounded-md px-2 text-[0.8125rem]",
                      isActive ? "bg-sand font-semibold text-ink" : "text-muted hover:bg-canvas hover:text-ink",
                    )
                  }
                >
                  <Icon aria-hidden className="size-4 shrink-0" />
                  <span className="truncate">{step.label}</span>
                  {count && count.n > 0 && <span className={clsx("numeric ml-auto rounded-full px-1.5 text-[0.6875rem] leading-4 font-semibold", count.tone)}>{count.n}</span>}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
      {cycle && (
        <div className="border-t border-line px-3 py-2 text-[0.6875rem] text-muted">
          <p className="font-medium text-ink">{cycle.desk}</p>
          <p>Cycle {cycle.cycle.id}</p>
        </div>
      )}
    </aside>
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
  const items = cycle ? notices(cycle, session, actor) : [];
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

function UserMenu({ onReset }: { onReset: () => void }) {
  const { data: cycle } = useCycle();
  const { actor, setActor } = useActor();
  const { on } = usePresenter();
  const me = cycle?.team?.[actor] ?? { name: actor, title: "" };
  return (
    <Menu
      label="User menu"
      width="w-64"
      trigger={
        <button type="button" className="flex h-8 cursor-pointer items-center gap-2 rounded-md px-1.5 hover:bg-sand" data-testid="user-menu">
          <Avatar name={me.name} size="md" />
          <span className="hidden text-left leading-tight xl:block">
            <span className="block text-xs font-semibold">{me.name}</span>
            <span className="block text-[0.6875rem] text-muted">{me.title}</span>
          </span>
          <ChevronDown aria-hidden className="size-3.5 text-muted" />
        </button>
      }
    >
      <DropdownMenu.Label className="px-2 py-1 text-xs font-semibold text-muted">Switch user</DropdownMenu.Label>
      <DropdownMenu.RadioGroup value={actor} onValueChange={(v) => setActor(v as CycleActor)}>
        {ACTORS.map((id) => {
          const person = cycle?.team?.[id] ?? { name: id, title: "" };
          return (
            <DropdownMenu.RadioItem key={id} value={id} className={clsx(itemClass, "items-center")}>
              <Avatar name={person.name} />
              <span className="min-w-0 flex-1">
                <span className="block truncate">{person.name}</span>
                <span className="block truncate text-[0.6875rem] text-muted">{person.title}</span>
              </span>
              <DropdownMenu.ItemIndicator className="text-xs font-semibold">✓</DropdownMenu.ItemIndicator>
            </DropdownMenu.RadioItem>
          );
        })}
      </DropdownMenu.RadioGroup>
      {on && (
        <>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <DropdownMenu.Item className={clsx(itemClass, "items-center")} onSelect={onReset}>
            <RotateCw aria-hidden className="size-3.5" />
            Reset session
          </DropdownMenu.Item>
        </>
      )}
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
    <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-line bg-surface px-4">
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
            <option disabled>Apr 2026 · closed</option>
            <option disabled>Mar 2026 · closed</option>
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
            className={clsx("grid size-8 cursor-pointer place-items-center rounded-md", presenter.on ? "bg-accent text-ink" : "text-muted hover:bg-sand hover:text-ink")}
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
        <UserMenu onReset={onReset} />
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
      <p className="min-w-0 flex-1 truncate text-ink">{STEPS[index].hint}</p>
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
  const { setActor } = useActor();
  const { data: session } = useCycleSession();
  const action = useCycleAction();
  const reset = useCycleReset();
  useEffect(() => {
    const page = STEPS.find((s) => s.path === pathname);
    document.title = `${page?.label ?? "Monitoring"} · Monitoring · Oxane`;
  }, [pathname]);
  const doReset = () => {
    reset.mutate();
    setActor("analyst");
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
        setActor("analyst");
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
  }, [navigate, presenter, reset, setActor]);

  return (
    <div className="flex min-h-screen bg-canvas">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onReset={doReset} />
        {presenter.on && <PresenterBar />}
        <main key={pathname} className="w-full min-w-0 flex-1 px-4 py-3">
          <Outlet />
        </main>
        <footer className="flex items-center gap-1.5 border-t border-line px-4 py-1.5 text-[0.6875rem] text-muted">
          <FileInput aria-hidden className="size-3" />
          Synthetic data. Not connected to Panorama or client systems.
        </footer>
      </div>
    </div>
  );
}

export function MonitoringShell() {
  const [actor, setActor] = useState<CycleActor>("analyst");
  const [client, setClient] = useState<ClientScope>("all");
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
