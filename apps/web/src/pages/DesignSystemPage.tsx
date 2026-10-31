import { useState } from "react";
import {
  Confidence,
  Kbd,
  ProvenanceChip,
  StatusPill,
  TierBadge,
  type ConfidenceLevel,
  type Provenance,
  type ReviewStatus,
} from "../components/ui/badges";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { Card, Money, SectionLabel, Skeleton } from "../components/ui/layout";
import { Tooltip } from "../components/ui/Tooltip";
import { formatUsd } from "../lib/format";
import type { ReactNode } from "react";

const swatches = [
  ["ink", "bg-ink"],
  ["ink-soft", "bg-ink-soft"],
  ["muted", "bg-muted"],
  ["subtle", "bg-subtle"],
  ["stone", "bg-stone"],
  ["line", "bg-line"],
  ["sand", "bg-sand"],
  ["canvas", "bg-canvas"],
  ["accent", "bg-accent"],
  ["ok", "bg-ok"],
  ["warn", "bg-warn"],
  ["danger", "bg-danger"],
  ["info", "bg-info"],
];

const statuses: ReviewStatus[] = ["approved", "review", "missing", "open", "pending"];
const provenances: Provenance[] = ["ai", "calculated", "derived", "edited", "approved"];
const confidences: ConfidenceLevel[] = ["high", "medium", "low"];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="p-6">
      <SectionLabel>{title}</SectionLabel>
      <div className="mt-4 flex flex-wrap items-center gap-3">{children}</div>
    </Card>
  );
}

export function DesignSystemPage() {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div className="space-y-5">
      <h1 className="text-[1.75rem] font-semibold tracking-tight">Design system</h1>

      <Section title="Colour">
        {swatches.map(([name, swatch]) => (
          <div key={name} className="w-20">
            <div className={`h-12 rounded-md border border-line ${swatch}`} />
            <p className="mt-1 text-xs text-muted">{name}</p>
          </div>
        ))}
      </Section>

      <Section title="Type">
        <div className="space-y-2">
          <p className="text-[2rem] font-semibold tracking-tight">Display, 32 semibold</p>
          <p className="text-[0.9375rem]">Body, 15 regular</p>
          <p className="text-sm text-muted">Supporting, 14 muted</p>
          <p className="font-mono text-sm">days_past_due &lt;= 30</p>
        </div>
      </Section>

      <Section title="Figures align on the digit">
        <div className="text-right">
          <p>
            <Money value={formatUsd(250_000_000)} />
          </p>
          <p>
            <Money value={formatUsd(1_111_111)} />
          </p>
          <p>
            <Money value={formatUsd(-75_000)} />
          </p>
        </div>
      </Section>

      <Section title="Buttons">
        <Button>Approve</Button>
        <Button variant="secondary">Edit</Button>
        <Button variant="secondary">Send to queue</Button>
        <Button variant="ghost">Cancel</Button>
        <Button disabled>Disabled</Button>
        <Button size="sm">Small</Button>
        <Button size="lg">Large</Button>
      </Section>

      <Section title="Review status">
        {statuses.map((status) => (
          <StatusPill key={status} status={status} />
        ))}
      </Section>

      <Section title="Who produced a value">
        {provenances.map((kind) => (
          <ProvenanceChip key={kind} kind={kind} />
        ))}
      </Section>

      <Section title="Confidence and tier">
        {confidences.map((level) => (
          <Confidence key={level} level={level} />
        ))}
        <TierBadge tier={1} />
        <TierBadge tier={2} />
        <TierBadge tier={3} />
      </Section>

      <Section title="Overlays and loading">
        <Tooltip content="Tooltips explain, and never carry the only copy of a fact.">
          <Button variant="secondary">Hover for tooltip</Button>
        </Tooltip>
        <Button variant="secondary" onClick={() => setDialogOpen(true)}>
          Open dialog
        </Button>
        <Kbd>A</Kbd>
        <Skeleton className="h-4 w-40" />
      </Section>

      <Dialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title="Approve advance rate?"
        description="This Tier 1 value needs your explicit approval."
      >
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDialogOpen(false)}>
            Cancel
          </Button>
          <Button onClick={() => setDialogOpen(false)}>Approve</Button>
        </div>
      </Dialog>
    </div>
  );
}
