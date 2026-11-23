import { RotateCw } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ONBOARDING_ROLES, usePersona } from "../../lib/persona";
import { useLargeText, usePresenterMode } from "../../lib/presenter";
import { scenes } from "../../lib/scenes";
import { useSession } from "../../lib/session";
import { useWorkbench } from "../../lib/workbench";
import { Button } from "../ui/Button";
import { Breadcrumbs } from "./Breadcrumbs";
import { CommandPalette } from "./CommandPalette";
import { DealBar } from "./DealBar";
import { Sidebar } from "./Sidebar";
import { Stepper } from "./Stepper";

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

export function EnvironmentFooter() {
  return (
    <footer className="mt-8 border-t border-line pt-2 pb-3 text-[0.6875rem] text-muted">
      UAT environment · synthetic data only · no client or Oxane data
    </footer>
  );
}

export function AppShell() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const presenter = usePresenterMode();
  const largeText = useLargeText();
  const workbench = useWorkbench();
  const { dispatch, refusal, clearRefusal } = useSession();
  const { persona } = usePersona();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
        return;
      }
      if (event.altKey && event.key.toLowerCase() === "r") {
        event.preventDefault();
        dispatch({ type: "reset" });
        navigate("/");
        return;
      }
      if (event.altKey && event.key.toLowerCase() === "p") {
        event.preventDefault();
        presenter.toggle();
        return;
      }
      if (!presenter.enabled || isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      if (event.key === "[" || event.key === "]") {
        // Read the address itself, so quick presses never act on the step before last.
        const current = scenes.findIndex((scene) => scene.path === window.location.pathname);
        const next = scenes[current + (event.key === "]" ? 1 : -1)];
        if (next) {
          navigate(next.path);
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dispatch, navigate, presenter]);

  if (persona?.role === "client") {
    return <Navigate to="/portal" replace />;
  }
  if (persona && !ONBOARDING_ROLES.includes(persona.role)) {
    return <Navigate to="/work" replace />;
  }
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30">
        <DealBar onOpenPalette={() => setPaletteOpen(true)} />
      </header>
      {presenter.enabled && <Stepper />}
      <div className="flex flex-1">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col px-6 pt-3">
          <Breadcrumbs />
          <motion.main
            key={pathname}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.1, ease: "easeOut" }}
            className="w-full max-w-[100rem] flex-1"
          >
            {refusal && (
              <div
                role="alert"
                className="mb-3 flex items-center justify-between gap-4 rounded-md bg-warn-tint px-3 py-2 text-sm"
              >
                <span className="font-medium text-warn">{refusal}</span>
                <Button variant="secondary" size="sm" onClick={clearRefusal}>
                  Dismiss
                </Button>
              </div>
            )}
            {workbench.isError && (
              <div
                role="alert"
                className="mb-3 flex items-center justify-between gap-4 rounded-md bg-danger-tint px-3 py-2 text-sm"
              >
                <span className="font-medium text-danger">The workbench data could not be loaded.</span>
                <Button variant="secondary" size="sm" onClick={() => void workbench.refetch()}>
                  <RotateCw aria-hidden className="size-3.5" />
                  Try again
                </Button>
              </div>
            )}
            <Outlet />
          </motion.main>
          <EnvironmentFooter />
        </div>
      </div>
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        largeText={largeText.enabled}
        onToggleLargeText={largeText.toggle}
      />
    </div>
  );
}
