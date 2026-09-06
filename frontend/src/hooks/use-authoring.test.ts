/**
 * Tests for the authoring helpers.
 *
 * The reorder logic is the part worth pinning. `sort_order` carries a UNIQUE(parent, sort_order)
 * constraint, so the obvious implementation — write A's position to B, then B's to A — fails on
 * the first write, because for that instant two siblings hold the same value. The bug would look
 * like an intermittent 409 that only appears once a course has more than one module, which is
 * exactly the kind of thing that ships.
 */

import { describe, it, expect, vi } from "vitest";

import { nextSortOrder, swapOrder, type Orderable } from "./use-authoring";

describe("nextSortOrder", () => {
  it("starts at zero for an empty list", () => {
    expect(nextSortOrder([])).toBe(0);
  });

  it("appends after the highest existing position", () => {
    expect(nextSortOrder([{ id: "a", sortOrder: 0 }, { id: "b", sortOrder: 1 }])).toBe(2);
  });

  it("does not assume positions are contiguous", () => {
    // Deleting a middle sibling leaves a gap, and the next item must still land past the end
    // rather than reusing a freed number that a later reorder could collide with.
    expect(nextSortOrder([{ id: "a", sortOrder: 0 }, { id: "c", sortOrder: 7 }])).toBe(8);
  });
});

describe("swapOrder", () => {
  const items: Orderable[] = [
    { id: "a", sortOrder: 0 },
    { id: "b", sortOrder: 1 },
    { id: "c", sortOrder: 2 },
  ];

  it("never leaves two siblings holding the same position", async () => {
    // The whole point. Replays the writes against a model of the unique constraint and fails if
    // any single write would have collided.
    const positions = new Map(items.map((i) => [i.id, i.sortOrder]));
    const update = vi.fn(async (id: string, sortOrder: number) => {
      const clash = [...positions.entries()].find(
        ([otherId, other]) => otherId !== id && other === sortOrder,
      );
      if (clash) {
        throw new Error(
          `unique violation: ${id} -> ${sortOrder} collides with ${clash[0]}`,
        );
      }
      positions.set(id, sortOrder);
    });

    await expect(swapOrder(items, items[0], items[1], update)).resolves.toBeUndefined();
  });

  it("ends with the two siblings exchanged", async () => {
    const positions = new Map(items.map((i) => [i.id, i.sortOrder]));
    const update = async (id: string, sortOrder: number) => {
      positions.set(id, sortOrder);
    };

    await swapOrder(items, items[0], items[1], update);

    expect(positions.get("a")).toBe(1);
    expect(positions.get("b")).toBe(0);
  });

  it("leaves every other sibling where it was", async () => {
    const positions = new Map(items.map((i) => [i.id, i.sortOrder]));
    const update = async (id: string, sortOrder: number) => {
      positions.set(id, sortOrder);
    };

    await swapOrder(items, items[0], items[1], update);

    expect(positions.get("c")).toBe(2);
  });

  it("parks outside the used range so the temporary position cannot collide", async () => {
    const seen: number[] = [];
    const update = async (_id: string, sortOrder: number) => {
      seen.push(sortOrder);
    };

    await swapOrder(items, items[0], items[1], update);

    // First write is the parking slot, and it must be beyond every real position.
    expect(seen[0]).toBeGreaterThan(Math.max(...items.map((i) => i.sortOrder)));
  });

  it("works on non-adjacent siblings", async () => {
    const positions = new Map(items.map((i) => [i.id, i.sortOrder]));
    const update = async (id: string, sortOrder: number) => {
      positions.set(id, sortOrder);
    };

    await swapOrder(items, items[0], items[2], update);

    expect(positions.get("a")).toBe(2);
    expect(positions.get("c")).toBe(0);
  });

  it("takes exactly three writes", async () => {
    // A fourth would mean an extra round trip on every reorder click.
    const update = vi.fn(async () => {});
    await swapOrder(items, items[0], items[1], update);
    expect(update).toHaveBeenCalledTimes(3);
  });
});
