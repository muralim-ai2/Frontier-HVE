import { describe, expect, it } from "vitest";
import { getBestTextColor, getContrastLabel, getContrastRatio, hexToRgb, hslToHex, isValidHex, normalizeHex, rgbToHex, rgbToHsl } from "./color";
import { HARMONY_MODES, applyLocks, generatePalette, parsePaletteParam } from "./palette";
import { paletteToCssVariables, paletteToJson, paletteToSvg, paletteToTailwindConfig } from "./export";

const SAMPLE = ["264653", "2A9D8F", "E9C46A", "F4A261", "E76F51"];

describe("color", () => {
  it("normalizes hex input", () => {
    expect(normalizeHex("#4f46e5")).toBe("4F46E5");
    expect(normalizeHex("4f46e5")).toBe("4F46E5");
    expect(normalizeHex("#fff")).toBe("FFFFFF");
    expect(normalizeHex("#12345")).toBeNull();
    expect(normalizeHex("zzzzzz")).toBeNull();
    expect(isValidHex("abc")).toBe(true);
  });

  it("round-trips conversions", () => {
    expect(hexToRgb("264653")).toEqual({ r: 38, g: 70, b: 83 });
    expect(rgbToHex(38, 70, 83)).toBe("264653");
    expect(rgbToHsl(255, 0, 0)).toEqual({ h: 0, s: 100, l: 50 });
    expect(hslToHex(120, 100, 50)).toBe("00FF00");
    expect(hslToHex(480, 150, -5)).toBe("000000");
  });

  it("computes contrast and best text color", () => {
    expect(getContrastRatio("000000", "FFFFFF")).toBeCloseTo(21, 5);
    expect(getBestTextColor("FFFFFF")).toBe("black");
    expect(getBestTextColor("111827")).toBe("white");
    expect(getContrastLabel(8)).toBe("Good for text");
    expect(getContrastLabel(5)).toBe("Use carefully");
    expect(getContrastLabel(3)).toBe("Decorative only");
  });
});

describe("palette", () => {
  it("always returns 5 valid, non-uniform colors for every mode", () => {
    for (const mode of HARMONY_MODES) {
      for (let i = 0; i < 50; i++) {
        const p = generatePalette({ mode, seed: i % 2 ? "#4F46E5" : undefined });
        expect(p).toHaveLength(5);
        p.forEach((c) => expect(normalizeHex(c)).toBe(c));
        expect(new Set(p).size).toBeGreaterThan(1);
      }
    }
  });

  it("rejects invalid seeds", () => {
    expect(() => generatePalette({ mode: "analogous", seed: "nope" })).toThrow(/Invalid seed/);
  });

  it("preserves locked colors", () => {
    const next = ["000000", "111111", "222222", "333333", "444444"];
    expect(applyLocks(SAMPLE, next, [true, false, true, false, false])).toEqual(["264653", "111111", "E9C46A", "333333", "444444"]);
  });

  it("parses URL palettes and drops invalid entries", () => {
    expect(parsePaletteParam("264653,2A9D8F,E9C46A,F4A261,E76F51")).toEqual(SAMPLE);
    expect(parsePaletteParam("264653,xyz,#fff")).toEqual(["264653", "FFFFFF"]);
  });
});

describe("export", () => {
  it("formats exports", () => {
    expect(paletteToCssVariables(SAMPLE)).toContain("--color-1: #264653;");
    expect(paletteToTailwindConfig(SAMPLE)).toContain("5: '#E76F51',");
    expect(JSON.parse(paletteToJson(SAMPLE)).colors[2]).toBe("#E9C46A");
    expect(paletteToSvg(SAMPLE)).toContain('fill="#F4A261"');
  });
});
