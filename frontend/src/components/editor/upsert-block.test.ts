/**
 * Regression tests for the editor's silent-write bug.
 *
 * The quiz and exercise tabs used to write only when a block of their type already existed
 * (`if (quizBlock) { PUT }`) while toasting "saved" unconditionally. Authoring the FIRST quiz for
 * a section therefore stored nothing and reported success. These tests pin the create path, which
 * is the half that was missing, and the throw-rather-than-succeed behaviour when there is nowhere
 * to write — because the failure mode being guarded is a save that claims to have happened.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

import { upsertBlock } from "./upsert-block";
import type { SectionDetail } from "@/types/course";

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api-client", () => ({ apiFetch }));

function section(overrides: Partial<SectionDetail> = {}): SectionDetail {
  return {
    id: "sec-1",
    title: "Section",
    sortOrder: 0,
    contentBlocks: [],
    createdAt: "",
    updatedAt: "",
    ...overrides,
  } as SectionDetail;
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ id: "blk-new" });
});

describe("upsertBlock", () => {
  it("CREATES the block when the section has none of that type", async () => {
    await upsertBlock({
      section: section(),
      blockType: "quiz",
      content: { question: "Why?" },
    });

    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe("/courses/sections/sec-1/content-blocks");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toMatchObject({
      blockType: "quiz",
      content: { question: "Why?" },
      sortOrder: 0,
    });
  });

  it("UPDATES in place when a block of that type already exists", async () => {
    const existing = section({
      contentBlocks: [
        { id: "blk-7", blockType: "quiz", content: {}, sortOrder: 0, variantKey: "original" },
      ] as SectionDetail["contentBlocks"],
    });

    await upsertBlock({ section: existing, blockType: "quiz", content: { question: "New" } });

    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe("/courses/content-blocks/blk-7");
    expect(init.method).toBe("PUT");
  });

  it("appends after existing blocks rather than colliding on sortOrder", async () => {
    const existing = section({
      contentBlocks: [
        { id: "b1", blockType: "text", content: {}, sortOrder: 0, variantKey: "original" },
        { id: "b2", blockType: "code", content: {}, sortOrder: 1, variantKey: "original" },
      ] as SectionDetail["contentBlocks"],
    });

    await upsertBlock({ section: existing, blockType: "quiz", content: {} });

    expect(JSON.parse(apiFetch.mock.calls[0][1].body).sortOrder).toBe(2);
  });

  it("does not target a block of a DIFFERENT type", async () => {
    const existing = section({
      contentBlocks: [
        { id: "b1", blockType: "exercise", content: {}, sortOrder: 0, variantKey: "original" },
      ] as SectionDetail["contentBlocks"],
    });

    await upsertBlock({ section: existing, blockType: "quiz", content: {} });

    // Must create a quiz block, not overwrite the exercise one.
    expect(apiFetch.mock.calls[0][0]).toBe("/courses/sections/sec-1/content-blocks");
  });

  it("throws instead of silently succeeding when the lesson has no section", async () => {
    await expect(
      upsertBlock({ section: undefined, blockType: "quiz", content: {} })
    ).rejects.toThrow(/no sections/i);
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
