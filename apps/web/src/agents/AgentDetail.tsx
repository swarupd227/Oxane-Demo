import { ArrowLeft, ArrowRight, ShieldCheck } from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, DataTable, Kpis, Panel } from "../monitoring/ui";
import { runColumns } from "./runColumns";
import { AgentGraph } from "./AgentGraph";
import { pct, seconds, tokens, usd, type Agent, type Registry } from "./api";
import { KindBadge, Trigger, useBase } from "./parts";

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-3 border-b border-line py-2 text-[0.8125rem] last:border-b-0">
      <dt className="text-xs font-medium text-muted">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

function List({ items }: { items: ReactNode[] }) {
  return (
    <ul className="space-y-0.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2">
          <span aria-hidden className="mt-[0.55rem] size-1 shrink-0 rounded-full bg-stone" />
          <span className="min-w-0">{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function AgentDetail({ registry }: { registry: Registry }) {
  const { id } = useParams();
  const base = useBase();
  const agent = registry.agents.find((a) => a.id === id);
  const names = useMemo(() => new Map(registry.agents.map((a) => [a.id, a.name])), [registry]);
  if (!agent) {
    return (
      <p className="text-sm text-muted">
        No agent called {id}.{" "}
        <Link to={base} className="text-ink underline">
          All agents
        </Link>
      </p>
    );
  }
  const runs = registry.runs.filter((r) => r.agent === agent.id);
  const clientName = (cid: string) => registry.clients[cid]?.name ?? cid;
  const stage = registry.stages.findIndex((s) => s.id === agent.stage);
  const label = (list: { id: string; label: string }[], key: string) => list.find((x) => x.id === key)?.label ?? key;
  const s = agent.stats;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Link to={base} className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
          <ArrowLeft aria-hidden className="size-3.5" />
          Agents
        </Link>
        <span aria-hidden className="text-stone">/</span>
        <h2 className="text-base font-semibold">{agent.name}</h2>
        <KindBadge kind={agent.kind} />
        <Badge tone="neutral">
          {stage + 1}. {registry.stages[stage]?.label}
        </Badge>
        <span className="font-mono text-[0.6875rem] text-muted">{agent.id}</span>
      </div>

      {s ? (
        <Kpis
          items={[
            { label: "Runs", value: s.runs },
            { label: "Refused (no AI)", value: s.refused },
            { label: "Cost", value: usd(s.cost_usd) },
            { label: "Tokens", value: tokens(s.tokens) },
            { label: "Mean duration", value: s.runs ? seconds(Math.round(s.duration_ms / s.runs)) : "–" },
            { label: "Acceptance", value: s.decided ? `${pct(s.acceptance)} of ${s.decided}` : "–" },
            { label: "Awaiting review", value: s.outcomes.awaiting_review, tone: s.outcomes.awaiting_review ? "warn" : undefined },
          ]}
        />
      ) : null}

      <div className="grid gap-3 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Panel title="Definition" flush>
          <dl className="px-3">
            <Section label="Purpose">{agent.purpose}</Section>
            <Section label="Tasks">
              <List items={agent.tasks} />
            </Section>
            <Section label="Trigger">
              <List items={agent.triggers.map((t) => <Trigger key={t.label} kind={t.kind} label={t.label} />)} />
            </Section>
            <Section label="Inputs">
              <List items={agent.inputs} />
            </Section>
            <Section label="Outputs">
              <List items={agent.outputs} />
            </Section>
            <Section label="Use case steps">
              <div className="flex flex-wrap gap-1">
                {Object.entries(agent.use_cases).flatMap(([uc, steps]) =>
                  steps.map((step) => (
                    <Badge key={`${uc}-${step}`} tone="neutral">
                      {uc} · {step}. {registry.use_cases[uc]?.steps[String(step)]}
                    </Badge>
                  )),
                )}
              </div>
            </Section>
            <Section label="Pain points">
              <div className="flex flex-wrap gap-1">
                {agent.pain_points.map((p) => (
                  <Badge key={p} tone="info">
                    {label(registry.pain_points, p)}
                  </Badge>
                ))}
              </div>
            </Section>
            <Section label="Asset classes">
              <div className="flex flex-wrap gap-1">
                {agent.asset_classes.now.map((a) => (
                  <Badge key={a} tone="ok">
                    {label(registry.asset_classes, a)} · now
                  </Badge>
                ))}
                {agent.asset_classes.after_pilot.map((a) => (
                  <Badge key={a} tone="neutral">
                    {label(registry.asset_classes, a)} · after pilot
                  </Badge>
                ))}
              </div>
            </Section>
          </dl>
        </Panel>

        <div className="space-y-3">
          <Panel title="Constraints" flush>
            <ul className="divide-y divide-line">
              {agent.constraints.map((c) => (
                <li key={c} className="flex gap-2 px-3 py-1.5 text-[0.8125rem]">
                  <ShieldCheck aria-hidden className="mt-0.5 size-3.5 shrink-0 text-ok" />
                  <span>{registry.constraints[c] ?? c}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Dependencies" flush>
            <div className="grid grid-cols-2 divide-x divide-line">
              <DependencyList title="Upstream" links={agent.upstream} names={names} base={base} icon="in" />
              <DependencyList title="Downstream" links={agent.downstream} names={names} base={base} icon="out" />
            </div>
          </Panel>
          <Panel title={agent.kind === "model" ? "Model" : "Implementation"} flush>
            <dl className="px-3">
              {agent.kind === "model" ? (
                <>
                  <Section label="Model">
                    <span className="font-mono text-xs">{registry.model.name}</span> <span className="text-xs text-muted">· effort {registry.model.effort}</span>
                  </Section>
                  <Section label="Prompt version">
                    {agent.prompt_version ? (
                      <span>
                        <span className="font-mono text-xs">{agent.prompt_version.id}</span>{" "}
                        <span className="text-xs text-muted">· {agent.prompt_version.recordings} recorded requests</span>
                      </span>
                    ) : (
                      <span className="text-muted">Not recorded</span>
                    )}
                  </Section>
                  <Section label="Gateway tasks">
                    <ul className="space-y-0.5">
                      {Object.entries(agent.gateway_tasks).map(([task, text]) => (
                        <li key={task} className="flex flex-wrap items-baseline gap-x-2">
                          <code className="font-mono text-xs">{task}</code>
                          <span className="text-xs text-muted">{text}</span>
                        </li>
                      ))}
                    </ul>
                  </Section>
                </>
              ) : (
                <Section label="Model">
                  <span className="text-muted">None. Deterministic code.</span>
                </Section>
              )}
              <Section label="Source">
                <ul className="space-y-0.5">
                  {agent.source.map((path) => (
                    <li key={path}>
                      <code className="font-mono text-xs break-all">{path}</code>
                    </li>
                  ))}
                </ul>
              </Section>
            </dl>
          </Panel>
        </div>
      </div>

      <Panel title="Position in the pipeline" flush>
        <div className="p-3">
          <AgentGraph registry={registry} selected={agent.id} compact />
        </div>
      </Panel>

      {agent.kind === "model" &&
        (
          <DataTable
            title="Recent runs"
            rows={runs}
            columns={runColumns(registry, { names, clientName, showAgent: false })}
            rowKey={(r) => r.id}
            initialSort={{ key: "at", dir: "desc" }}
            pageSize={15}
            empty="No runs recorded for this agent."
          />
        )}
    </div>
  );
}

function DependencyList({ title, links, names, base, icon }: { title: string; links: Agent["upstream"]; names: Map<string, string>; base: string; icon: "in" | "out" }) {
  return (
    <div className="min-w-0 p-3">
      <p className="mb-1.5 text-xs font-medium text-subtle">{title}</p>
      {links.length ? (
        <ul className="space-y-1.5">
          {links.map((link) => (
            <li key={link.agent} className="text-[0.8125rem]">
              <Link to={`${base}/${link.agent}`} className="inline-flex items-center gap-1 font-medium hover:underline">
                {icon === "in" ? <ArrowRight aria-hidden className="size-3 text-muted" /> : null}
                {names.get(link.agent) ?? link.agent}
                {icon === "out" ? <ArrowRight aria-hidden className="size-3 text-muted" /> : null}
              </Link>
              <span className="block text-xs text-muted">{link.hands_off}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted">{icon === "in" ? "External trigger only" : "None"}</p>
      )}
    </div>
  );
}
