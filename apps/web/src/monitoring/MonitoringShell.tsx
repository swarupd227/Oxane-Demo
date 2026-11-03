import clsx from "clsx";
import { CalendarClock, FlaskConical, Radio, Rewind, RotateCw } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Skeleton } from "../components/ui/layout";
import { Tooltip } from "../components/ui/Tooltip";
import { formatDate } from "../lib/format";
import { usePresenterMode } from "../lib/presenter";
import { ActorContext, useCycle, useCycleAction, useCycleReset, useCycleSession, type CycleActor } from "./cycle";
import { WorkbenchSwitch } from "./parts";

export const STEPS = [
  { path: "/monitoring", label: "Portfolio" },
  { path: "/monitoring/submissions", label: "Submissions" },
  { path: "/monitoring/reconciliation", label: "Reconcile" },
  { path: "/monitoring/terms", label: "Terms" },
  { path: "/monitoring/covenants", label: "Covenants" },
  { path: "/monitoring/collateral", label: "Collateral" },
  { path: "/monitoring/triage", label: "Triage" },
  { path: "/monitoring/pack", label: "Lender pack" },
  { path: "/monitoring/results", label: "Scorecard" },
];

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
}

function CycleBar() {
  const { data, isPending, isError, refetch } = useCycle();
  const modeIcon = data?.llm_mode === "replay" ? Rewind : Radio;
  const Icon = modeIcon;
  return (
    <div className="flex h-16 items-center gap-6 border-b border-line bg-surface px-6">
      <div className="flex shrink-0 items-center gap-2.5 pr-2">
        <span aria-hidden className="size-5 rounded-[5px] bg-ink">
          <span className="ml-[5px] block h-full w-[5px] bg-accent" />
        </span>
        <span className="text-sm font-semibold tracking-tight">Monitoring Workbench</span>
      </div>
      <WorkbenchSwitch current="monitoring" />
      <div className="flex min-w-0 flex-1 items-center gap-4 border-l border-line pl-6">
        {data && (
          <>
            <div className="min-w-0">
              <p className="truncate text-[0.9375rem] leading-tight font-semibold">
                {data.lender} <span className="font-normal text-muted">· {data.desk}</span>
              </p>
              <p className="numeric mt-0.5 truncate text-[0.8125rem] leading-tight text-muted">
                {data.cycle.label} cycle
                <span aria-hidden className="mx-1.5 text-stone">|</span>
                {data.facilities.length} facilities
                <span aria-hidden className="mx-1.5 text-stone">|</span>
                Period end {formatDate(data.cycle.period_end)}
              </p>
            </div>
            <Tooltip content="The demo runs on a fixed date, so the late file and its chase are always the same.">
              <span tabIndex={0} className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full bg-warn-tint px-3 text-[0.8125rem] font-medium text-warn">
                <CalendarClock aria-hidden className="size-3.5" />
                As of {formatDate(data.cycle.as_of)}
              </span>
            </Tooltip>
          </>
        )}
        {isPending && (
          <div className="space-y-1.5" role="status" aria-label="Loading cycle">
            <Skeleton className="h-4 w-72" />
            <Skeleton className="h-3.5 w-56" />
          </div>
        )}
        {isError && (
          <div role="alert" className="flex items-center gap-3 text-sm">
            <span className="text-danger">The monitoring cycle could not be loaded.</span>
            <Button variant="secondary" size="sm" onClick={() => void refetch()}>
              <RotateCw aria-hidden className="size-3.5" />
              Retry
            </Button>
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Tooltip content="Sandbox environment. All documents and data are synthetic. Not connected to Panorama.">
          <span tabIndex={0} className="inline-flex h-7 items-center gap-1.5 rounded-md bg-ink px-2.5 text-xs font-medium text-white">
            <FlaskConical aria-hidden className="size-3.5 text-accent" />
            Sandbox
          </span>
        </Tooltip>
        {data && (
          <Tooltip content={data.llm_mode === "replay" ? "Results are from a recorded run. No model calls are being made." : "The model is being called."}>
            <span tabIndex={0} className="inline-flex h-7 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 text-xs font-medium text-muted">
              <Icon aria-hidden className="size-3.5" />
              {data.llm_mode === "replay" ? "Recorded run" : "Live"}
            </span>
          </Tooltip>
        )}
      </div>
    </div>
  );
}

function CycleStepper() {
  const { pathname } = useLocation();
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const counts = useMemo(() => {
    if (!cycle || !session) {
      return {} as Record<string, string>;
    }
    const open = cycle.findings.filter((f) => !session.decisions[f.id]).length;
    const approved = Object.keys(session.packs).length;
    const late = cycle.submissions.filter((s) => s.status === "late").length;
    return {
      "/monitoring/submissions": late ? `${late} late` : "",
      "/monitoring/triage": open ? `${open} to decide` : "Done",
      "/monitoring/pack": `${approved}/${cycle.facilities.length}`,
    } as Record<string, string>;
  }, [cycle, session]);
  return (
    <nav aria-label="Monitoring steps" className="border-b border-line bg-surface px-6">
      <ol className="flex items-stretch gap-1">
        {STEPS.map((step, index) => {
          const active = step.path === pathname;
          return (
            <li key={step.path} className="relative flex-auto">
              <NavLink
                to={step.path}
                end
                aria-current={active ? "step" : undefined}
                className={clsx(
                  "flex h-12 items-center gap-2 rounded-md px-2 text-sm whitespace-nowrap transition-colors duration-100",
                  active ? "font-semibold text-ink" : "text-muted hover:text-ink",
                )}
              >
                <span
                  aria-hidden
                  className={clsx(
                    "numeric flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                    active ? "bg-ink text-white" : "bg-sand text-muted",
                  )}
                >
                  {index}
                </span>
                <span className="truncate">{step.label}</span>
                {counts[step.path] && (
                  <span className="numeric rounded-full bg-sand px-1.5 text-[0.6875rem] font-medium text-muted">{counts[step.path]}</span>
                )}
              </NavLink>
              {active && (
                <motion.span
                  layoutId="monitoring-step"
                  transition={{ type: "spring", stiffness: 500, damping: 40 }}
                  className="absolute inset-x-0 -bottom-px h-[3px] bg-accent"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function MonitoringShell() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [actor, setActor] = useState<CycleActor>("analyst");
  const presenter = usePresenterMode();
  const { data: session } = useCycleSession();
  const action = useCycleAction();
  const reset = useCycleReset();

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
      if (isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) {
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
    <ActorContext.Provider value={{ actor, setActor }}>
      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-30">
          <CycleBar />
          <CycleStepper />
        </header>
        <motion.main
          key={pathname}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.12, ease: "easeOut" }}
          className="mx-auto w-full max-w-[90rem] flex-1 px-6 py-7"
        >
          <Outlet />
        </motion.main>
      </div>
    </ActorContext.Provider>
  );
}
