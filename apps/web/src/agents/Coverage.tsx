import clsx from "clsx";
import { Check } from "lucide-react";
import { Link } from "react-router-dom";
import { Panel } from "../monitoring/ui";
import type { Agent, Registry } from "./api";
import { KindBadge, useBase } from "./parts";

function AgentCell({ agent }: { agent: Agent }) {
  const base = useBase();
  return (
    <th scope="row" className="sticky left-0 z-10 bg-surface px-3 py-1.5 text-left font-normal">
      <span className="flex items-center gap-2">
        <Link to={`${base}/${agent.id}`} className="truncate font-medium hover:underline">
          {agent.name}
        </Link>
        <span className="ml-auto shrink-0">
          <KindBadge kind={agent.kind} />
        </span>
      </span>
    </th>
  );
}

export function Coverage({ registry }: { registry: Registry }) {
  const agents = [...registry.agents].sort((a, b) => registry.stages.findIndex((s) => s.id === a.stage) - registry.stages.findIndex((s) => s.id === b.stage));
  return (
    <div className="space-y-3">
      <Panel title="Pain points" meta={`${registry.pain_points.length} from the pitch brief and RFP review`} flush>
        <div className="overflow-x-auto">
          <table className="w-full table-fixed text-[0.8125rem]">
            <colgroup>
              <col className="w-[17rem]" />
              {registry.pain_points.map((p) => (
                <col key={p.id} />
              ))}
            </colgroup>
            <thead>
              <tr className="border-b border-line bg-canvas text-[0.6875rem] text-muted">
                <th scope="col" className="sticky left-0 z-10 bg-canvas px-3 py-1.5 text-left align-bottom font-semibold">
                  Agent
                </th>
                {registry.pain_points.map((p) => (
                  <th key={p.id} scope="col" className="px-1 py-1.5 text-center align-bottom leading-tight font-semibold">
                    <span className="line-clamp-3 text-[0.625rem] [overflow-wrap:normal]" title={p.label}>
                      {p.short}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.id} className="border-b border-line last:border-b-0 hover:bg-canvas">
                  <AgentCell agent={agent} />
                  {registry.pain_points.map((p) => {
                    const on = agent.pain_points.includes(p.id);
                    return (
                      <td key={p.id} className="px-1 py-1.5 text-center">
                        {on ? (
                          <span className={clsx("inline-grid size-5 place-items-center rounded", agent.kind === "model" ? "bg-info-tint text-info" : "bg-sand text-ink-soft")}>
                            <Check aria-label={`${agent.name}: ${p.label}`} className="size-3.5" />
                          </span>
                        ) : (
                          <span aria-hidden className="text-stone">
                            ·
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="border-t border-line bg-canvas text-[0.6875rem] text-muted">
                <th scope="row" className="sticky left-0 z-10 bg-canvas px-3 py-1.5 text-left font-semibold">
                  Agents per pain point
                </th>
                {registry.pain_points.map((p) => (
                  <td key={p.id} className="numeric px-1 py-1.5 text-center font-semibold text-ink">
                    {registry.agents.filter((a) => a.pain_points.includes(p.id)).length}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Asset classes" meta="Now (demo facilities) and after the pilot" flush>
        <div className="overflow-x-auto">
          <table className="w-full table-fixed text-[0.8125rem]">
            <colgroup>
              <col className="w-[17rem]" />
              {registry.asset_classes.map((c) => (
                <col key={c.id} />
              ))}
            </colgroup>
            <thead>
              <tr className="border-b border-line bg-canvas text-[0.6875rem] text-muted">
                <th scope="col" className="sticky left-0 z-10 bg-canvas px-3 py-1.5 text-left font-semibold">
                  Agent
                </th>
                {registry.asset_classes.map((c) => (
                  <th key={c.id} scope="col" className="px-2 py-1.5 text-center font-semibold">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.id} className="border-b border-line last:border-b-0 hover:bg-canvas">
                  <AgentCell agent={agent} />
                  {registry.asset_classes.map((c) => {
                    const now = agent.asset_classes.now.includes(c.id);
                    const later = agent.asset_classes.after_pilot.includes(c.id);
                    return (
                      <td key={c.id} className="px-2 py-1.5 text-center">
                        {now ? (
                          <span className="inline-flex h-5 items-center rounded bg-ok-tint px-1.5 text-[0.6875rem] font-medium text-ok">Now</span>
                        ) : later ? (
                          <span className="inline-flex h-5 items-center rounded border border-dashed border-stone px-1.5 text-[0.6875rem] font-medium text-muted">After pilot</span>
                        ) : (
                          <span aria-hidden className="text-stone">
                            ·
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="border-t border-line bg-canvas text-[0.6875rem] text-muted">
                <th scope="row" className="sticky left-0 z-10 bg-canvas px-3 py-1.5 text-left font-semibold">
                  Model agents now / after pilot
                </th>
                {registry.asset_classes.map((c) => {
                  const model = registry.agents.filter((a) => a.kind === "model");
                  return (
                    <td key={c.id} className="numeric px-2 py-1.5 text-center font-semibold text-ink">
                      {model.filter((a) => a.asset_classes.now.includes(c.id)).length} / {model.filter((a) => a.asset_classes.now.includes(c.id) || a.asset_classes.after_pilot.includes(c.id)).length}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
