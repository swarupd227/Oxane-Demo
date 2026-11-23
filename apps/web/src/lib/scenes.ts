export interface Scene {
  path: string;
  label: string;
  /** A worked scenario that sits under a step, shown as a tab beside it. */
  parent?: string;
}

/** The working case's overview. The app root is each persona's home, never a case. */
export const CASE_HOME = "/overview";

// In walkthrough order: [ and ] move through every scene, sub-steps included.
export const scenes: Scene[] = [
  { path: CASE_HOME, label: "Deal" },
  { path: "/intake", label: "Intake" },
  { path: "/terms", label: "Terms" },
  { path: "/definitions", label: "Definitions", parent: "/terms" },
  { path: "/rules", label: "Rules" },
  { path: "/configuration", label: "Configuration", parent: "/rules" },
  { path: "/mapping", label: "Mapping" },
  { path: "/backbook", label: "Backbook", parent: "/mapping" },
  { path: "/validation", label: "Validation" },
  { path: "/exceptions", label: "Exceptions" },
  { path: "/client-model", label: "Client model", parent: "/exceptions" },
  { path: "/queries", label: "Query tracker", parent: "/exceptions" },
  { path: "/approve", label: "Approve" },
  { path: "/qc", label: "QC and release", parent: "/approve" },
  { path: "/results", label: "Scorecard" },
];

export const steps = scenes.filter((scene) => !scene.parent);

/** The step a path belongs to: itself, or the step it sits under. */
export function stepOf(path: string): string {
  return scenes.find((scene) => scene.path === path)?.parent ?? path;
}

/** "3" for a step, "3a" for the first scenario under it. */
export function sceneNumber(scene: Scene): string {
  const step = steps.findIndex((item) => item.path === stepOf(scene.path)) + 1;
  if (!scene.parent) {
    return String(step);
  }
  const siblings = scenes.filter((item) => item.parent === scene.parent);
  return `${step}${"abc"[siblings.indexOf(scene)]}`;
}

/** The sidebar: the case's records by object, each with the screens that belong to it. */
export interface Section {
  id: string;
  label: string;
  path: string;
  children: { path: string; label: string }[];
}

export const sections: Section[] = [
  { id: "overview", label: "Overview", path: CASE_HOME, children: [] },
  { id: "documents", label: "Documents", path: "/intake", children: [] },
  {
    id: "terms",
    label: "Terms & Definitions",
    path: "/terms",
    children: [
      { path: "/terms", label: "Terms" },
      { path: "/definitions", label: "Definitions" },
    ],
  },
  {
    id: "rules",
    label: "Rules & Configuration",
    path: "/rules",
    children: [
      { path: "/rules", label: "Rules" },
      { path: "/configuration", label: "Configuration" },
    ],
  },
  {
    id: "mapping",
    label: "Mapping & Backbook",
    path: "/mapping",
    children: [
      { path: "/mapping", label: "Tape mapping" },
      { path: "/backbook", label: "Backbook" },
    ],
  },
  { id: "validation", label: "Validation", path: "/validation", children: [] },
  {
    id: "exceptions",
    label: "Exceptions & Queries",
    path: "/exceptions",
    children: [
      { path: "/exceptions", label: "Exceptions" },
      { path: "/client-model", label: "Client model" },
      { path: "/queries", label: "Queries" },
    ],
  },
  {
    id: "approvals",
    label: "Approvals & QC",
    path: "/approve",
    children: [
      { path: "/approve", label: "Approvals" },
      { path: "/qc", label: "Independent QC" },
    ],
  },
  { id: "metrics", label: "Metrics", path: "/results", children: [] },
];

/** The sidebar section a path belongs to, and the screen within it. */
export function sectionOf(path: string): { section: Section; child?: { path: string; label: string } } | null {
  for (const section of sections) {
    const child = section.children.find((item) => item.path === path);
    if (child || section.path === path) {
      return { section, child };
    }
  }
  return null;
}
