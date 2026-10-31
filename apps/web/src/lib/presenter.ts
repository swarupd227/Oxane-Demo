import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "workbench.presenter";

function readStored(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function usePresenterMode() {
  const [enabled, setEnabled] = useState(readStored);

  useEffect(() => {
    document.documentElement.dataset.presenter = String(enabled);
    try {
      localStorage.setItem(STORAGE_KEY, String(enabled));
    } catch {
      // The setting only lasts for this page load if storage is blocked.
    }
  }, [enabled]);

  const toggle = useCallback(() => setEnabled((value) => !value), []);
  return { enabled, toggle };
}
