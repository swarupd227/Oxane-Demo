import { Command } from "cmdk";
import { Presentation, RotateCcw, Type } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCasework } from "../../lib/casework";
import { casePath, useCases } from "../../lib/cases";
import { usePresenterMode } from "../../lib/presenter";
import { sections } from "../../lib/scenes";
import { useSession } from "../../lib/session";
import { useWorkbench } from "../../lib/workbench";

const itemClass =
  "flex h-9 cursor-pointer items-center gap-3 rounded-md px-3 text-[0.8125rem] text-ink data-[selected=true]:bg-sand";

const groupHeadingClass =
  "[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[0.6875rem] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-muted [&_[cmdk-group-heading]]:uppercase";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  largeText: boolean;
  onToggleLargeText: () => void;
}

function Tag({ children }: { children: string }) {
  return <span className="numeric w-16 shrink-0 font-mono text-xs text-muted">{children}</span>;
}

export function CommandPalette({ open, onOpenChange, largeText, onToggleLargeText }: CommandPaletteProps) {
  const navigate = useNavigate();
  const { state, dispatch } = useSession();
  const presenter = usePresenterMode();
  const { data: workbench } = useWorkbench();
  const { data: casework } = useCasework();
  const { data: pipeline } = useCases();
  const [search, setSearch] = useState("");
  const searching = search.trim().length > 0;
  const loaded = state.intakeDone;

  function run(action: () => void) {
    onOpenChange(false);
    setSearch("");
    action();
  }

  const exceptions = loaded ? [...(workbench?.exceptions ?? []), ...state.heldItems] : [];

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Search"
      // Exact matching, so a typed command can never land on a look-alike record.
      filter={(value, typed) => (value.toLowerCase().includes(typed.toLowerCase()) ? 1 : 0)}
      overlayClassName="fixed inset-0 z-40 bg-ink/40"
      contentClassName="fixed top-[14vh] left-1/2 z-50 w-[40rem] max-w-[calc(100vw-2rem)] -translate-x-1/2 overflow-hidden rounded-xl border border-line bg-surface shadow-overlay"
    >
      <Command.Input
        value={search}
        onValueChange={setSearch}
        placeholder="Search terms, exceptions, queries, cases"
        className="h-11 w-full border-b border-line bg-transparent px-4 text-sm outline-none placeholder:text-muted focus-visible:shadow-none"
      />
      <Command.List className="max-h-[26rem] overflow-y-auto p-2">
        <Command.Empty className="px-3 py-6 text-center text-sm text-muted">No results.</Command.Empty>
        <Command.Group heading="Go to" className={groupHeadingClass}>
          {[{ path: "/cases", label: "Onboarding cases" }, ...sections.flatMap((section) =>
            section.children.length ? section.children : [section])].map((item) => (
            <Command.Item
              key={item.path + item.label}
              value={`go ${item.label}`}
              className={itemClass}
              onSelect={() => run(() => navigate(item.path))}
            >
              {item.label}
            </Command.Item>
          ))}
        </Command.Group>
        {searching && (
          <>
            <Command.Group heading="Terms" className={groupHeadingClass}>
              {loaded &&
                workbench?.terms.map((term) => (
                  <Command.Item
                    key={term.name}
                    value={`term ${term.name} ${term.value} ${term.clause}`}
                    className={itemClass}
                    onSelect={() => run(() => navigate(`/terms?term=${encodeURIComponent(term.name)}`))}
                  >
                    <Tag>{`Tier ${term.tier}`}</Tag>
                    <span className="min-w-0 flex-1 truncate">{term.name}</span>
                    <span className="max-w-56 truncate text-xs text-muted">{term.value}</span>
                  </Command.Item>
                ))}
              {loaded &&
                casework?.definitions.nodes.map((node) => (
                  <Command.Item
                    key={`def-${node.key}`}
                    value={`definition ${node.term} ${node.clause}`}
                    className={itemClass}
                    onSelect={() => run(() => navigate(`/definitions?key=${encodeURIComponent(node.key)}`))}
                  >
                    <Tag>Defn</Tag>
                    <span className="min-w-0 flex-1 truncate">{node.term}</span>
                    <span className="truncate text-xs text-muted">{node.clause}</span>
                  </Command.Item>
                ))}
            </Command.Group>
            <Command.Group heading="Exceptions" className={groupHeadingClass}>
              {exceptions.map((item) => (
                <Command.Item
                  key={item.id}
                  value={`exception ${item.id} ${item.title} ${item.label}`}
                  className={itemClass}
                  onSelect={() => run(() => navigate(`/exceptions?id=${encodeURIComponent(item.id)}`))}
                >
                  <Tag>{item.id}</Tag>
                  <span className="min-w-0 flex-1 truncate">{item.title}</span>
                  <span className="text-xs text-muted">{state.exceptions[item.id] ? "Worked" : "Open"}</span>
                </Command.Item>
              ))}
            </Command.Group>
            <Command.Group heading="Queries" className={groupHeadingClass}>
              {loaded &&
                casework?.tracker.queries.map((query) => (
                  <Command.Item
                    key={query.id}
                    value={`query ${query.id} ${query.subject} ${query.to}`}
                    className={itemClass}
                    onSelect={() => run(() => navigate(`/queries?id=${encodeURIComponent(query.id)}`))}
                  >
                    <Tag>{query.id}</Tag>
                    <span className="min-w-0 flex-1 truncate">{query.subject}</span>
                    <span className="text-xs text-muted capitalize">{query.status}</span>
                  </Command.Item>
                ))}
            </Command.Group>
            <Command.Group heading="Cases" className={groupHeadingClass}>
              {pipeline?.cases.map((item) => (
                <Command.Item
                  key={item.number}
                  value={`case ${item.number} ${item.facility} ${item.client} ${item.deal_type}`}
                  className={itemClass}
                  onSelect={() => run(() => navigate(casePath(item)))}
                >
                  <Tag>{item.number}</Tag>
                  <span className="min-w-0 flex-1 truncate">{item.facility}</span>
                  <span className="text-xs text-muted">{item.stage}</span>
                </Command.Item>
              ))}
            </Command.Group>
          </>
        )}
        <Command.Group heading="Actions" className={groupHeadingClass}>
          <Command.Item value="presenter mode walkthrough" className={itemClass} onSelect={() => run(presenter.toggle)}>
            <Presentation aria-hidden className="size-4 text-muted" />
            {presenter.enabled ? "Turn off presenter mode" : "Turn on presenter mode"}
          </Command.Item>
          <Command.Item value="large text" className={itemClass} onSelect={() => run(onToggleLargeText)}>
            <Type aria-hidden className="size-4 text-muted" />
            {largeText ? "Turn off large text" : "Turn on large text"}
          </Command.Item>
          <Command.Item
            value="reset case"
            className={itemClass}
            onSelect={() =>
              run(() => {
                dispatch({ type: "reset" });
                navigate("/");
              })
            }
          >
            <RotateCcw aria-hidden className="size-4 text-muted" />
            Reset case
          </Command.Item>
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
