/* Who is acting. One persona model for both workbenches: the choice is kept in this browser and
 * sent with every API request as X-Acting-User. The API looks up the role and enforces it; this
 * file only decides what to show. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type Role =
  | "onboarding_analyst"
  | "expert"
  | "qc"
  | "reviewer"
  | "monitoring_analyst"
  | "head"
  | "client"
  | "admin";

export interface Persona {
  id: string;
  name: string;
  role: Role;
  title: string;
  client: string | null;
  role_label: string;
}

const PERSONA_KEY = "oxane.persona";
const ACCESS_KEY = "oxane.access-code";
const DEFAULT_PERSONA = "hannah";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) {
      window.localStorage.removeItem(key);
    } else {
      window.localStorage.setItem(key, value);
    }
  } catch {
    /* Private windows may refuse storage; the choice then lasts for this page only. */
  }
}

// Nobody chosen yet: start as the person who works the screen being opened.
function firstPersona(): string {
  const path = window.location.pathname;
  if (path.startsWith("/monitoring") || path.startsWith("/facilities")) {
    return "priya";
  }
  return path.startsWith("/clients") ? "alex" : DEFAULT_PERSONA;
}
// Nobody chosen yet: start as the person who works the screen being opened, and remember it, so
// moving to another area (My work, the cases list) keeps the same person.
let actingId = (typeof window !== "undefined" && read(PERSONA_KEY)) || "";
if (!actingId) {
  actingId = typeof window !== "undefined" ? firstPersona() : DEFAULT_PERSONA;
  if (typeof window !== "undefined") {
    write(PERSONA_KEY, actingId);
  }
}
let accessCode = (typeof window !== "undefined" && read(ACCESS_KEY)) || "";

/** Every /api request carries the acting user and, once entered, the demo access code. */
function installHeaders() {
  if (typeof window === "undefined" || (window.fetch as { oxane?: boolean }).oxane) {
    return;
  }
  const original = window.fetch.bind(window);
  const wrapped = (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    if (url.startsWith("/api") || url.includes("/api/")) {
      const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
      headers.set("X-Acting-User", actingId);
      if (accessCode) {
        headers.set("X-Demo-Access-Code", accessCode);
      }
      return original(input, { ...init, headers });
    }
    return original(input, init);
  };
  (wrapped as unknown as { oxane: boolean }).oxane = true;
  window.fetch = wrapped as typeof window.fetch;
}
installHeaders();

/** Which workbench areas each role uses. */
export const ONBOARDING_ROLES: Role[] = ["onboarding_analyst", "expert", "qc", "reviewer", "admin"];
export const MONITORING_ROLES: Role[] = ["monitoring_analyst", "head", "reviewer", "expert", "qc", "admin"];

/** Who gets each global navigation item. Every shell reads this, so they never disagree. */
export const NAV_ROLES: Record<"/work" | "/cases" | "/facilities" | "/clients" | "/settings/ai-provider", Role[]> = {
  "/work": ["onboarding_analyst", "expert", "qc", "reviewer", "monitoring_analyst", "head", "admin"],
  "/cases": ONBOARDING_ROLES,
  "/facilities": MONITORING_ROLES,
  "/clients": ["admin", "onboarding_analyst", "reviewer", "head"],
  "/settings/ai-provider": ["admin"],
};

/** The scripted scenarios' own session actors, worked out from the persona. */
export function onboardingActor(role: Role | undefined): "analyst" | "approver" {
  return role === "reviewer" ? "approver" : "analyst";
}
export function cycleActor(role: Role | undefined): "analyst" | "approver" | "senior" | "client" {
  if (role === "reviewer") {
    return "approver";
  }
  if (role === "head") {
    return "senior";
  }
  return role === "client" ? "client" : "analyst";
}
export const PERSONA_FOR_ACTOR: Record<string, string> = {
  analyst: "hannah",
  approver: "marcus",
  senior: "elena",
  client: "james",
  monitoring: "priya",
};

interface PersonaContextValue {
  personas: Persona[];
  persona: Persona | null;
  setPersona: (id: string) => void;
  accessCode: string;
  setAccessCode: (code: string) => void;
}

const PersonaContext = createContext<PersonaContextValue>({
  personas: [],
  persona: null,
  setPersona: () => undefined,
  accessCode: "",
  setAccessCode: () => undefined,
});

export function PersonaProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [current, setCurrent] = useState(actingId);
  const [code, setCode] = useState(accessCode);
  const { data } = useQuery({
    queryKey: ["personas"],
    queryFn: async (): Promise<{ personas: Persona[] }> => (await fetch("/api/personas")).json(),
    staleTime: 60_000,
  });
  const setPersona = useCallback(
    (id: string) => {
      actingId = id;
      write(PERSONA_KEY, id);
      setCurrent(id);
      // Everything on screen was fetched as someone else.
      void client.invalidateQueries();
    },
    [client],
  );
  const setAccessCode = useCallback(
    (value: string) => {
      accessCode = value.trim();
      write(ACCESS_KEY, accessCode || null);
      setCode(accessCode);
      void client.invalidateQueries({ queryKey: ["deals-status"] });
    },
    [client],
  );
  const value = useMemo(() => {
    const personas = data?.personas ?? [];
    return {
      personas,
      persona: personas.find((p) => p.id === current) ?? null,
      setPersona,
      accessCode: code,
      setAccessCode,
    };
  }, [data, current, setPersona, code, setAccessCode]);
  return <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>;
}

export function usePersona() {
  return useContext(PersonaContext);
}

export function useRole(): Role | undefined {
  return usePersona().persona?.role;
}

/** The persona to switch to for a role, for presenter-mode hints. */
export function personaFor(personas: Persona[], role: string, client?: string | null): Persona | undefined {
  return personas.find((p) => p.role === role && (!client || p.client === client));
}
