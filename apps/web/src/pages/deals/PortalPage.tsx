/* What a lender contact sees: queries to answer, released reports, the weekly brief and alerts. */
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { FormMessage, TextInput, useForm, when } from "../../components/deals/parts";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/layout";
import { api, post, useDealAction } from "../../lib/deals";
import { usePersona } from "../../lib/persona";
import { Badge, Panel, PageTitle, RecordId } from "../../monitoring/ui";

interface Portal {
  client_name: string;
  queries: { case_id: number | null; case: string; facility: string; ref: string; title: string; question: string; asked_by: string; asked_at: string; answer: string | null; status: "waiting" | "answered"; scripted: boolean }[];
  reports: { facility: string; period: string; released_at: string; text: string[]; download: string; scripted: boolean }[];
  brief: { opening: string; sections: { heading: string; points: string[] }[] } | null;
  alerts: { id: number; request: string; summary: string | null; status: string; requestedAt: string }[];
  alert_examples?: string[];
}

function Query({ q, refresh }: { q: Portal["queries"][number]; refresh: () => void }) {
  const [text, setText] = useState("");
  const form = useForm();
  const action = useDealAction<unknown>();
  const answer = () =>
    void form.run(async () => {
      if (q.scripted) {
        await post("/api/session/events", { type: "record-answer", actor: "analyst", payload: { ids: [q.ref] } });
      } else {
        await action.mutateAsync(() => post(`/api/deals/queries/${q.case_id}/${q.ref}/answer`, { text }));
      }
      refresh();
    });
  return (
    <li className="border-b border-sand py-3 last:border-0">
      <div className="flex items-center gap-2">
        <RecordId>{q.ref}</RecordId>
        <span className="text-[0.8125rem] font-medium">{q.facility}</span>
        <Badge tone={q.status === "waiting" ? "warn" : "ok"}>{q.status === "waiting" ? "Waiting on you" : "Answered"}</Badge>
        <span className="ml-auto text-xs text-muted">{when(q.asked_at)}</span>
      </div>
      <p className="mt-1 text-[0.8125rem]">{q.title}</p>
      {q.question && <p className="mt-0.5 text-xs text-muted">{q.question}</p>}
      {q.answer && <p className="mt-1 rounded bg-canvas px-2 py-1 text-xs">Your answer: {q.answer}</p>}
      {q.status === "waiting" && (
        <form
          className="mt-2 flex items-start gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            answer();
          }}
        >
          {!q.scripted && (
            <div className="flex-1">
              <TextInput id={`answer-${q.ref}`} aria-label="Answer" placeholder="Your answer" value={text} onChange={(e) => setText(e.target.value)} invalid={Boolean(form.errors.text)} />
            </div>
          )}
          <Button size="sm" type="submit" disabled={form.busy || (!q.scripted && !text.trim())}>
            {q.scripted ? "Send our answer" : "Send answer"}
          </Button>
        </form>
      )}
      <FormMessage message={form.message} />
    </li>
  );
}

export function PortalPage() {
  const { persona } = usePersona();
  const { data, refetch } = useQuery({ queryKey: ["portal", persona?.id], queryFn: () => api<Portal>("/api/portal"), enabled: persona?.role === "client" });
  if (!persona || persona.role !== "client") {
    return <p className="text-sm text-muted">The client portal is for client users.</p>;
  }
  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }
  const waiting = data.queries.filter((q) => q.status === "waiting").length;
  return (
    <>
      <PageTitle title={data.client_name || persona.title} meta={`${persona.name} · ${waiting} queries waiting · ${data.reports.length} released reports`} />
      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title="Queries from Oxane">
          {data.queries.length === 0 ? <p className="text-xs text-muted">No queries.</p> : <ul>{data.queries.map((q) => <Query key={`${q.case}-${q.ref}`} q={q} refresh={() => void refetch()} />)}</ul>}
        </Panel>
        <Panel title="Released reports">
          {data.reports.length === 0 ? (
            <p className="text-xs text-muted">No reports released yet.</p>
          ) : (
            <ul className="space-y-3">
              {data.reports.map((r) => (
                <li key={`${r.facility}-${r.period}`} className="border-b border-sand pb-3 last:border-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[0.8125rem] font-medium">{r.facility}</span>
                    <span className="text-xs text-muted">{r.period} · released {when(r.released_at)}</span>
                    <a href={r.download} className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-info hover:underline">
                      <Download aria-hidden className="size-3.5" />
                      Workbook
                    </a>
                  </div>
                  {r.text.slice(0, 3).map((p, i) => (
                    <p key={i} className="mt-1 text-xs">
                      {p}
                    </p>
                  ))}
                </li>
              ))}
            </ul>
          )}
        </Panel>
        {data.brief && (
          <Panel title="Weekly status call">
            <p className="text-[0.8125rem]">{data.brief.opening}</p>
            {data.brief.sections.map((s) => (
              <div key={s.heading} className="mt-2">
                <p className="text-xs font-semibold">{s.heading}</p>
                <ul className="ml-4 list-disc text-xs">
                  {s.points.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              </div>
            ))}
          </Panel>
        )}
        {data.alerts.length > 0 && (
          <Panel title="Your alert requests">
            <ul className="space-y-1 text-xs">
              {data.alerts.map((a) => (
                <li key={a.id} className="flex gap-2">
                  <Badge tone={a.status === "live" ? "ok" : "info"}>{a.status === "live" ? "Live" : "Awaiting approval"}</Badge>
                  {a.summary ?? a.request}
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </>
  );
}
