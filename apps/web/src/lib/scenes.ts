export interface Scene {
  path: string;
  label: string;
}

export const scenes: Scene[] = [
  { path: "/", label: "Deal" },
  { path: "/intake", label: "Intake" },
  { path: "/terms", label: "Terms" },
  { path: "/rules", label: "Rules" },
  { path: "/mapping", label: "Mapping" },
  { path: "/validation", label: "Validation" },
  { path: "/exceptions", label: "Exceptions" },
  { path: "/approve", label: "Approve" },
  { path: "/results", label: "Scorecard" },
];
