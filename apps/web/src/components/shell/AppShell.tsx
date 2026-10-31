import { RotateCw } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { usePresenterMode } from "../../lib/presenter";
import { sceneForPath, scenes } from "../../lib/scenes";
import { useWorkbench } from "../../lib/workbench";
import { Button } from "../ui/Button";
import { CommandPalette } from "./CommandPalette";
import { DealBar } from "./DealBar";
import { Stepper } from "./Stepper";

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

export function AppShell() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const presenter = usePresenterMode();
  const workbench = useWorkbench();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
        return;
      }
      if (isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      if (event.key === "[" || event.key === "]") {
        const current = sceneForPath(pathname)?.number ?? 0;
        const next = scenes[current + (event.key === "]" ? 1 : -1)];
        if (next) {
          navigate(next.path);
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, pathname]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30">
        <DealBar onOpenPalette={() => setPaletteOpen(true)} />
        <Stepper />
      </header>
      <motion.main
        key={pathname}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.12, ease: "easeOut" }}
        className="mx-auto w-full max-w-[88rem] flex-1 px-6 py-8"
      >
        {workbench.isError && (
          <div
            role="alert"
            className="mb-4 flex items-center justify-between gap-4 rounded-lg bg-danger-tint px-4 py-3 text-sm"
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
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        presenter={presenter.enabled}
        onTogglePresenter={presenter.toggle}
      />
    </div>
  );
}
