import clsx from "clsx";
import { motion } from "motion/react";
import { NavLink, useLocation } from "react-router-dom";
import { scenes } from "../../lib/scenes";
import { termStatus, useSession } from "../../lib/session";
import { useWorkbench } from "../../lib/workbench";

function useCounts(): Record<string, string> {
  const { data } = useWorkbench();
  const { state } = useSession();
  if (!data || !state.intakeDone) {
    return {};
  }
  const approved = data.terms.filter((term) => termStatus(term, state) === "approved").length;
  const items = [...data.exceptions, ...state.heldItems];
  const open = items.filter((item) => !state.exceptions[item.id]).length;
  return {
    "/terms": `${approved}/${data.terms.length}`,
    "/exceptions": open ? `${open} open` : "Done",
  };
}

export function Stepper() {
  const { pathname } = useLocation();
  const counts = useCounts();

  return (
    <nav aria-label="Onboarding steps" className="border-b border-line bg-surface px-6">
      <ol className="flex items-stretch gap-1">
        {scenes.map((scene, index) => {
          const active = scene.path === pathname;
          return (
            <li key={scene.path} className="relative flex-auto">
              <NavLink
                to={scene.path}
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
                  {index + 1}
                </span>
                <span className="truncate">{scene.label}</span>
                {counts[scene.path] && (
                  <span className="numeric rounded-full bg-sand px-1.5 text-[0.6875rem] font-medium text-muted">
                    {counts[scene.path]}
                  </span>
                )}
              </NavLink>
              {active && (
                <motion.span
                  layoutId="stepper-active"
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
