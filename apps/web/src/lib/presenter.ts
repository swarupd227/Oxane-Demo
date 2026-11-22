import { useCallback, useEffect, useSyncExternalStore } from "react";

/*
 * Walkthrough mode: the numbered steps, [ and ] navigation, next-step buttons and keyboard
 * hints. Off by default; on from the header toggle or ?presenter=1, and remembered in this
 * browser. Onboarding and Monitoring share the key, so the setting follows across both.
 */
export const PRESENTER_KEY = "oxane.presenter";

const listeners = new Set<() => void>();

function fromUrl(): boolean | null {
  try {
    const value = new URLSearchParams(window.location.search).get("presenter");
    return value === null ? null : value === "1" || value === "true";
  } catch {
    return null;
  }
}

function stored(): boolean {
  try {
    return localStorage.getItem(PRESENTER_KEY) === "1";
  } catch {
    return false;
  }
}

function persist(value: boolean) {
  try {
    if (value) {
      localStorage.setItem(PRESENTER_KEY, "1");
    } else {
      localStorage.removeItem(PRESENTER_KEY);
    }
  } catch {
    // Without storage the setting lasts for this page load only.
  }
}

let current = (() => {
  if (typeof window === "undefined") {
    return false;
  }
  const requested = fromUrl();
  if (requested !== null) {
    persist(requested);
    return requested;
  }
  return stored();
})();

export function setPresenter(value: boolean) {
  current = value;
  persist(value);
  if (typeof document !== "undefined") {
    document.documentElement.dataset.walkthrough = String(value);
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function usePresenterMode() {
  const enabled = useSyncExternalStore(subscribe, () => current, () => false);
  useEffect(() => {
    document.documentElement.dataset.walkthrough = String(enabled);
  }, [enabled]);
  const toggle = useCallback(() => setPresenter(!current), []);
  return { enabled, toggle, set: setPresenter };
}

const LARGE_TEXT_KEY = "workbench.presenter";
const largeListeners = new Set<() => void>();

let largeText = (() => {
  try {
    return localStorage.getItem(LARGE_TEXT_KEY) === "true";
  } catch {
    return false;
  }
})();

function setLargeText(value: boolean) {
  largeText = value;
  try {
    localStorage.setItem(LARGE_TEXT_KEY, String(value));
  } catch {
    // The setting only lasts for this page load if storage is blocked.
  }
  largeListeners.forEach((listener) => listener());
}

function subscribeLarge(listener: () => void) {
  largeListeners.add(listener);
  return () => largeListeners.delete(listener);
}

/** Larger type for a projector. All sizing is in rem, so the root size scales everything. */
export function useLargeText() {
  const enabled = useSyncExternalStore(subscribeLarge, () => largeText, () => false);
  useEffect(() => {
    document.documentElement.dataset.presenter = String(enabled);
  }, [enabled]);
  const toggle = useCallback(() => setLargeText(!largeText), []);
  return { enabled, toggle };
}
