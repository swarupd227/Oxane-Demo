import clsx from "clsx";
import {
  ArrowRight,
  Bell,
  CheckCheck,
  ClipboardCheck,
  Eye,
  MessageSquareText,
  Scale,
  Send,
  ShieldCheck,
  SquareCheckBig,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { FormMessage, TextInput, useForm, when } from "../../components/deals/parts";
import { Skeleton } from "../../components/ui/layout";
import { Button } from "../../components/ui/Button";
import { post, useDealAction, useWork, type WorkItem } from "../../lib/deals";
import { usePersona } from "../../lib/persona";
import { Avatar, Kpis, Panel, PageTitle, RecordId } from "../../monitoring/ui";

const KIND: Record<string, { label: string; icon: LucideIcon; tone: string }> = {
  approval: { label: "Approval", icon: ShieldCheck, tone: "bg-accent-tint text-accent" },
  query: { label: "Client query", icon: MessageSquareText, tone: "bg-info-tint text-info" },
  expert: { label: "Expert judgement", icon: Scale, tone: "bg-[#f4f3ff] text-[#5925dc]" },
  qc: { label: "Independent QC", icon: ClipboardCheck, tone: "bg-warn-tint text-warn" },
  release: { label: "Release", icon: Send, tone: "bg-ok-tint text-ok" },
  review: { label: "Review", icon: Eye, tone: "bg-sand text-muted" },
  work: { label: "Work", icon: SquareCheckBig, tone: "bg-sand text-muted" },
  notice: { label: "Notice", icon: Bell, tone: "bg-sand text-muted" },
};

function kindOf(item: WorkItem) {
  return KIND[item.kind] ?? { label: item.kind, icon: SquareCheckBig, tone: "bg-sand text-muted" };
}

function age(item: WorkItem): string {
  const hours = Math.round(item.age_hours);
  return hours < 1 ? "just now" : hours < 48 ? `${hours}h` : `${Math.round(hours / 24)}d`;
}

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

function TaskCard({ item }: { item: WorkItem }) {
  const action = useDealAction<unknown>();
  const form = useForm();
  const [note, setNote] = useState("");
  const kind = kindOf(item);
  const Icon = kind.icon;
  const closable = ["notice", "review", "expert"].includes(item.kind);
  return (
    <li
      className={clsx(
        "rounded-xl border bg-surface p-4 shadow-card transition-colors",
        item.overdue ? "border-danger/30" : "border-line hover:border-stone",
      )}
    >
      <div className="flex items-start gap-3">
        <span aria-hidden className={clsx("grid size-9 shrink-0 place-items-center rounded-lg", kind.tone)}>
          <Icon className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-subtle">
            <span className="font-medium text-muted">{kind.label}</span>
            <span aria-hidden>·</span>
            <RecordId>{item.ref}</RecordId>
          </div>
          <Link to={item.link || "/work"} className="mt-0.5 block text-sm font-semibold text-ink hover:text-accent-strong">
            {item.title}
          </Link>
          {item.detail && <p className="mt-1 text-[0.8125rem] leading-relaxed text-muted">{item.detail}</p>}
          {item.note && <p className="mt-1 text-xs text-subtle">Note: {item.note}</p>}
          <div className="mt-2.5 flex items-center gap-2 text-xs text-subtle">
            {item.from_name ? (
              <>
                <Avatar name={item.from_name} />
                <span>
                  From <span className="font-medium text-muted">{item.from_name}</span> · {when(item.created_at)}
                </span>
              </>
            ) : (
              <span>Raised {when(item.created_at)}</span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <span
            className={clsx(
              "numeric inline-flex h-[1.375rem] items-center rounded-full px-2 text-[0.6875rem] font-medium whitespace-nowrap",
              item.overdue ? "bg-danger-tint text-danger" : "bg-sand text-muted",
            )}
          >
            {item.overdue ? `Overdue · ${age(item)}` : age(item)}
          </span>
          {!closable && (
            <Link
              to={item.link || "/work"}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent px-3 text-[0.8125rem] font-medium text-white shadow-[0_1px_2px_rgb(16_24_40/0.05)] transition-colors hover:bg-accent-strong"
            >
              Open
              <ArrowRight aria-hidden className="size-3.5" />
            </Link>
          )}
        </div>
      </div>
      {closable && (
        <form
          className="mt-3 flex items-start gap-2 border-t border-line pt-3 pl-12"
          onSubmit={(event) => {
            event.preventDefault();
            void form.run(() => action.mutateAsync(() => post(`/api/work/${item.id}/complete`, { note: note || null })));
          }}
        >
          {item.kind === "expert" && (
            <div className="flex-1">
              <TextInput
                id={`note-${item.id}`}
                placeholder="Decision and reasoning"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                invalid={Boolean(form.message)}
                aria-label="Decision and reasoning"
              />
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

/** A compact history: one line per item, newest first. */
function Timeline({ items, done }: { items: WorkItem[]; done?: boolean }) {
  if (items.length === 0) {
    return <p className="text-[0.8125rem] text-subtle">Nothing yet.</p>;
  }
  return (
    <ol className="relative space-y-3 before:absolute before:top-1.5 before:bottom-1.5 before:left-[0.3125rem] before:w-px before:bg-line">
      {items.slice(0, 8).map((item) => {
        const kind = kindOf(item);
        return (
          <li key={item.id} className="relative pl-5">
            <span aria-hidden className={clsx("absolute top-1.5 left-0 size-2.5 rounded-full ring-2 ring-surface", done ? "bg-ok" : "bg-accent")} />
            <Link to={item.link || "/work"} className="block truncate text-[0.8125rem] font-medium text-ink hover:text-accent-strong" title={item.title}>
              {item.title}
            </Link>
            <p className="mt-0.5 truncate text-xs text-subtle">
              {kind.label}
              {done
                ? item.done_at && ` · done ${when(item.done_at)}${item.done_by_name ? ` by ${item.done_by_name}` : ""}`
                : ` · with ${item.assignee_name || item.role_label} · ${when(item.created_at)}`}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

function Workload({ team }: { team: { persona: string; name: string; open: number }[] }) {
  const top = Math.max(1, ...team.map((t) => t.open));
  return (
    <ul className="space-y-2.5">
      {team.map((t) => (
        <li key={t.persona} className="flex items-center gap-2.5">
          <Avatar name={t.name} />
          <span className="w-28 shrink-0 truncate text-[0.8125rem] text-ink-soft">{t.name}</span>
          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-sand">
            <span className="block h-full rounded-full bg-accent" style={{ width: `${(t.open / top) * 100}%` }} />
          </span>
          <span className="numeric w-6 text-right text-[0.8125rem] font-medium text-ink">{t.open}</span>
        </li>
      ))}
    </ul>
  );
}

export function MyWorkPage() {
  const { persona } = usePersona();
  const { data, isPending } = useWork(Boolean(persona));
  if (isPending || !data || !persona) {
    return <Skeleton className="h-96 w-full" />;
  }
  const overdue = data.waiting.filter((w) => w.overdue).length;
  const waiting = [...data.waiting].sort((a, b) => Number(b.overdue) - Number(a.overdue) || b.age_hours - a.age_hours);
  return (
    <>
      <PageTitle title={`${greeting()}, ${persona.name.split(" ")[0]}`} meta={`${persona.role_label} · ${data.waiting.length ? `${data.waiting.length} waiting on you` : "nothing waiting on you"}`} />
      <Kpis
        items={[
          { label: "Waiting on you", value: data.waiting.length, tone: data.waiting.length ? "warn" : undefined },
          { label: "Overdue", value: overdue, tone: overdue ? "danger" : undefined },
          { label: "Handed off", value: data.handed_off.length },
          { label: "Done recently", value: data.done.length, tone: data.done.length ? "ok" : undefined },
        ]}
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <section aria-labelledby="waiting-heading">
          <h2 id="waiting-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
            Waiting on you
            <span className="numeric rounded-full bg-sand px-2 text-xs font-medium text-muted">{data.waiting.length}</span>
          </h2>
          {waiting.length === 0 ? (
            <div className="flex flex-col items-center rounded-xl border border-dashed border-line bg-surface px-6 py-14 text-center">
              <span aria-hidden className="grid size-11 place-items-center rounded-full bg-ok-tint text-ok">
                <CheckCheck className="size-5" />
              </span>
              <p className="mt-3 text-sm font-semibold text-ink">You're all caught up</p>
              <p className="mt-1 max-w-sm text-[0.8125rem] text-subtle">New hand-offs appear here as soon as someone passes work to you.</p>
            </div>
          ) : (
            <ul className="space-y-3">
              {waiting.map((item) => (
                <TaskCard key={item.id} item={item} />
              ))}
            </ul>
          )}
        </section>
        <div className="space-y-4">
          {data.team && (
            <Panel title="Team workload" meta="open items">
              <Workload team={data.team} />
            </Panel>
          )}
          <Panel title="Handed off by you">
            <Timeline items={data.handed_off} />
          </Panel>
          <Panel title="Recently done">
            <Timeline items={data.done} done />
          </Panel>
        </div>
      </div>
    </>
  );
}
