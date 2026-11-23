/* The acting-user switch and hand-off notices, shared by every shell. */
import { Check, ChevronDown, ListTodo, RotateCcw, Settings, Type } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import { type ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useWork, type WorkItem } from "../../lib/deals";
import { useLargeText, usePresenterMode } from "../../lib/presenter";
import { usePersona, type Persona } from "../../lib/persona";
import { Avatar } from "../ui/Avatar";
import type { BellItem } from "./HeaderControls";

const menuItem =
  "flex h-8 cursor-pointer items-center gap-2 rounded px-2 text-[0.8125rem] outline-none data-[highlighted]:bg-sand";

export function homeOf(persona: Persona | null): string {
  return persona?.role === "client" ? "/portal" : "/work";
}

/** The app root belongs to no case: it sends the acting persona to their own home. */
export function HomeRedirect() {
  const { personas, persona } = usePersona();
  const { search } = useLocation();
  if (!persona && !personas.length) {
    return null;
  }
  return <Navigate to={`${homeOf(persona)}${search}`} replace />;
}

export function PersonaMenu({ onReset, resetLabel = "Reset case" }: { onReset?: () => void; resetLabel?: string }) {
  const { personas, persona, setPersona } = usePersona();
  const navigate = useNavigate();
  const largeText = useLargeText();
  const shown = persona ?? { id: "", name: "Loading", role_label: "", title: "", role: "admin" as const, client: null };
  const team = personas.filter((p) => p.role !== "client");
  const clients = personas.filter((p) => p.role === "client");
  const pick = (id: string) => {
    const next = personas.find((p) => p.id === id) ?? null;
    setPersona(id);
    navigate(homeOf(next));
  };
  const radio = (p: Persona) => (
    <DropdownMenu.RadioItem key={p.id} value={p.id} className={menuItem}>
      <Avatar name={p.name} />
      <span className="min-w-0 flex-1 leading-tight">
        <span className="block font-medium">{p.name}</span>
        <span className="block truncate text-[0.6875rem] text-muted">{p.role === "client" ? p.title : p.role_label}</span>
      </span>
      <DropdownMenu.ItemIndicator>
        <Check aria-hidden className="size-3.5" />
      </DropdownMenu.ItemIndicator>
    </DropdownMenu.RadioItem>
  );
  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            aria-label={`Acting as ${shown.name}, ${shown.role_label}`}
            className="flex h-8 cursor-pointer items-center gap-2 rounded-md pr-1.5 pl-1 hover:bg-sand"
          >
            <Avatar name={shown.name} />
            <span className="hidden text-left leading-tight xl:block">
              <span className="block text-xs font-medium">{shown.name}</span>
              <span className="block text-[0.6875rem] text-muted">{shown.role_label}</span>
            </span>
            <ChevronDown aria-hidden className="size-3.5 text-muted" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="end" sideOffset={6} className="z-50 max-h-[80vh] w-72 overflow-y-auto rounded-lg border border-line bg-surface p-1 shadow-overlay">
            <DropdownMenu.RadioGroup value={shown.id} onValueChange={pick} aria-label="Acting as">
              <DropdownMenu.Label className="px-2 pt-1.5 pb-1 text-[0.6875rem] font-semibold tracking-wide text-muted uppercase">Oxane team</DropdownMenu.Label>
              {team.map(radio)}
              <DropdownMenu.Separator className="my-1 h-px bg-line" />
              <DropdownMenu.Label className="px-2 pt-1.5 pb-1 text-[0.6875rem] font-semibold tracking-wide text-muted uppercase">Client users</DropdownMenu.Label>
              {clients.map(radio)}
            </DropdownMenu.RadioGroup>
            <DropdownMenu.Separator className="my-1 h-px bg-line" />
            <DropdownMenu.Item onSelect={() => navigate(homeOf(persona))} className={menuItem}>
              <ListTodo aria-hidden className="size-3.5 text-muted" />
              {persona?.role === "client" ? "Client portal" : "My work"}
            </DropdownMenu.Item>
            {persona?.role === "admin" && (
              <DropdownMenu.Item onSelect={() => navigate("/settings/ai-provider")} className={menuItem}>
                <Settings aria-hidden className="size-3.5 text-muted" />
                Settings
              </DropdownMenu.Item>
            )}
            <DropdownMenu.CheckboxItem checked={largeText.enabled} onCheckedChange={largeText.toggle} className={menuItem}>
              <Type aria-hidden className="size-3.5 text-muted" />
              <span className="flex-1">Large text</span>
              <DropdownMenu.ItemIndicator>
                <Check aria-hidden className="size-3.5" />
              </DropdownMenu.ItemIndicator>
            </DropdownMenu.CheckboxItem>
            {onReset && persona?.role !== "client" && (
              <DropdownMenu.Item onSelect={onReset} className={menuItem}>
                <RotateCcw aria-hidden className="size-3.5 text-muted" />
                {resetLabel}
              </DropdownMenu.Item>
            )}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </>
  );
}

/** Hand-offs waiting on the acting persona, as bell items. */
export function useWorkBell(): BellItem[] {
  const { persona } = usePersona();
  const { data } = useWork(Boolean(persona));
  return (data?.waiting ?? []).map((item: WorkItem) => ({
    id: `work-${item.id}`,
    title: item.title,
    detail: `${item.ref}${item.from_name ? ` · from ${item.from_name}` : ""}`,
    to: item.link || "/work",
    tone: item.overdue ? "danger" : item.kind === "approval" ? "warn" : "info",
  }));
}

/** Presenter mode only: who has to act next. */
export function HandOffHint({ items }: { items: WorkItem[] }) {
  const { enabled } = usePresenterMode();
  const { persona } = usePersona();
  const next = items.find((i) => i.status === "open" && i.assignee !== persona?.id);
  if (!enabled || !next) {
    return null;
  }
  return (
    <p role="status" className="mb-3 rounded-md bg-accent/30 px-3 py-1.5 text-xs font-medium">
      Switch to {next.assignee_name || next.role_label} to continue
    </p>
  );
}

export function Gate({ reason, children }: { reason: string | null | undefined; children: (disabled: boolean, title?: string) => ReactNode }) {
  return <>{children(Boolean(reason), reason ?? undefined)}</>;
}
