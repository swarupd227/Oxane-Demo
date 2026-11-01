import { Command } from "cmdk";
import { Presentation, RotateCcw } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { scenes } from "../../lib/scenes";
import { useSession } from "../../lib/session";

const itemClass =
  "flex h-10 cursor-pointer items-center gap-3 rounded-md px-3 text-sm text-ink data-[selected=true]:bg-sand";

const groupHeadingClass =
  "[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[0.6875rem] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-muted [&_[cmdk-group-heading]]:uppercase";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  presenter: boolean;
  onTogglePresenter: () => void;
}

export function CommandPalette({
  open,
  onOpenChange,
  presenter,
  onTogglePresenter,
}: CommandPaletteProps) {
  const navigate = useNavigate();
  const { dispatch } = useSession();

  function run(action: () => void) {
    onOpenChange(false);
    action();
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command menu"
      // Exact matching, so a typed command can never land on a look-alike step.
      filter={(value, search) => (value.toLowerCase().includes(search.toLowerCase()) ? 1 : 0)}
      overlayClassName="fixed inset-0 z-40 bg-ink/40"
      contentClassName="fixed top-[18vh] left-1/2 z-50 w-[34rem] max-w-[calc(100vw-2rem)] -translate-x-1/2 overflow-hidden rounded-xl border border-line bg-surface shadow-overlay"
    >
      <Command.Input
        placeholder="Go to a step or run a command"
        className="h-12 w-full border-b border-line bg-transparent px-4 text-[0.9375rem] outline-none placeholder:text-muted focus-visible:shadow-none"
      />
      <Command.List className="max-h-96 overflow-y-auto p-2">
        <Command.Empty className="px-3 py-6 text-center text-sm text-muted">
          No matching command.
        </Command.Empty>
        <Command.Group heading="Steps" className={groupHeadingClass}>
          {scenes.map((scene, index) => (
            <Command.Item
              key={scene.path}
              value={`${index + 1} ${scene.label}`}
              className={itemClass}
              onSelect={() => run(() => navigate(scene.path))}
            >
              <span className="numeric w-4 text-center text-muted">{index + 1}</span>
              {scene.label}
            </Command.Item>
          ))}
        </Command.Group>
        <Command.Group heading="View" className={groupHeadingClass}>
          <Command.Item
            value="large text"
            className={itemClass}
            onSelect={() => run(onTogglePresenter)}
          >
            <Presentation aria-hidden className="size-4 text-muted" />
            {presenter ? "Turn off large text" : "Turn on large text"}
          </Command.Item>
        </Command.Group>
        <Command.Group heading="Case" className={groupHeadingClass}>
          <Command.Item
            value="reset sandbox case"
            className={itemClass}
            onSelect={() =>
              run(() => {
                dispatch({ type: "reset" });
                navigate("/");
              })
            }
          >
            <RotateCcw aria-hidden className="size-4 text-muted" />
            Reset sandbox case
          </Command.Item>
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
