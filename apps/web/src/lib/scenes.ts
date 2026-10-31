export interface Scene {
  number: number;
  path: string;
  label: string;
  title: string;
  minutes: number;
  summary: string;
}

export const scenes: Scene[] = [
  {
    number: 0,
    path: "/",
    label: "Deal",
    title: "Deal card",
    minutes: 1,
    summary: "Who the deal is for, and what Oxane is doing on it.",
  },
  {
    number: 1,
    path: "/intake",
    label: "Intake",
    title: "Document intake",
    minutes: 2,
    summary: "Each file classified by type, version and effective date, with missing items flagged.",
  },
  {
    number: 2,
    path: "/terms",
    label: "Terms",
    title: "Facility terms",
    minutes: 4,
    summary: "Every value with its source, confidence and tier. Click a value to open its clause.",
  },
  {
    number: 3,
    path: "/rules",
    label: "Rules",
    title: "Rules from the agreement",
    minutes: 3,
    summary: "Each rule as clause, plain English and test logic. Edits are logged with a reason.",
  },
  {
    number: 4,
    path: "/mapping",
    label: "Mapping",
    title: "Data mapping",
    minutes: 2,
    summary: "Tape columns mapped to platform fields, with derived fields labelled as derived.",
  },
  {
    number: 5,
    path: "/validation",
    label: "Validation",
    title: "First validation run",
    minutes: 3,
    summary: "The system's borrowing base beside the borrower's, with differences traced to loans.",
  },
  {
    number: 6,
    path: "/exceptions",
    label: "Exceptions",
    title: "Exception queue",
    minutes: 3,
    summary: "Missing, conflicting and ambiguous items, each with evidence and a suggested action.",
  },
  {
    number: 7,
    path: "/approve",
    label: "Approve",
    title: "Approve and load",
    minutes: 1,
    summary: "A second analyst reviews the changes, then the load file and audit log are produced.",
  },
  {
    number: 8,
    path: "/results",
    label: "Results",
    title: "Scorecard",
    minutes: 1,
    summary: "Accuracy against the answer key, exceptions found and time taken, with formulas.",
  },
];

export function sceneForPath(pathname: string): Scene | undefined {
  return scenes.find((scene) => scene.path === pathname);
}
