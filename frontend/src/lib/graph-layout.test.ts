import { describe, it, expect } from "vitest";

import { layeredLayout } from "./graph-layout";

// The deployed agent graph (app/agents/graph.py EDGES), including the Video sub-agent fan-out.
const NODES = [
  "START",
  "affect_detection",
  "learner_profiler",
  "log_only",
  "pedagogical",
  "content_adapter",
  "video_resource",
  "deliver",
  "END",
];
const EDGES = [
  { from: "START", to: "affect_detection" },
  { from: "affect_detection", to: "learner_profiler" },
  { from: "learner_profiler", to: "log_only" },
  { from: "learner_profiler", to: "pedagogical" },
  { from: "pedagogical", to: "content_adapter" },
  { from: "pedagogical", to: "video_resource" },
  { from: "content_adapter", to: "deliver" },
  { from: "video_resource", to: "deliver" },
  { from: "deliver", to: "END" },
  { from: "log_only", to: "END" },
];

describe("layeredLayout", () => {
  const { positions, ranks } = layeredLayout(NODES, EDGES, { gapX: 200, gapY: 100 });

  it("ranks by longest path, so joins sit below every branch they merge", () => {
    expect(ranks.START).toBe(0);
    expect(ranks.learner_profiler).toBe(2);
    expect(ranks.log_only).toBe(3);
    expect(ranks.pedagogical).toBe(3);
    expect(ranks.content_adapter).toBe(4);
    expect(ranks.video_resource).toBe(4);
    expect(ranks.deliver).toBe(5);
    expect(ranks.END).toBe(6);
    expect(positions.END.y).toBe(600);
  });

  it("spreads a conditional branch and a fan-out symmetrically under their parent", () => {
    expect(positions.log_only.x).toBeCloseTo(positions.learner_profiler.x - 100);
    expect(positions.pedagogical.x).toBeCloseTo(positions.learner_profiler.x + 100);
    const mid = (positions.content_adapter.x + positions.video_resource.x) / 2;
    expect(mid).toBeCloseTo(positions.pedagogical.x);
    expect(Math.abs(positions.content_adapter.x - positions.video_resource.x)).toBe(200);
  });

  it("centres a join under the branches it merges", () => {
    const mid = (positions.content_adapter.x + positions.video_resource.x) / 2;
    expect(positions.deliver.x).toBeCloseTo(mid);
  });

  it("keeps the spine on one vertical line", () => {
    expect(positions.affect_detection.x).toBe(positions.START.x);
    expect(positions.learner_profiler.x).toBe(positions.START.x);
  });

  it("ignores edges to unknown nodes and survives a cycle", () => {
    const out = layeredLayout(["a", "b"], [
      { from: "a", to: "b" },
      { from: "b", to: "a" },
      { from: "a", to: "ghost" },
    ]);
    expect(Object.keys(out.positions)).toEqual(["a", "b"]);
  });
});
