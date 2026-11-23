import { RotateCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Skeleton } from "../components/ui/layout";
import { Badge, DataTable, FilterSelect, Kpis, PageTitle, Panel, type Column } from "../monitoring/ui";
import { AgentDetail } from "./AgentDetail";
import { AgentGraph, GraphLegend } from "./AgentGraph";
import { pct, tokens, usd, useAgents, type Agent, type Outcome, type Registry } from "./api";
import "./agents.css";
import { Coverage } from "./Coverage";
import { KindBadge, Meter, Tabs, Trigger, useBase } from "./parts";
import { runColumns } from "./runColumns";

export function AgentsConsole() {
  const { data, isPending, isError, refetch } = useAgents();
  const { pathname } = useLocation();
  useEffect(() => {
    const app = pathname.startsWith("/monitoring") ? "Monitoring" : "Onboarding";
    document.title = `Agents · ${app} · Oxane`;
  }, [pathname]);
  if (isPending) {
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div role="alert" className="flex items-center justify-between gap-4 rounded-md bg-danger-tint px-3 py-2 text-sm">
        <span className="font-medium text-danger">The agent registry could not be loaded.</span>
        <Button variant="secondary" size="sm" onClick={() => void refetch()}>
          <RotateCw aria-hidden className="size-3.5" />
          Try again
        </Button>
      </div>
    );
  }
  return (
    <div className="agents-console min-w-0">
      <PageTitle
        title="Agents"
        meta={`AI agents and code engines · registry v${data.version}`}
      />
      <Tabs />
      <Routes>
        <Route index element={<AgentsList registry={data} />} />
        <Route path="graph" element={<GraphView registry={data} />} />
        <Route path="coverage" element={<Coverage registry={data} />} />
        <Route path="runs" element={<RunLog registry={data} />} />
        <Route path=":id" element={<AgentDetail registry={data} />} />
      </Routes>
    </div>
  );
}

function Totals({ registry }: { registry: Registry }) {
  const model = registry.agents.filter((a) => a.kind === "model").length;
  const t = registry.totals;
  return (
    <Kpis
      items={[
        { label: "Model agents", value: model },
        { label: "Code engines", value: registry.agents.length - model },
        { label: "Model runs", value: t.runs },
        { label: "Model cost", value: usd(t.cost_usd) },
        { label: "Accepted", value: t.decided ? pct(t.acceptance) : "–", tone: t.acceptance !== null && t.acceptance < 0.9 ? "warn" : t.decided ? "ok" : undefined },
        { label: "Awaiting review", value: t.outcomes.awaiting_review, tone: t.outcomes.awaiting_review ? "warn" : undefined },
      ]}
    />
  );
}

function status(agent: Agent): { label: string; tone: "ok" | "neutral" | "info" } {
  if (agent.kind === "code") {
    return { label: "Always on", tone: "neutral" };
  }
  return agent.stats && agent.stats.runs > 0 ? { label: "Active", tone: "ok" } : { label: "No runs", tone: "info" };
}

function AgentsList({ registry }: { registry: Registry }) {
  const navigate = useNavigate();
  const base = useBase();
  const [kind, setKind] = useState<"all" | "model" | "code">("all");
  const stage = (id: string) => registry.stages.find((s) => s.id === id)?.label ?? id;
  const order = (id: string) => registry.stages.findIndex((s) => s.id === id);
  const rows = registry.agents.filter((a) => kind === "all" || a.kind === kind);
  const columns: Column<Agent>[] = [
    {
      key: "name",
      header: "Agent",
      sort: (a) => a.name,
      render: (a) => <span className="font-medium whitespace-nowrap text-ink">{a.name}</span>,
    },
    { key: "kind", header: "Type", sort: (a) => a.kind, render: (a) => <KindBadge kind={a.kind} /> },
    { key: "stage", header: "Stage", sort: (a) => order(a.stage), render: (a) => <span className="whitespace-nowrap">{order(a.stage) + 1}. {stage(a.stage)}</span> },
    {
      key: "trigger",
      header: "Trigger",
      render: (a) => (
        <span className="flex max-w-[17rem] min-w-0 items-center gap-1.5">
          <Trigger kind={a.triggers[0].kind} label={a.triggers[0].label} compact />
          {a.triggers.length > 1 && <span className="numeric shrink-0 text-[0.6875rem] text-muted">+{a.triggers.length - 1}</span>}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      sort: (a) => status(a).label,
      render: (a) => {
        const s = status(a);
        return <Badge tone={s.tone}>{s.label}</Badge>;
      },
    },
    { key: "runs", header: "Runs", align: "right", sort: (a) => a.stats?.runs ?? -1, render: (a) => <span className="numeric">{a.stats ? a.stats.runs : "–"}</span> },
    { key: "cost", header: "Cost", align: "right", sort: (a) => a.stats?.cost_usd ?? -1, render: (a) => <span className="numeric">{a.stats ? usd(a.stats.cost_usd) : "–"}</span> },
    { key: "acceptance", header: "Acceptance", sort: (a) => a.stats?.acceptance ?? -1, render: (a) => (a.stats ? <Meter value={a.stats.acceptance} /> : <span className="text-muted">–</span>) },
  ];
  return (
    <>
      <Totals registry={registry} />
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(a) => a.id}
        search={(a) => `${a.name} ${a.purpose} ${a.triggers.map((t) => t.label).join(" ")} ${Object.keys(a.gateway_tasks).join(" ")}`}
        searchPlaceholder="Search agents and tasks"
        initialSort={{ key: "stage", dir: "asc" }}
        onRowClick={(a) => navigate(`${base}/${a.id}`)}
        toolbar={
          <FilterSelect
            label="Type"
            value={kind}
            onChange={setKind}
            options={[
              { value: "all", label: "All types" },
              { value: "model", label: "Model agents" },
              { value: "code", label: "Code engines" },
            ]}
          />
        }
      />
    </>
  );
}

function GraphView({ registry }: { registry: Registry }) {
  return (
    <Panel title="Dependencies" meta={`${registry.agents.length} agents · ${registry.agents.reduce((n, a) => n + a.upstream.length, 0)} hand-offs`} actions={<GraphLegend />} flush>
      <div className="p-3">
        <AgentGraph registry={registry} />
      </div>
    </Panel>
  );
}

function RunLog({ registry }: { registry: Registry }) {
  const navigate = useNavigate();
  const base = useBase();
  const [agent, setAgent] = useState("all");
  const [client, setClient] = useState("all");
  const [outcome, setOutcome] = useState<"all" | Outcome>("all");
  const names = useMemo(() => new Map(registry.agents.map((a) => [a.id, a.name])), [registry]);
  const clientName = (id: string) => registry.clients[id]?.name ?? id;
  const rows = registry.runs.filter(
    (r) => (agent === "all" || r.agent === agent) && (client === "all" || r.client === client) && (outcome === "all" || r.outcome === outcome),
  );
  const columns = runColumns(registry, { names, clientName, showAgent: true });
  return (
    <>
      <div className="mb-3 grid gap-3 xl:grid-cols-2">
        {Object.entries(registry.by_client).map(([id, s]) => {
          const c = registry.clients[id];
          return (
            <div key={id} className="flex items-center gap-4 rounded-lg border border-line bg-surface px-3 py-2 text-xs">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[0.8125rem] font-semibold">{clientName(id)}</span>
                <span className="text-muted">{c?.ai_permitted === false ? "AI not permitted · code checks only" : "AI permitted"}</span>
              </span>
              <Stat label="Calls" value={s.runs} />
              <Stat label="Refused" value={s.refused} />
              <Stat label="Tokens" value={tokens(s.tokens)} />
              <Stat label="Cost" value={usd(s.cost_usd)} />
              <Stat label="Acceptance" value={pct(s.acceptance)} />
            </div>
          );
        })}
      </div>
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(r) => r.id}
        search={(r) => `${r.subject} ${r.task} ${r.note} ${r.ref} ${names.get(r.agent ?? "") ?? ""}`}
        searchPlaceholder="Search runs"
        initialSort={{ key: "at", dir: "desc" }}
        pageSize={50}
        onRowClick={(r) => r.agent && navigate(`${base}/${r.agent}`)}
        toolbar={
          <>
            <FilterSelect
              label="Agent"
              value={agent}
              onChange={setAgent}
              options={[{ value: "all", label: "All agents" }, ...registry.agents.filter((a) => a.kind === "model").map((a) => ({ value: a.id, label: a.name }))]}
            />
            <FilterSelect label="Client" value={client} onChange={setClient} options={[{ value: "all", label: "All clients" }, ...Object.keys(registry.by_client).map((id) => ({ value: id, label: clientName(id) }))]} />
            <FilterSelect
              label="Outcome"
              value={outcome}
              onChange={setOutcome}
              options={[{ value: "all" as const, label: "All outcomes" }, ...(Object.entries(registry.outcomes) as [Outcome, string][]).map(([value, label]) => ({ value, label }))]}
            />
          </>
        }
      />
    </>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <span className="shrink-0 text-right">
      <span className="block text-[0.6875rem] text-muted">{label}</span>
      <span className="numeric block text-[0.8125rem] font-semibold">{value}</span>
    </span>
  );
}
