import { useLocation } from "react-router-dom";
import { Card, SectionLabel } from "../components/ui/layout";
import { Kbd } from "../components/ui/badges";
import { sceneForPath } from "../lib/scenes";

export function ScenePlaceholder() {
  const { pathname } = useLocation();
  const scene = sceneForPath(pathname);

  if (!scene) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div>
        <SectionLabel>
          Scene {scene.number} · {scene.minutes} min
        </SectionLabel>
        <h1 className="mt-2 text-[1.75rem] leading-tight font-semibold tracking-tight">
          {scene.title}
        </h1>
        <p className="mt-2 max-w-2xl text-[0.9375rem] leading-relaxed text-muted">{scene.summary}</p>
      </div>
      <Card
        tone="outline"
        className="flex h-72 flex-col items-center justify-center gap-2 text-center"
      >
        <p className="font-medium">This screen is not built yet</p>
        <p className="text-sm text-muted">It arrives in phase 3 of the development plan.</p>
        <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
          <Kbd>[</Kbd>
          <Kbd>]</Kbd>
          move between steps
        </p>
      </Card>
    </div>
  );
}
