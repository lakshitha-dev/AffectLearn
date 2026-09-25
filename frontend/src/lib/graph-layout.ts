/**
 * Layered layout for the agent graph, computed from the graph's own edges.
 *
 * The topology is served by `/monitor/graph` from `app/agents/graph.py`, so a node added to the
 * backend graph (as `video_resource` was) must place itself without anyone editing coordinates.
 * The graph is a small DAG, so a full layout engine would be overkill:
 *
 *   1. RANK  -- longest path from the entry node, so a join (`deliver`, `END`) sits below every
 *               branch that feeds it.
 *   2. PLACE -- each node's preferred x is the mean of its parents' x (barycentre). Nodes on a
 *               rank are sorted by that preference, pushed apart to a minimum gap, and the rank
 *               is re-centred on its preferences, so a fan-out spreads symmetrically under its
 *               parent and a join lands centred under the branches it merges.
 *
 * Pure and deterministic: same edges in, same coordinates out.
 */

export interface LayoutEdge {
  from: string;
  to: string;
}

export interface LayoutOptions {
  /** Horizontal distance between node centres on one rank. */
  gapX?: number;
  /** Vertical distance between ranks. */
  gapY?: number;
}

export interface LayoutResult {
  positions: Record<string, { x: number; y: number }>;
  ranks: Record<string, number>;
}

export function layeredLayout(
  nodeIds: readonly string[],
  edges: readonly LayoutEdge[],
  { gapX = 280, gapY = 150 }: LayoutOptions = {},
): LayoutResult {
  const known = new Set(nodeIds);
  const valid = edges.filter((e) => known.has(e.from) && known.has(e.to) && e.from !== e.to);
  const parents: Record<string, string[]> = {};
  const children: Record<string, string[]> = {};
  for (const id of nodeIds) {
    parents[id] = [];
    children[id] = [];
  }
  for (const e of valid) {
    parents[e.to].push(e.from);
    children[e.from].push(e.to);
  }

  // 1. Longest-path ranks via a topological pass (Kahn). Anything left in a cycle keeps rank 0
  //    rather than looping: the agent graph is acyclic, but a malformed payload must not hang.
  const ranks: Record<string, number> = {};
  const indegree: Record<string, number> = {};
  for (const id of nodeIds) {
    ranks[id] = 0;
    indegree[id] = parents[id].length;
  }
  const queue = nodeIds.filter((id) => indegree[id] === 0);
  const order: string[] = [];
  while (queue.length) {
    const id = queue.shift()!;
    order.push(id);
    for (const c of children[id]) {
      ranks[c] = Math.max(ranks[c], ranks[id] + 1);
      indegree[c] -= 1;
      if (indegree[c] === 0) queue.push(c);
    }
  }

  // 2. Place rank by rank, top-down.
  const byRank = new Map<number, string[]>();
  for (const id of nodeIds) {
    const r = ranks[id];
    if (!byRank.has(r)) byRank.set(r, []);
    byRank.get(r)!.push(id);
  }
  const x: Record<string, number> = {};
  const position = (id: string) => nodeIds.indexOf(id);

  for (const r of [...byRank.keys()].sort((a, b) => a - b)) {
    const row = byRank.get(r)!;
    const preferred = (id: string) => {
      const ps = parents[id].filter((p) => p in x);
      return ps.length ? ps.reduce((s, p) => s + x[p], 0) / ps.length : 0;
    };
    const sorted = [...row].sort(
      (a, b) => preferred(a) - preferred(b) || position(a) - position(b),
    );
    const placed: number[] = [];
    sorted.forEach((id, i) => {
      const want = preferred(id);
      placed.push(i === 0 ? want : Math.max(want, placed[i - 1] + gapX));
    });
    // Re-centre: the rank's mean position equals the mean of what its nodes wanted.
    const wantMean = sorted.reduce((s, id) => s + preferred(id), 0) / sorted.length;
    const placedMean = placed.reduce((s, v) => s + v, 0) / placed.length;
    const shift = wantMean - placedMean;
    sorted.forEach((id, i) => {
      x[id] = placed[i] + shift;
    });
  }

  const positions: LayoutResult["positions"] = {};
  for (const id of nodeIds) positions[id] = { x: x[id] ?? 0, y: ranks[id] * gapY };
  return { positions, ranks };
}
