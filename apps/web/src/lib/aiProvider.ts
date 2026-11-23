/* Settings › AI provider: the administrator's model key. The API holds the key encrypted and
 * never sends it back; this file keeps only what the form has typed, until it is saved. */
import { useQuery, useQueryClient } from "@tanstack/react-query";

export type Provider = "anthropic" | "foundry";
export type Blocked = "access_code" | "not_admin" | "access_off";

export interface TestResult {
  ok: boolean;
  status: number | null;
  latency_ms: number | null;
  models?: string[];
  model_count?: number;
  error: string | null;
  provider: Provider;
  subject: "typed" | "db" | "env";
  at: string;
}

export interface ProviderView {
  provider: Provider;
  provider_label: string;
  configured: boolean;
  source: "db" | "env" | "none";
  last4: string | null;
  model: string;
  model_override: string | null;
  model_default: string;
  saved_provider: Provider | null;
  saved_key: boolean;
  saved_key_unreadable: boolean;
  env_provider: Provider;
  env_key_set: boolean;
  updated_by: string | null;
  updated_at: string | null;
  last_test: TestResult | null;
  encryption_ready: boolean;
  env_file: { enabled: boolean; writable: boolean };
  providers: { id: Provider; label: string }[];
}

export interface SaveResult extends ProviderView {
  saved: boolean;
  env_written: boolean;
  env_error: string | null;
}

export class SettingsError extends Error {
  status: number;
  reason: string | null;
  fields: Record<string, string>;
  constructor(status: number, message: string, reason: string | null = null, fields: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.reason = reason;
    this.fields = fields;
  }
}

const URL = "/api/admin/ai-provider";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (response.ok) {
    return response.json() as Promise<T>;
  }
  let detail: unknown = null;
  try {
    detail = (await response.json()).detail;
  } catch {
    /* not JSON */
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const d = detail as { message: string; reason?: string; fields?: Record<string, string> };
    throw new SettingsError(response.status, d.message, d.reason ?? null, d.fields ?? {});
  }
  throw new SettingsError(response.status, typeof detail === "string" ? detail : `Request failed (${response.status})`);
}

function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  return call<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const aiProviderApi = {
  get: () => call<ProviderView>(URL),
  save: (body: { provider: Provider; key?: string; model?: string }) => send<SaveResult>(URL, "PUT", body),
  remove: () => send<ProviderView>(URL, "DELETE"),
  test: (body: { provider?: Provider; key?: string; model?: string }) => send<TestResult>(`${URL}/test`, "POST", body),
};

/** Keyed by the access code too, so entering it fetches again. */
export function useAiProvider(enabled: boolean, accessCode: string) {
  return useQuery({
    queryKey: ["ai-provider", accessCode],
    queryFn: aiProviderApi.get,
    enabled,
    retry: false,
    staleTime: 0,
  });
}

export function useRefreshAiProvider() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["ai-provider"] });
    void client.invalidateQueries({ queryKey: ["deals-status"] });
  };
}

/** Which refusal, if any, stands between this browser and the screen. */
export function blockedBy(error: unknown): Blocked | null {
  if (error instanceof SettingsError && error.status === 403) {
    if (error.reason === "access_code" || error.reason === "access_off" || error.reason === "not_admin") {
      return error.reason;
    }
    return "not_admin";
  }
  return null;
}

// The form, as plain state so it can be tested without a browser.

export type TestState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; result: TestResult }
  | { status: "error"; message: string };

export interface FormState {
  provider: Provider;
  key: string;
  model: string;
  showKey: boolean;
  test: TestState;
  saving: boolean;
  notice: { tone: "ok" | "warn" | "danger"; text: string } | null;
  errors: Record<string, string>;
}

export type FormAction =
  | { type: "load"; view: ProviderView }
  | { type: "provider"; value: Provider }
  | { type: "key"; value: string }
  | { type: "model"; value: string }
  | { type: "toggle-key" }
  | { type: "test-start" }
  | { type: "test-done"; result: TestResult }
  | { type: "test-error"; message: string }
  | { type: "save-start" }
  | { type: "saved"; result: SaveResult }
  | { type: "removed" }
  | { type: "failed"; message: string; fields?: Record<string, string> };

export function initialForm(view?: ProviderView): FormState {
  return {
    provider: view?.saved_provider ?? view?.provider ?? "anthropic",
    key: "",
    model: view?.model_override ?? "",
    showKey: false,
    test: { status: "idle" },
    saving: false,
    notice: null,
    errors: {},
  };
}

export function formReducer(state: FormState, action: FormAction): FormState {
  switch (action.type) {
    case "load":
      return { ...initialForm(action.view), notice: state.notice };
    case "provider":
      // A result for one provider says nothing about another.
      return { ...state, provider: action.value, test: { status: "idle" }, notice: null, errors: {} };
    case "key":
      return { ...state, key: action.value, test: { status: "idle" }, notice: null, errors: { ...state.errors, key: "" } };
    case "model":
      return { ...state, model: action.value, notice: null, errors: { ...state.errors, model: "" } };
    case "toggle-key":
      return { ...state, showKey: !state.showKey };
    case "test-start":
      return { ...state, test: { status: "running" }, notice: null };
    case "test-done":
      return { ...state, test: { status: "done", result: action.result } };
    case "test-error":
      return { ...state, test: { status: "error", message: action.message } };
    case "save-start":
      return { ...state, saving: true, notice: null, errors: {} };
    case "saved":
      // The typed key is dropped as soon as the API has it.
      return { ...state, key: "", showKey: false, saving: false, notice: { tone: action.result.env_error ? "warn" : "ok", text: savedMessage(action.result) } };
    case "removed":
      return { ...state, key: "", saving: false, test: { status: "idle" }, notice: { tone: "ok", text: "Saved key removed · the environment's key applies" } };
    case "failed":
      return { ...state, saving: false, notice: { tone: "danger", text: action.message }, errors: action.fields ?? {} };
  }
}

export function savedMessage(result: SaveResult): string {
  if (result.env_written) {
    return "Saved · also written to .env";
  }
  if (result.env_error) {
    return `Saved · ${result.env_error}`;
  }
  return "Saved";
}

/** Why Save is unavailable, or null when it can be pressed. */
export function saveBlocked(state: FormState, view: ProviderView | undefined): string | null {
  if (!view) {
    return "Loading";
  }
  if (state.saving) {
    return "Saving";
  }
  if (state.key.trim() && !view.encryption_ready) {
    return "The key can't be saved: SETTINGS_ENCRYPTION_KEY is not set on the API";
  }
  if (!state.key.trim() && !view.saved_key) {
    return "Enter the API key";
  }
  return null;
}

/** Why Test connection is unavailable, or null. With nothing typed it tests the key in use. */
export function testBlocked(state: FormState, view: ProviderView | undefined): string | null {
  if (state.test.status === "running") {
    return "Testing";
  }
  if (!state.key.trim() && !view?.configured) {
    return "Enter a key to test";
  }
  return null;
}

export function testSummary(result: TestResult): string {
  const timing = result.latency_ms === null ? "" : ` · ${result.latency_ms} ms`;
  if (result.ok) {
    const count = result.models?.length ?? result.model_count ?? 0;
    return `Connected · HTTP ${result.status}${timing}${count ? ` · ${count} model${count === 1 ? "" : "s"}` : ""}`;
  }
  const status = result.status === null ? "No response" : `HTTP ${result.status}`;
  return `Failed · ${status}${timing}${result.error ? ` · ${result.error}` : ""}`;
}

export const SOURCE_LABEL: Record<ProviderView["source"], string> = {
  db: "Saved in Settings",
  env: "Environment variable",
  none: "Not configured",
};
