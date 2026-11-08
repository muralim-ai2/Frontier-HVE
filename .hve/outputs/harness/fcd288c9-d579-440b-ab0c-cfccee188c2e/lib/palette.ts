/** Local color palette generation. */

import { hexToRgb, hslToHex, normalizeHex, rgbToHsl } from "./color";

export const HARMONY_MODES = ["Random", "Monochromatic", "Analogous", "Complementary", "Triadic", "Tetradic", "Pastel", "Vibrant", "Dark"] as const;
export type HarmonyMode = (typeof HARMONY_MODES)[number];
export interface GenerateOptions { mode: HarmonyMode; seed?: string; }

const random = (min: number, max: number): number => Math.random() * (max - min) + min;
const seedHsl = (seed?: string): { h: number; s: number; l: number } => {
  const normalized = seed ? normalizeHex(seed) : null;
  return normalized ? rgbToHsl(...Object.values(hexToRgb(normalized)) as [number, number, number]) : { h: random(0, 360), s: random(45, 78), l: random(38, 62) };
};
const tones = (hues: number[], saturation: number, lightness: number): string[] =>
  hues.slice(0, 5).map((hue, index) => hslToHex(hue, Math.max(20, Math.min(96, saturation + (index - 2) * 4)), Math.max(12, Math.min(88, lightness + (index - 2) * 7))));

/** Generate five unrelated but visually varied colors. */
export function generateRandomPalette(): string[] {
  const base = random(0, 360);
  return [0, 67, 139, 211, 293].map((offset, index) => hslToHex(base + offset + random(-18, 18), random(48, 88), index % 2 ? random(42, 66) : random(32, 58)));
}

/** Generate five shades from one hue. */
export function generateMonochromatic(seed?: string): string[] {
  const { h, s } = seedHsl(seed);
  return [20, 35, 50, 65, 80].map((lightness) => hslToHex(h, s, lightness));
}

/** Generate five neighboring hues. */
export function generateAnalogous(seed?: string): string[] {
  const { h, s, l } = seedHsl(seed);
  return tones([-50, -25, 0, 25, 50].map((offset) => h + offset), s, l);
}

/** Generate a palette around opposing hues. */
export function generateComplementary(seed?: string): string[] {
  const { h, s, l } = seedHsl(seed);
  return tones([h, h + 20, h + 180, h + 200, h + 340], s, l);
}

/** Generate a palette around three evenly spaced hues. */
export function generateTriadic(seed?: string): string[] {
  const { h, s, l } = seedHsl(seed);
  return tones([h, h + 120, h + 240, h + 15, h + 135], s, l);
}

/** Generate a palette around four evenly spaced hues. */
export function generateTetradic(seed?: string): string[] {
  const { h, s, l } = seedHsl(seed);
  return tones([h, h + 90, h + 180, h + 270, h + 30], s, l);
}

/** Generate a soft, light palette. */
export function generatePastel(seed?: string): string[] {
  const { h } = seedHsl(seed);
  return [0, 38, 82, 151, 218].map((offset, index) => hslToHex(h + offset, 52 + index * 3, 78 + (index % 2) * 6));
}

/** Generate a highly saturated palette. */
export function generateVibrant(seed?: string): string[] {
  const { h } = seedHsl(seed);
  return [0, 58, 129, 204, 287].map((offset, index) => hslToHex(h + offset, 88, 47 + (index % 3) * 6));
}

/** Generate a deep, low-lightness palette. */
export function generateDark(seed?: string): string[] {
  const { h } = seedHsl(seed);
  return [0, 46, 112, 188, 271].map((offset, index) => hslToHex(h + offset, 48 + index * 5, 16 + index * 5));
}

/** Generate exactly five colors for the selected harmony. */
export function generatePalette(options: GenerateOptions): string[] {
  const generators: Record<HarmonyMode, (seed?: string) => string[]> = {
    Random: generateRandomPalette,
    Monochromatic: generateMonochromatic,
    Analogous: generateAnalogous,
    Complementary: generateComplementary,
    Triadic: generateTriadic,
    Tetradic: generateTetradic,
    Pastel: generatePastel,
    Vibrant: generateVibrant,
    Dark: generateDark,
  };
  return generators[options.mode](options.seed);
}

/** Preserve colors marked as locked while applying a generated palette. */
export function applyLocks(existingPalette: string[], newPalette: string[], lockedMap: boolean[]): string[] {
  if (existingPalette.length !== 5 || newPalette.length !== 5 || lockedMap.length !== 5) throw new Error("Palettes and lock map must contain exactly five entries.");
  return newPalette.map((color, index) => lockedMap[index] ? existingPalette[index] : color);
}