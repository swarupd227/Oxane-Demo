/* Lays out the agent dependency graph by pipeline stage, left to right.
 *
 * Each stage is a band. Inside a band, an agent fed by another agent of the same stage moves
 * one lane to the right of it, so every edge runs left to right. Within a lane, agents are
 * ordered by the average height of what feeds them, which keeps most edges short and level. */

export interface GraphNodeInput {
  id: string;
  stage: string;
  upstream: string[];
}

export interface LayoutOptions {
  nodeWidth: number;
  nodeHeight: number;
  laneGap: number;
  bandGap: number;
  rowGap: number;
  padX: number;
  padTop: number;
  padBottom: number;
}

export interface PlacedNode {
  id: string;
  stage: string;
  lane: number;
  row: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PlacedEdge {
  from: string;
  to: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  path: string;
}

export interface Band {
  stage: string;
  x: number;
  width: number;
}

export interface GraphLayout {
  nodes: PlacedNode[];
  edges: PlacedEdge[];
  bands: Band[];
  width: number;
  height: number;
}

export const DEFAULT_LAYOUT: LayoutOptions = {
  nodeWidth: 132,
  nodeHeight: 56,
  laneGap: 20,
  bandGap: 36,
  rowGap: 18,
  padX: 12,
  padTop: 36,
  padBottom: 12,
};

export function layoutGraph(input: GraphNodeInput[], stages: string[], options: Partial<LayoutOptions> = {}): GraphLayout {
  const o = { ...DEFAULT_LAYOUT, ...options };
  const byId = new Map(input.map((n) => [n.id, n]));
  const stageOf = new Map(stages.map((s, i) => [s, i]));
  if (byId.size !== input.length) {
    throw new Error("Node ids repeat");
  }
  for (const node of input) {
    if (!stageOf.has(node.stage)) {
      throw new Error(`${node.id}: unknown stage ${node.stage}`);
    }
    for (const up of node.upstream) {
      const source = byId.get(up);
      if (!source) {
        throw new Error(`${node.id}: upstream ${up} does not resolve`);
      }
      if (stageOf.get(source.stage)! > stageOf.get(node.stage)!) {
        throw new Error(`${node.id}: upstream ${up} sits in a later stage`);
      }
    }
  }

  // Lane inside the band: one to the right of the furthest same-stage agent feeding it.
  const lanes = new Map<string, number>();
  const visiting = new Set<string>();
  const laneOf = (id: string): number => {
    const known = lanes.get(id);
    if (known !== undefined) {
      return known;
    }
    if (visiting.has(id)) {
      throw new Error(`${id}: dependency loop`);
    }
    visiting.add(id);
    const node = byId.get(id)!;
    const same = node.upstream.filter((up) => byId.get(up)!.stage === node.stage);
    const lane = same.length ? Math.max(...same.map(laneOf)) + 1 : 0;
    visiting.delete(id);
    lanes.set(id, lane);
    return lane;
  };
  input.forEach((n) => laneOf(n.id));

  // Columns, left to right: each stage's lanes in turn.
  const columns: { stage: string; lane: number; ids: string[] }[] = [];
  const bands: Band[] = [];
  let x = o.padX;
  for (const stage of stages) {
    const members = input.filter((n) => n.stage === stage);
    const count = members.length ? Math.max(...members.map((n) => lanes.get(n.id)!)) + 1 : 1;
    const width = count * o.nodeWidth + (count - 1) * o.laneGap;
    bands.push({ stage, x, width });
    for (let lane = 0; lane < count; lane += 1) {
      columns.push({ stage, lane, ids: members.filter((n) => lanes.get(n.id) === lane).map((n) => n.id) });
    }
    x += width + o.bandGap;
  }
  const width = x - o.bandGap + o.padX;
  const tallest = Math.max(1, ...columns.map((c) => c.ids.length));
  const pitch = o.nodeHeight + o.rowGap;

  // Rows: order each column by where its feeders sit, then centre the column.
  const placed = new Map<string, PlacedNode>();
  columns.forEach((column) => {
    const order = input.map((n) => n.id);
    const weight = (id: string): number => {
      const feeders = byId.get(id)!.upstream.map((up) => placed.get(up)).filter((p): p is PlacedNode => !!p);
      return feeders.length ? feeders.reduce((sum, p) => sum + p.y, 0) / feeders.length : Number.POSITIVE_INFINITY;
    };
    const sorted = [...column.ids].sort((a, b) => {
      const wa = weight(a);
      const wb = weight(b);
      if (wa !== wb && Number.isFinite(wa) && Number.isFinite(wb)) {
        return wa - wb;
      }
      if (Number.isFinite(wa) !== Number.isFinite(wb)) {
        return Number.isFinite(wa) ? -1 : 1;
      }
      return order.indexOf(a) - order.indexOf(b);
    });
    const offset = ((tallest - sorted.length) * pitch) / 2;
    const band = bands.find((b) => b.stage === column.stage)!;
    sorted.forEach((id, row) => {
      placed.set(id, {
        id,
        stage: column.stage,
        lane: column.lane,
        row,
        x: band.x + column.lane * (o.nodeWidth + o.laneGap),
        y: o.padTop + offset + row * pitch,
        width: o.nodeWidth,
        height: o.nodeHeight,
      });
    });
  });

  const edges: PlacedEdge[] = [];
  for (const node of input) {
    const target = placed.get(node.id)!;
    for (const up of node.upstream) {
      const source = placed.get(up)!;
      const x1 = source.x + source.width;
      const y1 = source.y + source.height / 2;
      const x2 = target.x;
      const y2 = target.y + target.height / 2;
      const dx = Math.max(16, (x2 - x1) / 2);
      edges.push({ from: up, to: node.id, x1, y1, x2, y2, path: `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}` });
    }
  }

  return {
    nodes: input.map((n) => placed.get(n.id)!),
    edges,
    bands,
    width,
    height: o.padTop + tallest * pitch - o.rowGap + o.padBottom,
  };
}

/** Splits a label into at most `lines` lines of about `width` characters, word by word. */
export function wrapLabel(text: string, width: number, lines = 2): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const out: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length <= width || !current) {
      current = next;
    } else {
      out.push(current);
      current = word;
    }
  }
  if (current) {
    out.push(current);
  }
  if (out.length > lines) {
    const kept = out.slice(0, lines);
    kept[lines - 1] = `${kept[lines - 1].slice(0, Math.max(1, width - 1))}…`;
    return kept;
  }
  return out;
}
