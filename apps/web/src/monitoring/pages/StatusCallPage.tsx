import clsx from "clsx";
import { CalendarClock, Code2, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";
import { Card, SectionLabel, Skeleton } from "../../components/ui/layout";
import { Badge, PageTitle, Person, when } from "../ui";
import { useCycle, type ClientId, type Source } from "../cycle";
import { FacilityTag, Filled, NoAiBadge, SourcePanel } from "../parts";

export function StatusCallPage() {
  const { data: cycle } = useCycle();
  const [clientId, setClientId] = useState<ClientId>("calderwood");
  const [source, setSource] = useState<Source | null | undefined>(undefined);
  if (!cycle) {
    return <Skeleton className="h-96 w-full" />;
  }
  const client = cycle.clients.find((c) => c.id === clientId)!;
  const brief = cycle.briefs.find((b) => b.client === clientId)!;
  const facilities = cycle.facilities.filter((f) => f.client === clientId);
  const clean = brief.unknown_placeholders.length === 0 && brief.numbers_in_text.length === 0;
  const firstSourced = Object.values(brief.figures).find((f) => f.source)?.source ?? null;
  return (
    <>
      <PageTitle title="Status calls" meta={`Week of ${when(cycle.cycle.as_of)}`} />
      <div role="tablist" aria-label="Client" className="mb-3 flex items-center gap-1 border-b border-line">
        {cycle.clients.map((c) => (
          <button
            key={c.id}
            type="button"
            role="tab"
            aria-selected={clientId === c.id}
            onClick={() => {
              setClientId(c.id);
              setSource(undefined);
            }}
            className={clsx("-mb-px flex h-9 cursor-pointer items-center gap-2 border-b-2 px-3 text-[0.8125rem] font-medium", clientId === c.id ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink")}
          >
            {c.name}
            {!c.ai_permitted && <NoAiBadge compact />}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-3">
        <Card className="p-4">
          <div className="flex items-start justify-between gap-4 border-b border-sand pb-2.5">
            <div>
              <SectionLabel>Status call · {client.status_call}</SectionLabel>
              <h2 className="mt-0.5 text-base font-semibold">{client.name}</h2>
              <p className="mt-1 flex flex-wrap items-center gap-1.5 text-sm text-muted">
                {facilities.map((f) => (
                  <FacilityTag key={f.id} id={f.id} name={f.name} />
                ))}
              </p>
            </div>
            {brief.ai ? (
              <Badge tone="info" icon={<Sparkles aria-hidden className="size-3" />}>
                Drafted
              </Badge>
            ) : (
              <Badge tone="neutral" icon={<Code2 aria-hidden className="size-3" />}>
                Template
              </Badge>
            )}
          </div>
          <p className="mt-3 text-[0.875rem] leading-relaxed font-medium">
            <Filled text={brief.opening} figures={brief.figures} onSource={setSource} />
          </p>
          {brief.sections.map((section) => (
            <section key={section.heading} className="mt-3">
              <h3 className="text-[0.8125rem] font-semibold">{section.heading}</h3>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-5 text-[0.8125rem] leading-relaxed">
                {section.points.map((point) => (
                  <li key={point}>
                    <Filled text={point} figures={brief.figures} onSource={setSource} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </Card>
        <div className="space-y-3 self-start">
          <Card className="p-3">
            <SectionLabel>Attendees</SectionLabel>
            <ul className="mt-2 space-y-1.5 text-[0.8125rem]">
              <li>
                <Person name={client.contact.name} sub={client.contact.role} />
              </li>
              <li>
                <Person name={client.client_contact.name} sub={client.client_contact.role} />
              </li>
              <li className="flex items-center gap-1.5 text-xs text-muted">
                <CalendarClock aria-hidden className="size-3.5" />
                {client.status_call}
              </li>
            </ul>
          </Card>
          <Card className="p-3">
            <SectionLabel>Checks</SectionLabel>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
              <div>
                <dt className="text-muted">Figures</dt>
                <dd className="numeric font-semibold">{Object.keys(brief.figures).length}</dd>
              </div>
              <div>
                <dt className="text-muted">Number check</dt>
                <dd className={clsx("flex items-center gap-1 font-semibold", clean ? "text-ok" : "text-danger")}>
                  <ShieldCheck aria-hidden className="size-3.5" />
                  {clean ? "Passed" : "Failed"}
                </dd>
              </div>
            </dl>
          </Card>
          <SourcePanel source={source === undefined ? firstSourced : source} emptyText="Calculated figure; no source page." />
        </div>
      </div>
    </>
  );
}
