import { describe, expect, it } from "vitest";
import { DEFAULT_LAYOUT, layoutGraph, wrapLabel, type GraphNodeInput } from "./graph";

const STAGES = ["receive", "interpret", "codify", "validate", "resolve", "report", "communicate"];

const PIPELINE: GraphNodeInput[] = [
  { id: "intake", stage: "receive", upstream: [] },
  { id: "extraction", stage: "interpret", upstream: ["intake"] },
  { id: "definitions", stage: "interpret", upstream: ["intake"] },
  { id: "mapping", stage: "codify", upstream: ["intake"] },
  { id: "quote_check", stage: "validate", upstream: ["extraction", "definitions"] },
  { id: "validation", stage: "validate", upstream: ["mapping"] },
  { id: "calculation", stage: "validate", upstream: ["validation", "quote_check"] },
  { id: "triage", stage: "resolve", upstream: ["validation", "calculation"] },
  { id: "drafting", stage: "report", upstream: ["triage", "calculation"] },
  { id: "status_brief", stage: "communicate", upstream: ["triage"] },
];

function overlaps(a: { x: number; y: number; width: number; height: number }, b: typeof a): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

describe("layoutGraph", () => {
  const layout = layoutGraph(PIPELINE, STAGES);
  const at = (id: string) => layout.nodes.find((n) => n.id === id)!;

  it("places every node once, in input order", () => {
    expect(layout.nodes.map((n) => n.id)).toEqual(PIPELINE.map((n) => n.id));
  });

  it("orders the bands by stage, left to right, inside the drawing", () => {
    expect(layout.bands.map((b) => b.stage)).toEqual(STAGES);
    for (let i = 1; i < layout.bands.length; i += 1) {
      expect(layout.bands[i].x).toBeGreaterThan(layout.bands[i - 1].x + layout.bands[i - 1].width);
    }
    const last = layout.bands.at(-1)!;
    expect(last.x + last.width).toBeLessThanOrEqual(layout.width);
    for (const node of layout.nodes) {
      expect(node.y + node.height).toBeLessThanOrEqual(layout.height);
      expect(node.y).toBeGreaterThanOrEqual(DEFAULT_LAYOUT.padTop);
    }
  });

  it("moves an agent fed from its own stage one lane right", () => {
    expect(at("validation").lane).toBe(0);
    expect(at("quote_check").lane).toBe(0);
    expect(at("calculation").lane).toBe(1);
    const band = layout.bands.find((b) => b.stage === "validate")!;
    expect(band.width).toBe(2 * DEFAULT_LAYOUT.nodeWidth + DEFAULT_LAYOUT.laneGap);
    expect(at("calculation").x).toBeGreaterThan(at("validation").x + at("validation").width);
  });

  it("keeps every node inside its band and apart from the others", () => {
    for (const node of layout.nodes) {
      const band = layout.bands.find((b) => b.stage === node.stage)!;
      expect(node.x).toBeGreaterThanOrEqual(band.x);
      expect(node.x + node.width).toBeLessThanOrEqual(band.x + band.width);
    }
    for (const a of layout.nodes) {
      for (const b of layout.nodes) {
        if (a.id !== b.id) {
          expect(overlaps(a, b)).toBe(false);
        }
      }
    }
  });

  it("draws one edge per hand-off, always left to right, end to end", () => {
    const count = PIPELINE.reduce((sum, n) => sum + n.upstream.length, 0);
    expect(layout.edges).toHaveLength(count);
    for (const edge of layout.edges) {
      const from = at(edge.from);
      const to = at(edge.to);
      expect(edge.x1).toBe(from.x + from.width);
      expect(edge.x2).toBe(to.x);
      expect(edge.x2).toBeGreaterThan(edge.x1);
      expect(edge.y1).toBe(from.y + from.height / 2);
      expect(edge.path.startsWith(`M ${edge.x1} ${edge.y1} C`)).toBe(true);
      expect(edge.path.endsWith(`${edge.x2} ${edge.y2}`)).toBe(true);
    }
  });

  it("orders a column by where its feeders sit", () => {
    // Quote check is fed from interpret, which sits above codify's mapping -> validation.
    const nodes = layoutGraph(
      [
        { id: "a", stage: "receive", upstream: [] },
        { id: "b", stage: "receive", upstream: [] },
        { id: "fromB", stage: "interpret", upstream: ["b"] },
        { id: "fromA", stage: "interpret", upstream: ["a"] },
      ],
      STAGES,
    ).nodes;
    const y = (id: string) => nodes.find((n) => n.id === id)!.y;
    expect(y("fromA")).toBeLessThan(y("fromB"));
  });

  it("centres a shorter column against the tallest", () => {
    expect(at("intake").y).toBe(at("extraction").y + (DEFAULT_LAYOUT.nodeHeight + DEFAULT_LAYOUT.rowGap) / 2);
  });

  it("is deterministic", () => {
    expect(layoutGraph(PIPELINE, STAGES)).toEqual(layout);
  });

  it("refuses an unknown stage, an unresolved or backward dependency and a loop", () => {
    expect(() => layoutGraph([{ id: "x", stage: "nowhere", upstream: [] }], STAGES)).toThrow(/unknown stage/);
    expect(() => layoutGraph([{ id: "x", stage: "receive", upstream: ["ghost"] }], STAGES)).toThrow(/does not resolve/);
    expect(() =>
      layoutGraph(
        [
          { id: "late", stage: "report", upstream: [] },
          { id: "early", stage: "receive", upstream: ["late"] },
        ],
        STAGES,
      ),
    ).toThrow(/later stage/);
    expect(() =>
      layoutGraph(
        [
          { id: "a", stage: "validate", upstream: ["b"] },
          { id: "b", stage: "validate", upstream: ["a"] },
        ],
        STAGES,
      ),
    ).toThrow(/loop/);
  });

  it("keeps an empty stage as a one-lane band", () => {
    const sparse = layoutGraph([{ id: "only", stage: "report", upstream: [] }], STAGES);
    expect(sparse.bands).toHaveLength(STAGES.length);
    expect(sparse.bands.every((b) => b.width === DEFAULT_LAYOUT.nodeWidth)).toBe(true);
  });
});

describe("wrapLabel", () => {
  it("wraps by word and caps the line count", () => {
    expect(wrapLabel("Intake and classification", 16)).toEqual(["Intake and", "classification"]);
    expect(wrapLabel("Triage", 16)).toEqual(["Triage"]);
    const capped = wrapLabel("Alerts (self-service rule drafting) for clients", 14, 2);
    expect(capped).toHaveLength(2);
    expect(capped[1].endsWith("…")).toBe(true);
  });
});
