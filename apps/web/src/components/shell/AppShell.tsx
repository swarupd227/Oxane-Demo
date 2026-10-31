import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { usePresenterMode } from "../../lib/presenter";
import { sceneForPath, scenes } from "../../lib/scenes";
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
      <AnimatePresence mode="wait" initial={false}>
        <motion.main
          key={pathname}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12, ease: "easeOut" }}
          className="mx-auto w-full max-w-[88rem] flex-1 px-6 py-8"
        >
          <Outlet />
        </motion.main>
      </AnimatePresence>
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        presenter={presenter.enabled}
        onTogglePresenter={presenter.toggle}
      />
    </div>
  );
}
