import { useEffect, useRef } from "react";

function isBusy(target: EventTarget | null): boolean {
  const typing =
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
  return typing || document.querySelector("[role=dialog]") !== null;
}

/** Single-key shortcuts for a screen. Ignored while typing or while a dialog is open. */
export function useKeys(bindings: Record<string, () => void>) {
  const latest = useRef(bindings);
  latest.current = bindings;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || isBusy(event.target)) {
        return;
      }
      const action = latest.current[event.key.toLowerCase()];
      if (action) {
        event.preventDefault();
        action();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
