import { describe, expect, it } from "vitest";
import { getBestTextColor, getContrastRatio, normalizeHex, rgbToHex } from "./color";
import { applyLocks, generatePalette, HARMONY_MODES } from "./palette";

describe("color utilities", () => {
  it("normalizes short and long hex values", () => {
    expect(normalizeHex("#fff")).toBe("FFFFFF");
    expect(normalizeHex("4f46e5")).toBe("4F46E5");
    expect(normalizeHex("nope")).toBeNull();
  });

  it("clamps RGB values and calculates readable contrast", () => {
    expect(rgbToHex(300, -4, 128)).toBe("#FF0080");
    expect(getContrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21);
    expect(getBestTextColor("#111111")).toBe("#FFFFFF");
  });
});

describe("palette generation", () => {
  it.each(HARMONY_MODES)("generates five valid colors for %s", (mode) => {
    const palette = generatePalette({ mode, seed: "#4F46E5" });
    expect(palette).toHaveLength(5);
    expect(palette.every((color) => /^#[0-9A-F]{6}$/.test(color))).toBe(true);
    if (mode !== "Monochromatic") expect(new Set(palette).size).toBeGreaterThan(3);
  });

  it("preserves locked positions", () => {
    expect(applyLocks(["#111111", "#222222", "#333333", "#444444", "#555555"], ["#AAAAAA", "#BBBBBB", "#CCCCCC", "#DDDDDD", "#EEEEEE"], [true, false, true, false, false]))
      .toEqual(["#111111", "#BBBBBB", "#333333", "#DDDDDD", "#EEEEEE"]);
  });
});