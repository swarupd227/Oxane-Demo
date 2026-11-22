import clsx from "clsx";
import { Check, ChevronsUpDown, Search } from "lucide-react";
import { Popover } from "radix-ui";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { casePath, STAGE_TONES, useCases } from "../../lib/cases";
import { useNotifications } from "../../lib/notifications";
import { ANALYST, APPROVER, useSession, type Actor } from "../../lib/session";
import { WorkbenchSwitch } from "../../monitoring/parts";
import { Kbd } from "../ui/badges";
import {
  EnvironmentLabel,
  NotificationBell,
  UserMenu,
  WalkthroughToggle,
} from "./HeaderControls";

function CaseSwitcher() {
  const { data } = useCases();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const active = data?.cases.find((item) => item.active);
  const shown = (data?.cases ?? []).filter((item) =>
    `${item.number} ${item.client} ${item.facility}`.toLowerCase().includes(filter.toLowerCase()),
  );
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label="Switch case"
          className="flex h-8 max-w-[19rem] min-w-0 cursor-pointer items-center gap-2 rounded-md border border-line bg-surface px-2.5 text-left hover:border-stone"
        >
          <span className="numeric shrink-0 text-xs font-semibold text-muted">{active?.number ?? "0412"}</span>
          <span className="truncate text-[0.8125rem] font-medium">
            {active?.facility.replace(/ LLC$/, "") ?? "Loading"}
          </span>
          <ChevronsUpDown aria-hidden className="size-3.5 shrink-0 text-muted" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          className="z-50 w-[26rem] overflow-hidden rounded-lg border border-line bg-surface shadow-overlay"
        >
          <input
            autoFocus
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter cases"
            aria-label="Filter cases"
            className="h-9 w-full border-b border-line px-3 text-[0.8125rem] outline-none focus-visible:shadow-none"
          />
          <ul className="max-h-80 overflow-y-auto py-1">
            {shown.map((item) => (
              <li key={item.number}>
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    navigate(casePath(item));
                  }}
                  className="flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left hover:bg-canvas"
                >
                  <span className="numeric w-14 shrink-0 text-xs font-semibold text-muted">{item.number}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[0.8125rem] font-medium">{item.facility}</span>
                    <span className="block truncate text-[0.6875rem] text-muted">
                      {item.client} · {item.deal_type}
                    </span>
                  </span>
                  <span
                    className={clsx(
                      "shrink-0 rounded px-1.5 py-px text-[0.6875rem] font-medium",
                      STAGE_TONES[item.stage],
                    )}
                  >
                    {item.stage}
                  </span>
                  {item.active ? (
                    <Check aria-label="Current case" className="size-3.5 shrink-0" />
                  ) : (
                    <span className="size-3.5 shrink-0" />
                  )}
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              navigate("/cases");
            }}
            className="block w-full cursor-pointer border-t border-line px-3 py-2 text-left text-xs font-medium text-info hover:bg-canvas"
          >
            All cases
          </button>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

const ROLES: Record<Actor, string> = { analyst: "Preparer", approver: "Reviewer" };

export function DealBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { state, me, dispatch } = useSession();
  const navigate = useNavigate();
  const notices = useNotifications();

  return (
    <div className="flex h-12 items-center gap-3 border-b border-line bg-surface px-4">
      <div className="flex shrink-0 items-center gap-2 pr-1">
        <span aria-hidden className="size-5 rounded-[5px] bg-ink">
          <span className="ml-[5px] block h-full w-[5px] bg-accent" />
        </span>
        <span className="text-sm font-semibold tracking-tight">Oxane</span>
      </div>
      <WorkbenchSwitch current="onboarding" />
      <span aria-hidden className="h-5 w-px bg-line" />
      <CaseSwitcher />
      <button
        type="button"
        onClick={onOpenPalette}
        aria-label="Search"
        className="ml-2 flex h-8 w-full max-w-80 min-w-40 cursor-pointer items-center gap-2 rounded-md border border-line bg-canvas px-2.5 text-[0.8125rem] text-muted hover:border-stone"
      >
        <Search aria-hidden className="size-3.5 shrink-0" />
        <span className="flex-1 truncate text-left">Search terms, exceptions, queries</span>
        <Kbd>Ctrl</Kbd>
        <Kbd>K</Kbd>
      </button>
      <div className="ml-auto flex shrink-0 items-center gap-1.5">
        <WalkthroughToggle />
        <NotificationBell
          items={notices.map((notice) => ({
            ...notice,
            tone: notice.kind === "variance" ? "danger" : notice.kind === "approval" ? "warn" : "info",
          }))}
        />
        <EnvironmentLabel />
        <UserMenu
          users={[
            { id: "analyst", name: ANALYST, role: ROLES.analyst },
            { id: "approver", name: APPROVER, role: ROLES.approver },
          ]}
          current={state.actor}
          signedIn={
            me?.signed_in && me.user
              ? { name: me.user, role: me.role ? ROLES[me.role] : "No role" }
              : null
          }
          onSwitch={(id) => dispatch({ type: "set-actor", actor: id as Actor })}
          onReset={() => {
            dispatch({ type: "reset" });
            navigate("/");
          }}
        />
      </div>
    </div>
  );
}
