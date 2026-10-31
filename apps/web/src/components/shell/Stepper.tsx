import clsx from "clsx";
import { motion } from "motion/react";
import { NavLink, useLocation } from "react-router-dom";
import { scenes } from "../../lib/scenes";

export function Stepper() {
  const { pathname } = useLocation();

  return (
    <nav aria-label="Onboarding steps" className="border-b border-line bg-surface px-6">
      <ol className="flex items-stretch gap-1">
        {scenes.map((scene) => {
          const active = scene.path === pathname;
          return (
            <li key={scene.path} className="relative min-w-0 flex-1">
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
                  {scene.number}
                </span>
                <span className="truncate">{scene.label}</span>
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
