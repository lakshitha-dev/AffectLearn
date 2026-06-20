import { describe, it, expect } from "vitest";
import {
  PREPROCESS_CONTRACT,
  FLOATS_PER_FRAME,
  normalizeRgbaToChwFloat32,
  toBase64,
  framesToBase64,
} from "./preprocess";

describe("PREPROCESS_CONTRACT", () => {
  it("locks cropSize at 96", () => {
    expect(PREPROCESS_CONTRACT.cropSize).toBe(96);
  });

  it("uses RGB (not BGR) channel order", () => {
    expect(PREPROCESS_CONTRACT.channelOrder).toBe("RGB");
    expect(PREPROCESS_CONTRACT.channels).toBe(3);
  });

  it("uses ImageNet mean/std", () => {
    expect(PREPROCESS_CONTRACT.mean).toEqual([0.485, 0.456, 0.406]);
    expect(PREPROCESS_CONTRACT.std).toEqual([0.229, 0.224, 0.225]);
  });

  it("locks cycle window at 30 seconds, 1 fps, 30 expected frames", () => {
    expect(PREPROCESS_CONTRACT.frameSamplingHz).toBe(1);
    expect(PREPROCESS_CONTRACT.cycleDurationSeconds).toBe(30);
    expect(PREPROCESS_CONTRACT.expectedFramesPerCycle).toBe(30);
  });

  it("inference window matches CNN-LSTM training (16 frames)", () => {
    expect(PREPROCESS_CONTRACT.framesPerInferenceWindow).toBe(16);
  });

  it("FLOATS_PER_FRAME equals 3*96*96 = 27648", () => {
    expect(FLOATS_PER_FRAME).toBe(27648);
  });
});

describe("normalizeRgbaToChwFloat32", () => {
  // Helper: build a 96x96 RGBA buffer where every pixel has the same constant color.
  function constantRgba(r: number, g: number, b: number): Uint8ClampedArray {
    const len = 96 * 96 * 4;
    const arr = new Uint8ClampedArray(len);
    for (let i = 0; i < len; i += 4) {
      arr[i] = r;
      arr[i + 1] = g;
      arr[i + 2] = b;
      arr[i + 3] = 255;
    }
    return arr;
  }

  it("rejects buffers of the wrong length", () => {
    expect(() => normalizeRgbaToChwFloat32(new Uint8ClampedArray(100))).toThrow(
      /expected 36864 bytes/,
    );
  });

  it("returns a Float32Array of length 27648 (CHW = 3*96*96)", () => {
    const result = normalizeRgbaToChwFloat32(constantRgba(128, 128, 128));
    expect(result).toBeInstanceOf(Float32Array);
    expect(result.length).toBe(FLOATS_PER_FRAME);
  });

  it("normalizes mid-gray (128) per channel using ImageNet stats", () => {
    const result = normalizeRgbaToChwFloat32(constantRgba(128, 128, 128));
    const v = 128 / 255;
    const expectedR = (v - 0.485) / 0.229;
    const expectedG = (v - 0.456) / 0.224;
    const expectedB = (v - 0.406) / 0.225;
    // First pixel of each channel (CHW order: R-plane at offset 0, G at 96*96, B at 2*96*96).
    expect(result[0]).toBeCloseTo(expectedR, 5);
    expect(result[96 * 96]).toBeCloseTo(expectedG, 5);
    expect(result[2 * 96 * 96]).toBeCloseTo(expectedB, 5);
  });

  it("normalizes a pure-black image to negative values (since 0 < ImageNet means)", () => {
    const result = normalizeRgbaToChwFloat32(constantRgba(0, 0, 0));
    expect(result[0]).toBeCloseTo(-0.485 / 0.229, 5);
    expect(result[96 * 96]).toBeCloseTo(-0.456 / 0.224, 5);
    expect(result[2 * 96 * 96]).toBeCloseTo(-0.406 / 0.225, 5);
  });

  it("normalizes pure white (255) above zero on every channel", () => {
    const result = normalizeRgbaToChwFloat32(constantRgba(255, 255, 255));
    expect(result[0]).toBeCloseTo((1 - 0.485) / 0.229, 5);
    expect(result[96 * 96]).toBeCloseTo((1 - 0.456) / 0.224, 5);
    expect(result[2 * 96 * 96]).toBeCloseTo((1 - 0.406) / 0.225, 5);
  });

  it("respects CHW layout — every pixel in R plane comes before G plane", () => {
    // Pure red: R=255, G=0, B=0. The R plane should be one (large positive) value,
    // G/B planes should be one (large negative) value.
    const result = normalizeRgbaToChwFloat32(constantRgba(255, 0, 0));
    // All values in R plane (indices [0, 96*96)) should be identical and positive.
    for (let i = 0; i < 96 * 96; i++) {
      expect(result[i]).toBeCloseTo((1 - 0.485) / 0.229, 5);
    }
    // All values in G plane should be identical and negative.
    for (let i = 96 * 96; i < 2 * 96 * 96; i++) {
      expect(result[i]).toBeCloseTo((0 - 0.456) / 0.224, 5);
    }
    // All values in B plane should be identical and negative.
    for (let i = 2 * 96 * 96; i < 3 * 96 * 96; i++) {
      expect(result[i]).toBeCloseTo((0 - 0.406) / 0.225, 5);
    }
  });
});

describe("toBase64 / framesToBase64", () => {
  it("returns empty string for an empty tensor", () => {
    expect(toBase64(new Float32Array(0))).toBe("");
  });

  it("returns empty string for zero frames", () => {
    expect(framesToBase64([])).toBe("");
  });

  it("round-trips a Float32Array through base64 → bytes → floats within FP epsilon", () => {
    const original = new Float32Array(27648);
    for (let i = 0; i < original.length; i++) {
      original[i] = Math.sin(i * 0.001);
    }

    const encoded = toBase64(original);
    expect(typeof encoded).toBe("string");
    expect(encoded.length).toBeGreaterThan(0);

    // Decode and verify.
    const binary = atob(encoded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    const decoded = new Float32Array(bytes.buffer);

    expect(decoded.length).toBe(original.length);
    for (let i = 0; i < original.length; i++) {
      expect(decoded[i]).toBeCloseTo(original[i], 6);
    }
  });

  it("handles a 30-frame concatenated buffer (full cycle ≈ 3.3MB)", () => {
    const frames: Float32Array[] = [];
    for (let f = 0; f < 30; f++) {
      const frame = new Float32Array(FLOATS_PER_FRAME);
      frame.fill(f / 30);
      frames.push(frame);
    }
    const encoded = framesToBase64(frames);
    expect(encoded.length).toBeGreaterThan(0);

    // Decode and verify shape + a sentinel value from frame 15 (mid-cycle).
    const binary = atob(encoded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const decoded = new Float32Array(bytes.buffer);
    expect(decoded.length).toBe(30 * FLOATS_PER_FRAME);
    const frame15Start = 15 * FLOATS_PER_FRAME;
    expect(decoded[frame15Start]).toBeCloseTo(15 / 30, 5);
  });
});
