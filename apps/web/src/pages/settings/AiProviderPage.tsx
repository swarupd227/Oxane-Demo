/* Settings › AI provider. The administrator sets the model key: a status card for what is in use
 * now, and a form that tests a typed key before saving it. The API enforces the persona and the
 * access code whatever this screen shows. */
import clsx from "clsx";
import { CircleCheck, CircleX, Eye, EyeOff, Lock, PlugZap, ShieldAlert } from "lucide-react";
import { useReducer, useState, type ReactNode } from "react";
import { Field, Select, TextInput, when } from "../../components/deals/parts";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/layout";
import { Tooltip } from "../../components/ui/Tooltip";
import {
  aiProviderApi,
  blockedBy,
  formReducer,
  initialForm,
  saveBlocked,
  SettingsError,
  SOURCE_LABEL,
  testBlocked,
  testSummary,
  useAiProvider,
  useRefreshAiProvider,
  type Provider,
  type ProviderView,
  type TestResult,
} from "../../lib/aiProvider";
import { usePersona } from "../../lib/persona";
import { Badge, PageTitle, Panel } from "../../monitoring/ui";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-2 last:border-b-0">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="min-w-0 truncate text-right text-[0.8125rem] font-medium">{children}</dd>
    </div>
  );
}

function TestLine({ result }: { result: TestResult }) {
  return (
    <p
      role="status"
      data-testid="test-result"
      className={clsx("flex items-start gap-2 rounded-md px-3 py-2 text-[0.8125rem] font-medium", result.ok ? "bg-ok-tint text-ok" : "bg-danger-tint text-danger")}
    >
      {result.ok ? <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0" /> : <CircleX aria-hidden className="mt-0.5 size-4 shrink-0" />}
      <span className="min-w-0 break-words">{testSummary(result)}</span>
    </p>
  );
}

function Blocked({ reason }: { reason: "not_admin" }) {
  const copy = {
    not_admin: { title: "Administrator only", text: "Switch to Alex Morgan, administrator, to change the AI provider.", icon: Lock },
  }[reason];
  const Icon = copy.icon;
  return (
    <div role="status" className="grid h-64 place-items-center rounded-lg border border-dashed border-line text-center">
      <div className="max-w-sm">
        <Icon aria-hidden className="mx-auto size-5 text-muted" />
        <p className="mt-2 text-sm font-medium">{copy.title}</p>
        <p className="mt-1 text-[0.8125rem] text-muted">{copy.text}</p>
      </div>
    </div>
  );
}

function StatusCard({ view }: { view: ProviderView }) {
  const test = view.last_test;
  return (
    <Panel
      title="In use now"
      actions={view.configured ? <Badge tone="ok">Configured</Badge> : <Badge tone="warn">Not configured</Badge>}
    >
      <dl data-testid="provider-status">
        <Row label="Provider">{view.provider_label}</Row>
        <Row label="Source">{SOURCE_LABEL[view.source]}</Row>
        <Row label="Key">{view.last4 ? <span className="font-mono">••••{view.last4}</span> : "–"}</Row>
        <Row label="Model">
          <span className="font-mono">{view.model}</span>
          {!view.model_override && <span className="ml-1.5 text-xs font-normal text-muted">default</span>}
        </Row>
        <Row label="Updated">{view.updated_by ? `${view.updated_by} · ${when(view.updated_at)}` : "–"}</Row>
        <Row label="Last test">
          {test ? (
            <span className={test.ok ? "text-ok" : "text-danger"}>
              {test.ok ? "Passed" : "Failed"}
              {test.status !== null && ` · HTTP ${test.status}`}
              {test.subject === "typed" ? " · typed key" : ""} · {when(test.at)}
            </span>
          ) : (
            "–"
          )}
        </Row>
      </dl>
      {view.saved_key_unreadable && (
        <p role="alert" className="mt-3 rounded-md bg-warn-tint px-3 py-2 text-xs font-medium text-warn">
          A key is saved but SETTINGS_ENCRYPTION_KEY cannot decrypt it, so the environment&rsquo;s key applies. Save the key again.
        </p>
      )}
      <p className="mt-3 text-xs text-muted">
        A key saved here is used from the next model call, ahead of the environment&rsquo;s {view.env_provider === "foundry" ? "ANTHROPIC_FOUNDRY_API_KEY" : "ANTHROPIC_API_KEY"}
        {view.env_key_set ? " (set)" : " (not set)"}.
        {view.env_file.enabled && (view.env_file.writable ? " Saving also writes it to the local .env file." : " The local .env file is not writable.")}
      </p>
    </Panel>
  );
}

function ProviderForm({ view }: { view: ProviderView }) {
  const [state, dispatch] = useReducer(formReducer, view, initialForm);
  const refresh = useRefreshAiProvider();
  const [confirmRemove, setConfirmRemove] = useState(false);
  const saveReason = saveBlocked(state, view);
  const testReason = testBlocked(state, view);
  const typed = state.key.trim();

  const runTest = async () => {
    dispatch({ type: "test-start" });
    try {
      const result = await aiProviderApi.test(typed ? { key: typed, provider: state.provider, model: state.model || undefined } : {});
      dispatch({ type: "test-done", result });
      refresh();
    } catch (error) {
      dispatch({ type: "test-error", message: error instanceof Error ? error.message : "The test did not run" });
    }
  };
  const save = async () => {
    dispatch({ type: "save-start" });
    try {
      const result = await aiProviderApi.save({ provider: state.provider, key: typed || undefined, model: state.model.trim() });
      dispatch({ type: "saved", result });
      refresh();
    } catch (error) {
      dispatch({ type: "failed", message: error instanceof Error ? error.message : "Not saved", fields: error instanceof SettingsError ? error.fields : {} });
    }
  };
  const remove = async () => {
    setConfirmRemove(false);
    dispatch({ type: "save-start" });
    try {
      await aiProviderApi.remove();
      dispatch({ type: "removed" });
      refresh();
    } catch (error) {
      dispatch({ type: "failed", message: error instanceof Error ? error.message : "Not removed" });
    }
  };

  const gated = (reason: string | null, button: ReactNode) =>
    reason ? (
      <Tooltip content={reason}>
        <span tabIndex={0}>{button}</span>
      </Tooltip>
    ) : (
      button
    );

  return (
    <Panel title="Change key" meta={view.saved_key ? `Saved key ••••${view.last4 ?? ""}` : "No key saved here"}>
      <form
        noValidate
        aria-label="AI provider"
        onSubmit={(event) => {
          event.preventDefault();
          if (!saveReason) {
            void save();
          }
        }}
      >
        {!view.encryption_ready && (
          <p role="alert" data-testid="encryption-missing" className="mb-3 flex items-start gap-2 rounded-md bg-warn-tint px-3 py-2 text-[0.8125rem] font-medium text-warn">
            <ShieldAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            <span>The key can&rsquo;t be saved: SETTINGS_ENCRYPTION_KEY is not set on the API. Test connection still works.</span>
          </p>
        )}
        {state.notice && (
          <p
            role={state.notice.tone === "danger" ? "alert" : "status"}
            data-testid="save-notice"
            className={clsx(
              "mb-3 rounded-md px-3 py-2 text-[0.8125rem] font-medium",
              state.notice.tone === "ok" ? "bg-ok-tint text-ok" : state.notice.tone === "warn" ? "bg-warn-tint text-warn" : "bg-danger-tint text-danger",
            )}
          >
            {state.notice.text}
          </p>
        )}
        <Field id="ai-provider" label="Provider" error={state.errors.provider}>
          <Select id="ai-provider" value={state.provider} onChange={(e) => dispatch({ type: "provider", value: e.target.value as Provider })}>
            {view.providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field id="ai-key" label="API key" hint={view.saved_key ? "Leave empty to keep the saved key" : "Starts sk-ant- for the Anthropic API"} error={state.errors.key || undefined}>
          <div className="relative">
            <TextInput
              id="ai-key"
              type={state.showKey ? "text" : "password"}
              autoComplete="off"
              spellCheck={false}
              placeholder={view.saved_key ? `••••${view.last4 ?? ""}` : "sk-ant-…"}
              value={state.key}
              onChange={(e) => dispatch({ type: "key", value: e.target.value })}
              invalid={Boolean(state.errors.key)}
              className="pr-10 font-mono"
            />
            <button
              type="button"
              onClick={() => dispatch({ type: "toggle-key" })}
              aria-label={state.showKey ? "Hide key" : "Show key"}
              aria-pressed={state.showKey}
              className="absolute top-1/2 right-1 grid size-7 -translate-y-1/2 cursor-pointer place-items-center rounded text-muted hover:bg-sand hover:text-ink"
            >
              {state.showKey ? <EyeOff aria-hidden className="size-4" /> : <Eye aria-hidden className="size-4" />}
            </button>
          </div>
        </Field>
        <Field id="ai-model" label="Model" hint={`Empty uses the default, ${view.model_default}`} error={state.errors.model || undefined}>
          <TextInput id="ai-model" value={state.model} placeholder={view.model_default} onChange={(e) => dispatch({ type: "model", value: e.target.value })} invalid={Boolean(state.errors.model)} className="font-mono" />
        </Field>

        {state.test.status === "done" && (
          <div className="mb-3">
            <TestLine result={state.test.result} />
          </div>
        )}
        {state.test.status === "error" && (
          <p role="alert" data-testid="test-result" className="mb-3 rounded-md bg-danger-tint px-3 py-2 text-[0.8125rem] font-medium text-danger">
            {state.test.message}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
          {gated(
            testReason,
            <Button size="sm" variant="secondary" disabled={Boolean(testReason)} onClick={() => void runTest()}>
              <PlugZap aria-hidden className="size-4" />
              {state.test.status === "running" ? "Testing…" : typed ? "Test connection" : "Test key in use"}
            </Button>,
          )}
          {gated(
            saveReason,
            <Button size="sm" type="submit" disabled={Boolean(saveReason)}>
              {state.saving ? "Saving…" : "Save"}
            </Button>,
          )}
          {view.saved_key && (
            <div className="ml-auto flex items-center gap-2">
              {confirmRemove ? (
                <>
                  <span className="text-xs text-muted">Remove the saved key?</span>
                  <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(false)}>
                    Keep
                  </Button>
                  <Button size="sm" variant="secondary" className="text-danger" onClick={() => void remove()}>
                    Remove
                  </Button>
                </>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(true)}>
                  Remove saved key
                </Button>
              )}
            </div>
          )}
        </div>
      </form>
    </Panel>
  );
}

export function AiProviderPage() {
  const { persona } = usePersona();
  const isAdmin = persona?.role === "admin";
  const { data, error, isLoading } = useAiProvider(Boolean(persona) && isAdmin, "");
  const blocked = (persona && !isAdmin) || blockedBy(error) ? "not_admin" : null;

  return (
    <>
      <PageTitle title="AI provider" meta="Settings · administrator only" />
      {!persona || (isAdmin && isLoading) ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      ) : blocked ? (
        <Blocked reason={blocked} />
      ) : error || !data ? (
        <p role="alert" className="rounded-md bg-danger-tint px-3 py-2 text-[0.8125rem] font-medium text-danger">
          {error instanceof Error ? error.message : "Settings did not load"}
        </p>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
          <StatusCard view={data} />
          <ProviderForm view={data} />
        </div>
      )}
    </>
  );
}
