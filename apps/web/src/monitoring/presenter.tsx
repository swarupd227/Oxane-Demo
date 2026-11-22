/* Presenter mode: the guided walkthrough (numbered steps, next-step buttons, short notes).
 * Off by default. On from the header toggle, Alt+P or ?presenter=1, and remembered per browser. */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

const KEY = "oxane.presenter";

function initial(): boolean {
  try {
    const param = new URLSearchParams(window.location.search).get("presenter");
    if (param === "1" || param === "0") {
      localStorage.setItem(KEY, param);
      return param === "1";
    }
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

const PresenterContext = createContext<{ on: boolean; toggle: () => void }>({ on: false, toggle: () => undefined });

export function PresenterProvider({ children }: { children: ReactNode }) {
  const [on, setOn] = useState(initial);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, on ? "1" : "0");
    } catch {
      // Storage blocked: the setting lasts for this page load only.
    }
  }, [on]);
  const toggle = useCallback(() => setOn((value) => !value), []);
  return <PresenterContext.Provider value={{ on, toggle }}>{children}</PresenterContext.Provider>;
}

export function usePresenter() {
  return useContext(PresenterContext);
}
