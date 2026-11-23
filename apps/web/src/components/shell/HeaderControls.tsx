/* Header controls shared by the workbench: environment label, walkthrough toggle,
   notifications and the acting user. */
import clsx from "clsx";
import { Bell, Check, ChevronDown, Presentation, RotateCcw, Type } from "lucide-react";
import { DropdownMenu, Popover } from "radix-ui";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useLargeText, usePresenterMode } from "../../lib/presenter";
import { Avatar } from "../ui/Avatar";
import { Tooltip } from "../ui/Tooltip";

const iconButton =
  "relative inline-flex size-8 cursor-pointer items-center justify-center rounded-md text-muted hover:bg-sand hover:text-ink";

export function EnvironmentLabel() {
  return (
    <Tooltip content="User acceptance environment.">
      <span
        tabIndex={0}
        className="inline-flex h-6 items-center rounded border border-warn/40 bg-warn-tint px-1.5 text-[0.6875rem] font-semibold tracking-wide text-warn"
      >
        UAT
      </span>
    </Tooltip>
  );
}

export function WalkthroughToggle() {
  const { enabled, toggle } = usePresenterMode();
  return (
    <Tooltip content={enabled ? "Presenter mode on (Alt+P)" : "Presenter mode (Alt+P)"}>
      <button
        type="button"
        aria-label="Presenter mode"
        aria-pressed={enabled}
        onClick={toggle}
        className={clsx(iconButton, enabled && "bg-accent text-white hover:bg-accent-strong hover:text-white")}
      >
        <Presentation aria-hidden className="size-4" />
      </button>
    </Tooltip>
  );
}

export interface BellItem {
  id: string;
  title: string;
  detail: string;
  to: string;
  tone?: "info" | "warn" | "danger";
}

export function NotificationBell({ items }: { items: BellItem[] }) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button type="button" aria-label={`Notifications, ${items.length}`} className={iconButton}>
          <Bell aria-hidden className="size-4" />
          {items.length > 0 && (
            <span className="numeric absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[0.625rem] font-semibold text-white">
              {items.length}
            </span>
          )}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className="z-50 w-80 overflow-hidden rounded-lg border border-line bg-surface shadow-overlay"
        >
          <p className="border-b border-line px-3 py-2 text-xs font-semibold">Notifications</p>
          {items.length === 0 ? (
            <p className="px-3 py-4 text-center text-xs text-muted">Nothing new</p>
          ) : (
            <ul className="max-h-96 overflow-y-auto">
              {items.map((item) => (
                <li key={item.id}>
                  <Popover.Close asChild>
                    <Link
                      to={item.to}
                      className="flex gap-2.5 border-b border-sand px-3 py-2 last:border-0 hover:bg-canvas"
                    >
                      <span
                        aria-hidden
                        className={clsx(
                          "mt-1.5 size-1.5 shrink-0 rounded-full",
                          { info: "bg-info", warn: "bg-warn", danger: "bg-danger" }[item.tone ?? "info"],
                        )}
                      />
                      <span className="min-w-0">
                        <span className="block text-[0.8125rem] font-medium">{item.title}</span>
                        <span className="block truncate text-xs text-muted">{item.detail}</span>
                      </span>
                    </Link>
                  </Popover.Close>
                </li>
              ))}
            </ul>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export interface ActingUser {
  id: string;
  name: string;
  role: string;
}

const menuItem =
  "flex h-8 cursor-pointer items-center gap-2 rounded px-2 text-[0.8125rem] outline-none data-[highlighted]:bg-sand";

export function UserMenu({
  users,
  current,
  signedIn,
  onSwitch,
  onReset,
  extra,
}: {
  users: ActingUser[];
  current: string;
  signedIn?: { name: string; role: string } | null;
  onSwitch: (id: string) => void;
  onReset?: () => void;
  extra?: ReactNode;
}) {
  const largeText = useLargeText();
  const user = signedIn ?? users.find((item) => item.id === current) ?? users[0];
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          aria-label={`Acting as ${user.name}, ${user.role}`}
          className="flex h-8 cursor-pointer items-center gap-2 rounded-md pr-1.5 pl-1 hover:bg-sand"
        >
          <Avatar name={user.name} />
          <span className="hidden text-left leading-tight xl:block">
            <span className="block text-xs font-medium">{user.name}</span>
            <span className="block text-[0.6875rem] text-muted">{user.role}</span>
          </span>
          <ChevronDown aria-hidden className="size-3.5 text-muted" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 w-64 rounded-lg border border-line bg-surface p-1 shadow-overlay"
        >
          {signedIn ? (
            <p className="px-2 py-1.5 text-xs text-muted">Signed in as {signedIn.name}</p>
          ) : (
            <>
              <DropdownMenu.Label className="px-2 pt-1.5 pb-1 text-[0.6875rem] font-semibold tracking-wide text-muted uppercase">
                Acting as
              </DropdownMenu.Label>
              <DropdownMenu.RadioGroup value={current} onValueChange={onSwitch}>
                {users.map((item) => (
                  <DropdownMenu.RadioItem key={item.id} value={item.id} className={menuItem}>
                    <Avatar name={item.name} />
                    <span className="min-w-0 flex-1 leading-tight">
                      <span className="block font-medium">{item.name}</span>
                      <span className="block text-[0.6875rem] text-muted">{item.role}</span>
                    </span>
                    <DropdownMenu.ItemIndicator>
                      <Check aria-hidden className="size-3.5" />
                    </DropdownMenu.ItemIndicator>
                  </DropdownMenu.RadioItem>
                ))}
              </DropdownMenu.RadioGroup>
            </>
          )}
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <DropdownMenu.CheckboxItem
            checked={largeText.enabled}
            onCheckedChange={largeText.toggle}
            className={menuItem}
          >
            <Type aria-hidden className="size-3.5 text-muted" />
            <span className="flex-1">Large text</span>
            <DropdownMenu.ItemIndicator>
              <Check aria-hidden className="size-3.5" />
            </DropdownMenu.ItemIndicator>
          </DropdownMenu.CheckboxItem>
          {extra}
          {onReset && (
            <DropdownMenu.Item onSelect={onReset} className={menuItem}>
              <RotateCcw aria-hidden className="size-3.5 text-muted" />
              Reset case
            </DropdownMenu.Item>
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
