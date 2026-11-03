import clsx from "clsx";
import { ArrowRight, Bot, Calculator, CheckCircle2, Link2, Lock, Send, ShieldCheck, UserRoundCheck } from "lucide-react";
import { Fragment, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { PageHeader } from "../../components/ui/PageHeader";
import { Tooltip } from "../../components/ui/Tooltip";
import { Refusal, useActor, useCycle, useCycleAction, useCycleSession, type FacilityId, type LenderPack, type Source } from "../cycle";
import { FacilityTag, SourcePanel } from "../parts";

/** Draft text with each {{placeholder}} replaced by the code's figure, linked to its source. */
function Filled({ text, pack, onSource }: { text: string; pack: LenderPack; onSource: (s: Source | null) => void }) {
  const parts = text.split(/(\{\{\w+\}\})/);
  return (
    <>
      {parts.map((part, index) => {
        const key = part.match(/^\{\{(\w+)\}\}$/)?.[1];
        const figure = key ? pack.figures[key] : undefined;
        if (!figure) {
          return <Fragment key={index}>{part}</Fragment>;
        }
        return (
          <Tooltip key={index} content={`${figure.means}. Inserted by code${figure.source ? "; click for its source" : ""}.`}>
            <button
              type="button"
              onClick={() => onSource(figure.source)}
              className={clsx(
                "numeric inline-flex cursor-pointer items-center gap-0.5 rounded bg-accent/30 px-1 font-semibold underline decoration-ink/40 decoration-dotted underline-offset-2 hover:bg-accent/60",
              )}
            >
              {figure.value}
              {figure.source && <Link2 aria-hidden className="size-3" />}
            </button>
          </Tooltip>
        );
      })}
    </>
  );
}

export function PackPage() {
  const { data: cycle } = useCycle();
  const { data: session } = useCycleSession();
  const { actor, setActor } = useActor();
  const action = useCycleAction();
  const navigate = useNavigate();
  const [tab, setTab] = useState<FacilityId>("bramble");
  const [source, setSource] = useState<Source | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const pack = cycle.packs.find((p) => p.facility === tab)!;
  const facility = cycle.facilities.find((f) => f.id === tab)!;
  const approved = session?.packs[tab];
  const pending = session?.pending[tab] ?? [];
  const clean = pack.unknown_placeholders.length === 0 && pack.numbers_in_text.length === 0;
  const approve = () => {
    setError(null);
    action.mutate(
      { type: "approve-pack", payload: { facility: tab } },
      { onError: (e) => setError(e instanceof Refusal ? e.message : "The approval could not be saved.") },
    );
  };
  const firstSourced = Object.values(pack.figures).find((f) => f.source)?.source ?? null;
  return (
    <>
      <PageHeader
        title="Lender pack"
        summary="One pack per facility for Calderwood Bank. The AI drafts the words; code inserts every figure with its source; a second analyst approves and sends."
        actions={
          <Button onClick={() => navigate("/monitoring/results")}>
            Scorecard
            <ArrowRight aria-hidden className="size-4" />
          </Button>
        }
      />
      <div role="tablist" aria-label="Facility" className="mb-5 flex items-center gap-1 border-b border-line">
        {cycle.facilities.map((f) => (
          <button
            key={f.id}
            type="button"
            role="tab"
            aria-selected={tab === f.id}
            onClick={() => {
              setTab(f.id);
              setSource(undefined);
              setError(null);
            }}
            className={clsx("-mb-px flex h-11 cursor-pointer items-center gap-2 border-b-2 px-3 text-sm font-medium", tab === f.id ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink")}
          >
            {f.name}
            {session?.packs[f.id] ? <CheckCircle2 aria-label="Approved" className="size-4 text-ok" /> : <span className="text-xs text-muted">Draft</span>}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-5">
        <Card className="p-6">
          <div className="flex items-start justify-between gap-4 border-b border-sand pb-4">
            <div>
              <SectionLabel>Monthly monitoring pack · May 2026</SectionLabel>
              <h2 className="mt-1 text-xl font-semibold">{facility.name}</h2>
              <p className="mt-0.5 flex items-center gap-2 text-sm text-muted">
                <FacilityTag id={facility.id} name={facility.asset_class} />
                {facility.role} for {cycle.lender}
              </p>
            </div>
            {approved ? (
              <span className="inline-flex h-7 items-center gap-1.5 rounded-full bg-ok-tint px-3 text-sm font-medium text-ok">
                <Send aria-hidden className="size-3.5" />
                Approved and sent
              </span>
            ) : (
              <span className="inline-flex h-7 items-center gap-1.5 rounded-full bg-sand px-3 text-sm font-medium text-muted">
                <Bot aria-hidden className="size-3.5" />
                AI draft
              </span>
            )}
          </div>
          <p className="mt-4 text-[0.9375rem] leading-relaxed font-medium">
            <Filled text={pack.summary} pack={pack} onSource={setSource} />
          </p>
          {pack.sections.map((section) => (
            <section key={section.heading} className="mt-5">
              <h3 className="text-sm font-semibold">{section.heading}</h3>
              <p className="mt-1 text-sm leading-relaxed">
                <Filled text={section.text} pack={pack} onSource={setSource} />
              </p>
            </section>
          ))}
        </Card>

        <div className="space-y-4">
          <Card className="p-5">
            <SectionLabel>Controls on this draft</SectionLabel>
            <ul className="mt-3 space-y-2 text-sm">
              <li className="flex items-start gap-2">
                <Calculator aria-hidden className="mt-0.5 size-4 shrink-0 text-muted" />
                <span>
                  <strong className="numeric">{Object.keys(pack.figures).length} figures</strong> inserted by code from the checks, each with its source where one exists.
                </span>
              </li>
              <li className={clsx("flex items-start gap-2", clean ? "text-ok" : "text-danger")}>
                <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0" />
                <span className="text-ink">
                  {clean ? "No number in the text was written by the model." : `The model wrote figures itself: ${[...pack.numbers_in_text, ...pack.unknown_placeholders].join(", ")}.`}
                </span>
              </li>
              <li className="flex items-start gap-2">
                <UserRoundCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-muted" />
                <span>A second analyst approves. Whoever prepared the cycle cannot.</span>
              </li>
            </ul>
            <div className="mt-4 border-t border-sand pt-4">
              {approved ? (
                <p className="flex items-center gap-2 text-sm font-medium text-ok">
                  <Lock aria-hidden className="size-4" />
                  Approved by {approved.by} and sent to {cycle.lender}
                </p>
              ) : (
                <>
                  {pending.length > 0 && (
                    <p className="mb-3 text-sm text-warn">
                      {pending.length} finding{pending.length === 1 ? "" : "s"} still to decide in triage.
                    </p>
                  )}
                  <div className="flex items-center justify-between gap-3">
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={actor === "approver"} onChange={(e) => setActor(e.target.checked ? "approver" : "analyst")} className="size-4 accent-ink" />
                      Act as second analyst
                    </label>
                    <Button onClick={approve} disabled={action.isPending}>
                      <Send aria-hidden className="size-4" />
                      Approve and send
                    </Button>
                  </div>
                  {error && (
                    <p role="alert" className="mt-2 text-sm text-danger">
                      {error}
                    </p>
                  )}
                </>
              )}
            </div>
          </Card>
          <SourcePanel source={source === undefined ? firstSourced : source} emptyText="This figure is calculated; it has no page to show." />
          <Card className="p-5">
            <SectionLabel>Audit log</SectionLabel>
            <ol className="mt-2 max-h-56 space-y-1.5 overflow-auto text-sm">
              {[...(session?.audit ?? [])].reverse().map((entry, index) => (
                <li key={`${entry.at}-${index}`} className="flex gap-3">
                  <span className="numeric w-16 shrink-0 text-xs text-muted">{new Date(entry.at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</span>
                  <span>
                    <span className="font-medium">{entry.actor}</span> · {entry.action}
                    {entry.reason && <span className="text-muted"> ({entry.reason})</span>}
                  </span>
                </li>
              ))}
            </ol>
            <p className={clsx("mt-2 text-xs", session?.chainIntact ? "text-ok" : "text-danger")}>
              {session?.chainIntact ? "Hash chain intact" : "Hash chain broken"} · head {session?.chainHead.slice(0, 12)}
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}
