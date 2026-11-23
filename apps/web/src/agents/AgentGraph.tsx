import clsx from "clsx";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Agent, Registry } from "./api";
import { layoutGraph, wrapLabel } from "./graph";
import { useBase } from "./parts";

/** The agents and code engines by pipeline stage; edges are data hand-offs. */
export function AgentGraph({ registry, selected, compact }: { registry: Registry; selected?: string; compact?: boolean }) {
  const navigate = useNavigate();
  const base = useBase();
  const [hover, setHover] = useState<string | null>(null);
  const layout = useMemo(
    () =>
      layoutGraph(
        registry.agents.map((a) => ({ id: a.id, stage: a.stage, upstream: a.upstream.map((u) => u.agent) })),
        registry.stages.map((s) => s.id),
      ),
    [registry],
  );
  const agents = useMemo(() => new Map(registry.agents.map((a) => [a.id, a])), [registry]);
  const focus = hover ?? selected ?? null;
  const linked = useMemo(() => {
    if (!focus) {
      return null;
    }
    const set = new Set([focus]);
    layout.edges.forEach((e) => {
      if (e.from === focus) set.add(e.to);
      if (e.to === focus) set.add(e.from);
    });
    return set;
  }, [focus, layout]);
  const handsOff = (from: string, to: string) => agents.get(to)?.upstream.find((u) => u.agent === from)?.hands_off ?? "";
  const open = (agent: Agent) => navigate(`${base}/${agent.id}`);

  return (
    <div className="overflow-x-auto">
      <svg
        role="group"
        aria-label="Agent dependencies by pipeline stage"
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        width="100%"
        style={{ maxWidth: layout.width, minWidth: compact ? undefined : Math.round(layout.width * 0.8) }}
        className="block select-none"
      >
        <defs>
          <marker id="agents-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L8 4 L0 8 z" className="fill-stone" />
          </marker>
          <marker id="agents-arrow-on" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L8 4 L0 8 z" className="fill-ink" />
          </marker>
        </defs>
        {layout.bands.map((band, i) => {
          const stage = registry.stages.find((s) => s.id === band.stage)!;
          return (
            <g key={band.stage}>
              <rect x={band.x - 6} y={4} width={band.width + 12} height={layout.height - 8} rx={6} className={i % 2 ? "fill-canvas" : "fill-sand/50"} />
              <text x={band.x} y={22} className="fill-muted text-[11px] font-medium">
                {i + 1}. {stage.label}
              </text>
            </g>
          );
        })}
        {layout.edges.map((edge) => {
          const on = linked ? linked.has(edge.from) && linked.has(edge.to) && (edge.from === focus || edge.to === focus) : false;
          return (
            <path
              key={`${edge.from}-${edge.to}`}
              d={edge.path}
              fill="none"
              markerEnd={on ? "url(#agents-arrow-on)" : "url(#agents-arrow)"}
              className={clsx("transition-opacity", on ? "stroke-ink" : "stroke-stone", linked && !on && "opacity-30")}
              strokeWidth={on ? 1.75 : 1.25}
            >
              <title>{`${agents.get(edge.from)?.name} → ${agents.get(edge.to)?.name}: ${handsOff(edge.from, edge.to)}`}</title>
            </path>
          );
        })}
        {layout.nodes.map((node) => {
          const agent = agents.get(node.id)!;
          const model = agent.kind === "model";
          const lines = wrapLabel(agent.name, 19);
          const dim = linked && !linked.has(node.id);
          const isSelected = selected === node.id;
          const runs = agent.stats?.runs ?? 0;
          return (
            <g
              key={node.id}
              role="link"
              tabIndex={0}
              aria-label={`${agent.name}, ${model ? "model agent" : "code engine, no model"}`}
              transform={`translate(${node.x} ${node.y})`}
              className={clsx("cursor-pointer outline-none transition-opacity [&:focus-visible>rect:first-child]:stroke-ink", dim && "opacity-40")}
              onMouseEnter={() => setHover(node.id)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(node.id)}
              onBlur={() => setHover(null)}
              onClick={() => open(agent)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  open(agent);
                }
              }}
            >
              <rect
                width={node.width}
                height={node.height}
                rx={model ? 8 : 3}
                className={clsx(model ? "fill-surface" : "fill-canvas", isSelected ? "stroke-ink" : model ? "stroke-ink-soft/70" : "stroke-subtle")}
                strokeWidth={isSelected ? 2 : 1}
                strokeDasharray={model ? undefined : "4 3"}
              />
              {isSelected && <rect x={0} y={0} width={4} height={node.height} rx={2} className="fill-accent" />}
              {lines.map((line, i) => (
                <text key={i} x={10} y={18 + i * 14} className={clsx("text-[12px] font-semibold", model ? "fill-ink" : "fill-ink-soft")}>
                  {line}
                </text>
              ))}
              <text x={10} y={node.height - 9} className="fill-muted text-[10px]">
                {model ? `Model · ${runs} run${runs === 1 ? "" : "s"}` : "No model · code"}
              </text>
              <title>{`${agent.name}: ${agent.purpose}`}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function GraphLegend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-muted">
      <span className="inline-flex items-center gap-1.5">
        <svg aria-hidden width="22" height="12">
          <rect x="1" y="1" width="20" height="10" rx="3" className="fill-surface stroke-ink-soft/70" />
        </svg>
        Model agent
      </span>
      <span className="inline-flex items-center gap-1.5">
        <svg aria-hidden width="22" height="12">
          <rect x="1" y="1" width="20" height="10" rx="1" className="fill-canvas stroke-subtle" strokeDasharray="3 2" />
        </svg>
        Code engine (no model)
      </span>
      <span className="inline-flex items-center gap-1.5">
        <svg aria-hidden width="26" height="10">
          <path d="M1 5 H21" className="stroke-stone" strokeWidth="1.25" markerEnd="url(#agents-arrow)" />
        </svg>
        Data hand-off
      </span>
    </div>
  );
}
