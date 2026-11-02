import { Waypoints } from "lucide-react";
import type { Grounding } from "../../lib/workbench";

/** The ontology concept behind a value, how it relates to others, and what the model relied on. */
export function GroundingLine({ grounding }: { grounding: Grounding | undefined }) {
  if (!grounding) {
    return null;
  }
  const { concept, cited } = grounding;
  const shown = concept.relations.slice(0, 2);
  const named = new Set([concept.label, ...shown.map((relation) => relation.target)]);
  const others = cited.filter((label) => !named.has(label));
  return (
    <div
      role="group"
      aria-label="Ontology grounding"
      className="rounded-md bg-canvas px-3 py-2 text-[0.8125rem] leading-snug"
    >
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Waypoints aria-hidden className="size-3.5 shrink-0 text-muted" />
        <span className="text-muted">Grounded in</span>
        <span
          title={concept.meaning}
          className="rounded border border-line bg-surface px-1.5 py-px font-medium"
        >
          {concept.label}
        </span>
        {shown.map((relation) => (
          <span key={`${relation.type}-${relation.target}`} className="text-muted">
            {relation.type} <span className="text-ink">{relation.target}</span>
          </span>
        ))}
      </p>
      {others.length > 0 && (
        <p className="mt-1 pl-5.5 text-muted">Also relied on: {others.join(", ")}</p>
      )}
    </div>
  );
}
