import { describe, expect, it } from "vitest";
import { visibleNav } from "../components/shell/WorkspaceShell";
import {
  blockedBy,
  formReducer,
  initialForm,
  saveBlocked,
  savedMessage,
  SettingsError,
  testBlocked,
  testSummary,
  type ProviderView,
  type SaveResult,
  type TestResult,
} from "./aiProvider";

const view: ProviderView = {
  provider: "anthropic",
  provider_label: "Anthropic API",
  configured: true,
  source: "env",
  last4: "abcd",
  model: "claude-opus-5-5",
  model_override: null,
  model_default: "claude-opus-5-5",
  saved_provider: null,
  saved_key: false,
  saved_key_unreadable: false,
  env_provider: "anthropic",
  env_key_set: true,
  updated_by: null,
  updated_at: null,
  last_test: null,
  encryption_ready: true,
  env_file: { enabled: true, writable: true },
  providers: [
    { id: "anthropic", label: "Anthropic API" },
    { id: "foundry", label: "Claude on Microsoft Foundry" },
  ],
};

const failed: TestResult = {
  ok: false,
  status: 401,
  latency_ms: 120,
  models: [],
  error: "authentication_error: invalid x-api-key",
  provider: "anthropic",
  subject: "typed",
  at: "2026-11-22T10:00:00Z",
};

describe("AI provider form", () => {
  it("starts empty and never holds a saved key", () => {
    const state = initialForm({ ...view, saved_key: true, saved_provider: "foundry", model_override: "claude-x" });
    expect(state.key).toBe("");
    expect(state.provider).toBe("foundry");
    expect(state.model).toBe("claude-x");
    expect(state.showKey).toBe(false);
  });

  it("toggles the key between hidden and shown", () => {
    const shown = formReducer(initialForm(view), { type: "toggle-key" });
    expect(shown.showKey).toBe(true);
    expect(formReducer(shown, { type: "toggle-key" }).showKey).toBe(false);
  });

  it("drops a test result once the key or provider changes", () => {
    let state = formReducer(initialForm(view), { type: "key", value: "sk-ant-dummy-key-0000000000" });
    state = formReducer(state, { type: "test-start" });
    expect(testBlocked(state, view)).toBe("Testing");
    state = formReducer(state, { type: "test-done", result: failed });
    expect(state.test.status).toBe("done");
    expect(formReducer(state, { type: "key", value: "sk-ant-other-key-000000000" }).test.status).toBe("idle");
    expect(formReducer(state, { type: "provider", value: "foundry" }).test.status).toBe("idle");
  });

  it("says why Save is unavailable", () => {
    const empty = initialForm(view);
    expect(saveBlocked(empty, undefined)).toBe("Loading");
    expect(saveBlocked(empty, view)).toBe("Enter the API key");
    const typed = formReducer(empty, { type: "key", value: "sk-ant-dummy-key-0000000000" });
    expect(saveBlocked(typed, view)).toBeNull();
    expect(saveBlocked(typed, { ...view, encryption_ready: false })).toMatch(/SETTINGS_ENCRYPTION_KEY/);
    // With a key saved, the provider or model can change without retyping it.
    expect(saveBlocked(empty, { ...view, saved_key: true })).toBeNull();
  });

  it("tests the typed key, or the key in use when nothing is typed", () => {
    expect(testBlocked(initialForm(view), view)).toBeNull();
    expect(testBlocked(initialForm(view), { ...view, configured: false })).toBe("Enter a key to test");
  });

  it("clears the typed key on save and says whether .env was written", () => {
    const typed = formReducer(formReducer(initialForm(view), { type: "key", value: "sk-ant-dummy-key-0000000000" }), { type: "toggle-key" });
    const result: SaveResult = { ...view, saved: true, env_written: true, env_error: null, source: "db" };
    const saved = formReducer(formReducer(typed, { type: "save-start" }), { type: "saved", result });
    expect(saved.key).toBe("");
    expect(saved.showKey).toBe(false);
    expect(saved.notice).toEqual({ tone: "ok", text: "Saved · also written to .env" });
    expect(savedMessage({ ...result, env_written: false })).toBe("Saved");
    expect(savedMessage({ ...result, env_written: false, env_error: "Could not write the .env file" })).toBe("Saved · Could not write the .env file");
  });

  it("keeps the API's field errors on a failed save", () => {
    const state = formReducer(initialForm(view), { type: "failed", message: "Check the highlighted fields", fields: { key: "Enter the API key" } });
    expect(state.errors.key).toBe("Enter the API key");
    expect(state.notice?.tone).toBe("danger");
  });

  it("summarises a test result with its status and reason", () => {
    expect(testSummary(failed)).toBe("Failed · HTTP 401 · 120 ms · authentication_error: invalid x-api-key");
    expect(testSummary({ ...failed, ok: true, status: 200, error: null, models: ["a", "b"] })).toBe("Connected · HTTP 200 · 120 ms · 2 models");
    expect(testSummary({ ...failed, status: null, latency_ms: null, error: "Could not reach the provider" })).toBe("Failed · No response · Could not reach the provider");
  });

  it("tells the refusals apart", () => {
    expect(blockedBy(new SettingsError(403, "x", "access_code"))).toBe("access_code");
    expect(blockedBy(new SettingsError(403, "x", "access_off"))).toBe("access_off");
    expect(blockedBy(new SettingsError(403, "Not available to client users"))).toBe("not_admin");
    expect(blockedBy(new SettingsError(500, "x"))).toBeNull();
  });

  it("shows Settings to the administrator only", () => {
    expect(visibleNav("admin").map((n) => n.label)).toContain("Settings");
    for (const role of ["onboarding_analyst", "expert", "qc", "reviewer", "monitoring_analyst", "head", "client"] as const) {
      expect(visibleNav(role).map((n) => n.label)).not.toContain("Settings");
    }
  });
});
