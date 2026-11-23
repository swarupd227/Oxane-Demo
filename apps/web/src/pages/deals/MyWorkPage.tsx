import clsx from "clsx";
import { useState } from "react";
import { Link } from "react-router-dom";
import { FormMessage, TextInput, useForm, when } from "../../components/deals/parts";
import { Skeleton } from "../../components/ui/layout";
import { Button } from "../../components/ui/Button";
import { post, useDealAction, useWork, type WorkItem } from "../../lib/deals";
import { usePersona } from "../../lib/persona";
import { Badge, Panel, PageTitle, RecordId } from "../../monitoring/ui";

const KIND: Record<string, string> = {
  approval: "Approval",
  query: "Client query",
  expert: "Expert judgement",
  qc: "Independent QC",
  release: "Release",
  review: "Review",
  work: "Work",
  notice: "Notice",
};

function Age({ item }: { item: WorkItem }) {
  const hours = Math.round(item.age_hours);
  return (
    <span className={clsx("numeric whitespace-nowrap", item.overdue ? "font-semibold text-danger" : "text-muted")}>
      {hours < 48 ? `${hours}h` : `${Math.round(hours / 24)}d`}
      {item.overdue && " · overdue"}
    </span>
  );
}

function Row({ item, done }: { item: WorkItem; done?: boolean }) {
  const action = useDealAction<unknown>();
  const form = useForm();
  const [note, setNote] = useState("");
  const closable = !done && ["notice", "review", "expert"].includes(item.kind);
  return (
    <li className="border-b border-sand py-2.5 last:border-0">
      <div className="flex items-start gap-3">
        <RecordId>{item.ref}</RecordId>
        <div className="min-w-0 flex-1">
          <Link to={item.link || "/work"} className="text-[0.8125rem] font-medium hover:underline">
            {item.title}
          </Link>
          <p className="text-xs text-muted">
            {KIND[item.kind] ?? item.kind}
            {item.from_name && ` · handed over by ${item.from_name} · ${when(item.created_at)}`}
            {done && item.done_at && ` · done ${when(item.done_at)} by ${item.done_by_name}`}
            {!done && !item.from_name && ` · ${when(item.created_at)}`}
          </p>
          {item.detail && <p className="mt-0.5 text-xs">{item.detail}</p>}
          {item.note && <p className="mt-0.5 text-xs text-muted">Note: {item.note}</p>}
        </div>
        {!done && <Age item={item} />}
      </div>
      {closable && (
        <form
          className="mt-2 flex items-start gap-2 pl-20"
          onSubmit={(event) => {
            event.preventDefault();
            void form.run(() => action.mutateAsync(() => post(`/api/work/${item.id}/complete`, { note: note || null })));
          }}
        >
          {item.kind === "expert" && (
            <div className="flex-1">
              <TextInput id={`note-${item.id}`} placeholder="Decision and reasoning" value={note} onChange={(e) => setNote(e.target.value)} invalid={Boolean(form.message)} aria-label="Decision and reasoning" />
              <FormMessage message={form.message} />
            </div>
          )}
          <Button size="sm" variant={item.kind === "expert" ? "primary" : "secondary"} type="submit" disabled={form.busy}>
            {item.kind === "expert" ? "Record decision" : "Mark done"}
          </Button>
        </form>
      )}
    </li>
  );
}

export function MyWorkPage() {
  const { persona } = usePersona();
  const { data, isPending } = useWork(Boolean(persona));
  if (isPending || !data || !persona) {
    return <Skeleton className="h-96 w-full" />;
  }
  const overdue = data.waiting.filter((w) => w.overdue).length;
  return (
    <>
      <PageTitle
        title="My work"
        meta={`${persona.name} · ${persona.role_label} · ${data.waiting.length} waiting on you${overdue ? ` · ${overdue} overdue` : ""}`}
      />
      <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel title="Waiting on you" meta={<Badge tone={data.waiting.length ? "warn" : "ok"}>{data.waiting.length}</Badge>}>
          {data.waiting.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted">Nothing is waiting on you.</p>
          ) : (
            <ul>{data.waiting.map((item) => <Row key={item.id} item={item} />)}</ul>
          )}
        </Panel>
        <div className="space-y-3">
          {data.team && (
            <Panel title="Team workload">
              <table className="w-full text-xs">
                <tbody>
                  {data.team.map((t) => (
                    <tr key={t.persona} className="border-b border-sand last:border-0">
                      <td className="py-1">{t.name}</td>
                      <td className="numeric py-1 text-right font-medium">{t.open}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
          <Panel title="Handed off by you">
            {data.handed_off.length === 0 ? <p className="text-xs text-muted">None yet.</p> : <ul>{data.handed_off.map((item) => <Row key={item.id} item={item} done />)}</ul>}
          </Panel>
          <Panel title="Recently done">
            {data.done.length === 0 ? <p className="text-xs text-muted">None yet.</p> : <ul>{data.done.map((item) => <Row key={item.id} item={item} done />)}</ul>}
          </Panel>
        </div>
      </div>
    </>
  );
}
