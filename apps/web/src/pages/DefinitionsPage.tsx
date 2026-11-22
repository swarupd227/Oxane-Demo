import clsx from "clsx";
import { CheckCircle2, CircleAlert, CornerDownRight, FileWarning, GitBranch } from "lucide-react";
import { useState } from "react";
import { EvidencePanel } from "../components/evidence/EvidencePanel";
import { ProvenanceChip, StatusPill } from "../components/ui/badges";
import { useSearchParams } from "react-router-dom";
import { Card, SectionLabel, Skeleton } from "../components/ui/layout";
import { NeedsIntake, PageHeader } from "../components/ui/PageHeader";
import { useCasework, type DefinitionNode } from "../lib/casework";
import { useSession } from "../lib/session";
import { useWorkbench } from "../lib/workbench";

interface Line {
  node: DefinitionNode;
  level: number;
  repeat: boolean;
}

/** Walk the inputs from a root, depth first, showing a shared term in full only once. */
function chain(root: string, nodes: Map<string, DefinitionNode>, seen: Set<string>): Line[] {
  const lines: Line[] = [];
  const visit = (key: string, level: number, path: string[]) => {
    const node = nodes.get(key);
    if (!node || path.includes(key)) {
      return;
    }
    const repeat = seen.has(key);
    lines.push({ node, level, repeat });
    if (repeat) {
      return;
    }
    seen.add(key);
    for (const ref of node.refers_to) {
      if (ref.role === "input" && ref.status === "traced") {
        visit(ref.key, level + 1, [...path, key]);
      }
    }
  };
  visit(root, 0, []);
  return lines;
}

function rootKey(term: string): string {
  return term.toLowerCase();
}

function ChainRow({
  line,
  selected,
  onSelect,
}: {
  line: Line;
  selected: boolean;
  onSelect: () => void;
}) {
  const { node, level, repeat } = line;
  const outside = node.refers_to.filter((ref) => ref.status === "not_in_pack" && ref.role === "input");
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected || undefined}
        className={clsx(
          "relative flex w-full cursor-pointer items-start gap-2 border-b border-sand py-2 pr-4 text-left transition-colors duration-75",
          selected ? "bg-sand" : "hover:bg-canvas",
        )}
        style={{ paddingLeft: `${1 + level * 1.25}rem` }}
      >
        {selected && <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-accent" />}
        {level > 0 && <CornerDownRight aria-hidden className="mt-0.5 size-3.5 shrink-0 text-subtle" />}
        <span className="min-w-0 flex-1">
          <span className={clsx("text-sm", repeat ? "text-muted" : "font-medium")}>
            {node.term}
          </span>
          {repeat && <span className="ml-1.5 text-xs text-subtle">see above</span>}
          {!repeat && (
            <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
              <span>
                {node.clause}
                {node.source ? `, page ${node.source.page}` : ""}
              </span>
              {node.amended_by && (
                <span className="rounded bg-info-tint px-1.5 py-px font-medium text-info">
                  Amended: {node.amended_by.replace("Amendment No. 1, ", "Amdt 1, ")}
                </span>
              )}
              {outside.map((ref) => (
                <span key={ref.key} className="rounded bg-warn-tint px-1.5 py-px font-medium text-warn">
                  {ref.target}: not in pack
                </span>
              ))}
            </span>
          )}
        </span>
        {!repeat && node.resolved && (
          <span className="numeric shrink-0 pt-0.5 text-right text-[0.8125rem] font-semibold">
            {node.resolved.value}
          </span>
        )}
      </button>
    </li>
  );
}

export function DefinitionsPage() {
  const { state } = useSession();
  const workbench = useWorkbench();
  const { data, isError } = useCasework();
  const [params] = useSearchParams();
  const [selectedKey, setSelectedKey] = useState(params.get("key") ?? "borrowing base");
  const [showAmendment, setShowAmendment] = useState(false);

  if (!state.intakeDone) {
    return <NeedsIntake />;
  }
  if (isError) {
    return <p role="alert" className="text-sm text-danger">The casework run could not be loaded.</p>;
  }
  if (!data || !workbench.data) {
    return <Skeleton className="h-96 w-full" />;
  }

  const defs = data.definitions;
  const nodes = new Map(defs.nodes.map((node) => [node.key, node]));
  const seen = new Set<string>();
  const chains = defs.roots.map((root) => ({ root, lines: chain(rootKey(root), nodes, seen) }));
  const selected = nodes.get(selectedKey) ?? defs.nodes[0];
  const checks = defs.checks;
  const citation = showAmendment && selected.amendment_source ? selected.amendment_source : selected.source;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Nested definitions"
        summary="Credit Agreement, 15 Jan 2026 · Amendment No. 1, effective 1 Mar 2026 · period ending 30 Apr 2026"
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          {
            ok: checks.quotes_found === checks.quotes,
            label: `Quotes verified ${checks.quotes_found}/${checks.quotes}`,
          },
          {
            ok: checks.input_cycles.length === 0,
            label: `Circular inputs ${checks.input_cycles.length} · mutual references ${checks.mutual_references.length}`,
          },
          {
            ok: defs.borrowing_base_reproduced,
            label: defs.borrowing_base_reproduced
              ? "Borrowing base reconciles to engine"
              : "Borrowing base does not reconcile",
          },
          {
            ok: false,
            label: `Not in pack ${defs.not_in_pack.length}`,
          },
        ].map((item) => (
          <Card key={item.label} className="flex items-start gap-2 p-3 text-[0.8125rem]">
            {item.ok ? (
              <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-ok" />
            ) : (
              <FileWarning aria-hidden className="mt-0.5 size-4 shrink-0 text-warn" />
            )}
            {item.label}
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] items-start gap-4">
        <div className="space-y-4">
          {chains.map(({ root, lines }) => (
            <Card key={root} className="overflow-hidden">
              <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
                <GitBranch aria-hidden className="size-4 text-muted" />
                <h2 className="font-semibold">{root}</h2>
                <span className="text-xs text-muted">{lines.length} terms</span>
              </div>
              <ul>
                {lines.map((line, index) => (
                  <ChainRow
                    key={`${line.node.key}-${index}`}
                    line={line}
                    selected={!line.repeat && line.node.key === selected.key}
                    onSelect={() => {
                      setSelectedKey(line.node.key);
                      setShowAmendment(false);
                    }}
                  />
                ))}
              </ul>
            </Card>
          ))}
        </div>

        <div className="sticky top-14 space-y-3">
          <Card className="space-y-3 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <SectionLabel>{selected.clause}</SectionLabel>
                <h2 className="mt-0.5 text-base font-semibold">{selected.term}</h2>
                <p className="mt-1">
                  <ProvenanceChip kind="extracted" detail="quote checked" tip={`“${selected.quote}”`} />
                </p>
              </div>
              {selected.source ? (
                <StatusPill status="approved" label={`Quote found, page ${selected.source.page}`} />
              ) : (
                <StatusPill status="missing" label="Quote not found" />
              )}
            </div>
            <blockquote className="border-l-2 border-stone pl-3 text-[0.8125rem] leading-snug text-muted">
              {selected.quote}
            </blockquote>
            {selected.amended_by && (
              <div className="rounded-md bg-info-tint px-3 py-2 text-[0.8125rem]">
                <p className="font-medium text-info">
                  {selected.amended_by}
                  {selected.amendment_source && `, page ${selected.amendment_source.page}`}
                </p>
                <p className="mt-0.5 text-ink">{selected.amendment_quote}</p>
              </div>
            )}
            {selected.resolved && (
              <div className="rounded-md bg-canvas px-3 py-2 text-[0.8125rem]">
                <p className="flex items-center justify-between gap-3">
                  <span className="font-medium">Resolved value</span>
                  <span className="numeric text-base font-semibold">{selected.resolved.value}</span>
                </p>
                {selected.resolved.rule && (
                  <p className="mt-1 font-mono text-xs leading-snug break-words">
                    {selected.resolved.rule}
                  </p>
                )}
                {selected.resolved.worked && (
                  <p className="numeric mt-1 text-muted">{selected.resolved.worked}</p>
                )}
                {selected.resolved.check !== undefined && (
                  <p className="mt-1 flex items-center gap-1.5 text-xs font-medium text-ok">
                    <CheckCircle2 aria-hidden className="size-3.5" />
                    Reconciles to engine
                  </p>
                )}
              </div>
            )}
            <div>
              <SectionLabel>Relies on</SectionLabel>
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {selected.refers_to.map((ref) => (
                  <li key={ref.key}>
                    <button
                      type="button"
                      disabled={!nodes.has(ref.key)}
                      onClick={() => setSelectedKey(ref.key)}
                      title={
                        {
                          traced: "Traced in this chain",
                          not_in_pack: "A document the pack does not hold",
                          mentioned: "Only mentioned, not needed for the value",
                          untraced: "Not traced",
                        }[ref.status]
                      }
                      className={clsx(
                        "rounded border px-1.5 py-px text-xs",
                        ref.status === "not_in_pack"
                          ? "border-warn/40 bg-warn-tint text-warn"
                          : ref.role === "input"
                            ? "cursor-pointer border-line bg-surface font-medium hover:border-stone"
                            : "border-dashed border-line text-muted",
                      )}
                    >
                      {ref.target}
                      {ref.role === "context" && " (mention)"}
                    </button>
                  </li>
                ))}
                {selected.refers_to.length === 0 && (
                  <li className="text-xs text-muted">None</li>
                )}
              </ul>
            </div>
            {selected.amendment_source && (
              <div className="flex gap-1 text-xs">
                {[false, true].map((amendment) => (
                  <button
                    key={String(amendment)}
                    type="button"
                    onClick={() => setShowAmendment(amendment)}
                    className={clsx(
                      "cursor-pointer rounded-md px-2 py-1",
                      showAmendment === amendment ? "bg-ink text-white" : "bg-sand text-muted",
                    )}
                  >
                    {amendment ? "Amendment" : "Agreement"}
                  </button>
                ))}
              </div>
            )}
          </Card>
          <EvidencePanel citation={citation} documents={workbench.data.documents} />
        </div>
      </div>

      <Card className="p-4 text-[0.8125rem]">
        <SectionLabel>Open items</SectionLabel>
        <ul className="mt-1.5 space-y-1">
          {defs.not_in_pack.map((item) => (
            <li key={item} className="flex gap-2">
              <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0 text-warn" />
              {item}
            </li>
          ))}
          <li className="flex gap-2">
            <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0 text-info" />
            Delinquency Ratio, April: {defs.delinquency.literal.toFixed(2)}% with repossessed
            receivables (per definition) · {defs.delinquency.without_repossessed.toFixed(2)}% without
          </li>
        </ul>
      </Card>
    </div>
  );
}
