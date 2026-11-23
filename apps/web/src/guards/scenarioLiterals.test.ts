/* Guard: the shared, generic UI (shells, navigation, breadcrumbs, headers, the persona menu,
 * notifications, My work, list pages and shared components) must not hard-code anything from
 * the scripted scenarios. A case number, a facility, client or borrower name, a person who is not
 * in the persona registry, a fixed date or a "demo" word in those files pins one scenario into
 * every screen (as "Case 0412" once was in the global sidebar). Such values must come from the
 * API or the route instead.
 *
 * The scenario literals are read from the scenario data itself (deal-kit/*.yaml, the monitoring
 * portfolio and the persona registry), so a new facility or contact is guarded without editing
 * this file. Inside the web container only apps/web is mounted; there the guard falls back to
 * SEED below plus the patterns, and says so. Set SCENARIO_DATA_DIR to the repository root to
 * point it at the data from elsewhere. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const SRC = fileURLToPath(new URL("..", import.meta.url));

/** The shared UI the guard reads, relative to src. A directory means every .ts/.tsx in it. */
const GUARDED = [
  "components/shell",
  "components/ui",
  "lib/persona.tsx",
  "lib/notifications.ts",
  "lib/presenter.ts",
  "lib/cases.ts",
  "lib/deals.ts",
  "lib/api.ts",
  "lib/format.ts",
  "monitoring/MonitoringShell.tsx",
  "monitoring/parts.tsx",
  "monitoring/ui.tsx",
  "monitoring/presenter.tsx",
  "monitoring/desk.ts",
  "pages/deals/MyWorkPage.tsx",
  "pages/CasesPage.tsx",
  "pages/deals/ClientsPage.tsx",
  "agents/AgentsConsole.tsx",
  "main.tsx",
];

/**
 * Deliberate exceptions. Keep this list short: each entry needs a reason, and an entry that no
 * longer matches anything fails the test, so the list cannot go stale.
 */
const ALLOWLIST: { file: string; literal: string; reason: string }[] = [
  {
    file: "lib/persona.tsx",
    literal: "X-Demo-Access-Code",
    reason: "HTTP header name the API reads; never shown to the user.",
  },
];

/** Used only when the scenario data is not reachable (the web container mounts apps/web alone). */
const SEED = {
  caseNumbers: ["0412", "0371", "0384", "0390", "0403", "0406", "0408", "0410", "0415"],
  names: [
    "Bramble", "Northmoor", "Kestrel", "Larkspur", "Ravenglass", "Wharfedale", "Calderwood",
    "Thornbury", "Harbourline", "Fenwick", "Ashgrove", "Kingsgate", "Marlow", "Halden",
    "Northgate", "Granite Peak", "Ferncliff", "Osprey", "Pennant", "Cobalt", "Harrowgate",
  ],
  people: ["Daniel Okafor", "Okafor", "Nadia Brooks", "Rosa Lind"],
  allowedPeople: ["Hannah Cole", "Ruth Adeyemi", "Tom Fairley", "Marcus Hale", "Priya Raman",
    "Elena Varga", "James Whitcombe", "Laura Haskett", "Alex Morgan"],
};

/** Words that start entity names in the data but are ordinary English, so never flagged alone. */
const GENERIC = new Set([
  "the", "first", "second", "facility", "monthly", "quarterly", "unitranche", "senior", "north",
  "south", "east", "west", "new", "auto", "credit", "bank", "capital", "fund", "direct", "motor",
]);

const DATE_PATTERNS: { label: string; re: RegExp }[] = [
  { label: "ISO date", re: /\b(19|20)\d\d-(0[1-9]|1[0-2])(-\d\d)?\b/ },
  { label: "month and year", re: /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? (19|20)\d\d\b/ },
  { label: "quarter", re: /\bQ[1-4] (19|20)\d\d\b/ },
];
const WORDS = /\b(sandbox|recorded|demo)\b/i;
const CASE_PATTERN = /\bONB-\d+\b/;

interface Literals {
  source: "data" | "seed";
  caseNumbers: string[];
  names: string[];
  people: string[];
  allowedPeople: string[];
}

function findRoot(): string | null {
  const candidates = [process.env.SCENARIO_DATA_DIR, path.resolve(SRC, "../../..")].filter(Boolean) as string[];
  return candidates.find((dir) => fs.existsSync(path.join(dir, "deal-kit", "deal.yaml"))) ?? null;
}

const ENTITY_KEYS = "name|borrower|lender|short_name|legal_name|servicer|originator|sponsor|issuer|fund|manager|facility|client|trustee|counterparty";

/** Read the scenario's own names, numbers and people from its data files. */
export function scenarioLiterals(root: string | null): Literals {
  if (!root) {
    return { source: "seed", ...SEED };
  }
  const registry = fs.readFileSync(path.join(root, "services/api/app/personas.py"), "utf8");
  const allowedPeople: string[] = [];
  const clientIds: string[] = [];
  for (const m of registry.matchAll(/Persona\("([^"]+)",\s*"([^"]+)",\s*"[^"]+",\s*"[^"]*"(?:,\s*"([^"]+)")?\)/g)) {
    allowedPeople.push(m[2]);
    if (m[3]) {
      clientIds.push(m[3]);
    }
  }
  const files = [
    ...fs.readdirSync(path.join(root, "deal-kit")).filter((f) => f.endsWith(".yaml")).map((f) => path.join(root, "deal-kit", f)),
    path.join(root, "services/api/app/monitoring/portfolio.yaml"),
  ];
  const caseNumbers = new Set<string>();
  const names = new Set<string>(clientIds);
  const people = new Set<string>();
  const allowedParts = new Set(allowedPeople.flatMap((p) => [p, ...p.split(" ")]).map((p) => p.toLowerCase()));
  const keyed = new RegExp(`(?:^|[\\s{,-])(${ENTITY_KEYS}):\\s*(?:\\{\\s*name:\\s*)?("?)([^,}\\n#"]+)\\2`, "g");
  for (const file of files) {
    for (const line of fs.readFileSync(file, "utf8").split("\n")) {
      if (line.trimStart().startsWith("#")) {
        continue;
      }
      for (const m of line.matchAll(/\bnumber:\s*"?(\d{4})"?/g)) {
        caseNumbers.add(m[1]);
      }
      for (const m of line.matchAll(keyed)) {
        const value = m[3].trim();
        const words = value.split(/\s+/);
        if (words.length < 2 || !/^[A-Z]/.test(value)) {
          continue;
        }
        // A two-word "name" of plain capitalised words is a person (Daniel Okafor); entities carry more.
        const personLike = m[1] === "name" && words.length === 2 && words.every((w) => /^[A-Z][a-z]+$/.test(w));
        if (personLike) {
          if (!allowedParts.has(value.toLowerCase())) {
            people.add(value);
            if (!allowedParts.has(words[1].toLowerCase())) {
              people.add(words[1]);
            }
          }
          continue;
        }
        const head = words[0].replace(/[^A-Za-z-]/g, "");
        if (head.length >= 4 && !GENERIC.has(head.toLowerCase()) && !allowedParts.has(head.toLowerCase()) && ![...names].some((n) => n.toLowerCase() === head.toLowerCase())) {
          names.add(head);
        }
      }
    }
  }
  return { source: "data", caseNumbers: [...caseNumbers], names: [...names], people: [...people], allowedPeople };
}

interface Text {
  file: string;
  line: number;
  text: string;
}

/** Every piece of text a file could put on screen: string literals, template text and JSX text. */
export function textsOf(file: string, code: string): Text[] {
  const source = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const out: Text[] = [];
  const add = (node: ts.Node, text: string) => {
    if (text.trim()) {
      out.push({ file, line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1, text });
    }
  };
  const visit = (node: ts.Node) => {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      return;
    }
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
      add(node, node.text);
    } else if (ts.isJsxText(node)) {
      add(node, node.text);
    } else if ((ts.isPropertyAssignment(node) || ts.isPropertySignature(node)) && ts.isIdentifier(node.name)) {
      // Object keys too: a lookup keyed by facility id ({ bramble: ... }) is as scenario-bound.
      add(node.name, node.name.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return out;
}

function escape(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function violationsIn(texts: Text[], literals: Literals): { file: string; line: number; text: string; why: string }[] {
  const checks: { why: string; re: RegExp }[] = [
    ...literals.caseNumbers.map((n) => ({ why: `case number ${n}`, re: new RegExp(`(?<![\\d.])${n}(?![\\d.])`) })),
    { why: "new-deal case reference", re: CASE_PATTERN },
    ...literals.names.map((n) => ({ why: `scenario name "${n}"`, re: new RegExp(`\\b${escape(n)}\\b`, "i") })),
    ...literals.people.map((n) => ({ why: `person "${n}" outside the persona registry`, re: new RegExp(`\\b${escape(n)}\\b`) })),
    ...DATE_PATTERNS.map((d) => ({ why: `fixed date (${d.label})`, re: d.re })),
    { why: "sandbox/recorded/demo wording", re: WORDS },
  ];
  const found: { file: string; line: number; text: string; why: string }[] = [];
  for (const t of texts) {
    for (const check of checks) {
      if (!check.re.test(t.text)) {
        continue;
      }
      if (ALLOWLIST.some((a) => a.file === t.file && t.text.includes(a.literal))) {
        continue;
      }
      found.push({ ...t, text: t.text.trim().slice(0, 80), why: check.why });
    }
  }
  return found;
}

function guardedFiles(): string[] {
  return GUARDED.flatMap((entry) => {
    const full = path.join(SRC, entry);
    if (fs.statSync(full).isDirectory()) {
      return fs
        .readdirSync(full)
        .filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f))
        .map((f) => `${entry}/${f}`);
    }
    return [entry];
  });
}

describe("shared UI carries no scenario-specific literals", () => {
  const root = findRoot();
  const literals = scenarioLiterals(root);
  const files = guardedFiles();
  const texts = files.flatMap((file) => textsOf(file, fs.readFileSync(path.join(SRC, file), "utf8")));

  it("reads the scenario literals from the data when it is reachable", () => {
    if (process.env.CI) {
      expect(root, "CI checks out the whole repository, so the data must be found").not.toBeNull();
    }
    if (literals.source === "data") {
      // The scripted scenarios' own names must come through, or the extraction has broken.
      expect(literals.caseNumbers).toEqual(expect.arrayContaining(["0412", "0371"]));
      expect(literals.names.map((n) => n.toLowerCase())).toEqual(
        expect.arrayContaining(["bramble", "northmoor", "kestrel", "larkspur", "ravenglass", "wharfedale", "calderwood", "thornbury", "harbourline", "fenwick"]),
      );
      expect(literals.people).toEqual(expect.arrayContaining(["Daniel Okafor", "Okafor", "Tom Lister"]));
      expect(literals.people).not.toEqual(expect.arrayContaining(literals.allowedPeople));
    } else {
      console.warn("Scenario data not found (web container?): checking the seed list and patterns only.");
    }
  });

  it("finds every guarded file", () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it("has no case numbers, scenario names, outside people, fixed dates or demo wording", () => {
    const found = violationsIn(texts, literals).map((v) => `${v.file}:${v.line} ${v.why}: "${v.text}"`);
    expect(found).toEqual([]);
  });

  it("keeps every allowlist entry in use", () => {
    const unused = ALLOWLIST.filter((a) => !texts.some((t) => t.file === a.file && t.text.includes(a.literal)));
    expect(unused).toEqual([]);
  });

  it("catches the gap it was written for", () => {
    const planted = textsOf("planted.tsx", `export const X = () => <p>Case 0412 · Bramble Auto, as of 24 Jun 2026 (demo)</p>;`);
    const why = violationsIn(planted, literals).map((v) => v.why);
    expect(why).toEqual(expect.arrayContaining(["case number 0412", "fixed date (month and year)", "sandbox/recorded/demo wording"]));
    expect(why.some((w) => w.includes("Bramble"))).toBe(true);
  });
});
