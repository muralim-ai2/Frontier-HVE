/** Local palette generation for each harmony mode. */
import { hexToHsl, hslToHex, normalizeHex, wrapHue } from "./color";

export const PALETTE_SIZE = 5;

export const HARMONY_MODES = [
  "random",
  "monochromatic",
  "analogous",
  "complementary",
  "triadic",
  "tetradic",
  "pastel",
  "vibrant",
  "dark",
] as const;

export type HarmonyMode = (typeof HARMONY_MODES)[number];
export type Palette = string[];

export interface GenerateOptions {
  mode: HarmonyMode;
  seed?: string;
}

type Hsl3 = [number, number, number];

const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value));
const rand = (min: number, max: number): number => min + Math.random() * (max - min);

function toPalette(colors: Hsl3[]): Palette {
  return colors.map(([h, s, l]) => hslToHex(wrapHue(h), clamp(s, 0, 100), clamp(l, 0, 100)));
}

function seedHsl(seed: string | undefined): Hsl3 {
  if (seed === undefined) return [rand(0, 360), rand(45, 85), rand(40, 60)];
  const n = normalizeHex(seed);
  if (n === null) throw new Error(`Invalid seed color: "${seed}"`);
  const { h, s, l } = hexToHsl(n);
  return [h, s, l];
}

/** Return 5 shades of the seed hue across a lightness range. */
export function generateMonochromatic(seed?: string): Palette {
  const [h, s] = seedHsl(seed);
  const sat = clamp(s, 25, 90);
  return toPalette([18, 34, 50, 66, 84].map((l, i): Hsl3 => [h, sat - i * 4, l]));
}

/** Return 5 neighboring hues around the seed. */
export function generateAnalogous(seed?: string): Palette {
  const [h, s, l] = seedHsl(seed);
  const sat = clamp(s, 40, 85);
  const light = clamp(l, 35, 65);
  return toPalette([
    [h - 40, sat, light - 15],
    [h - 20, sat, light + 10],
    [h, sat, light],
    [h + 20, sat, light + 22],
    [h + 40, sat, light - 25],
  ]);
}

/** Return the seed hue plus its complement in varied lightness. */
export function generateComplementary(seed?: string): Palette {
  const [h, s, l] = seedHsl(seed);
  const sat = clamp(s, 40, 85);
  return toPalette([
    [h, sat, 22],
    [h, sat, clamp(l, 38, 58)],
    [h, sat * 0.4, 90],
    [h + 180, sat, 62],
    [h + 180, sat, 40],
  ]);
}

/** Return three evenly spaced hues plus tints. */
export function generateTriadic(seed?: string): Palette {
  const [h, s, l] = seedHsl(seed);
  const sat = clamp(s, 45, 85);
  const light = clamp(l, 40, 60);
  return toPalette([
    [h, sat, light],
    [h + 120, sat, light],
    [h + 240, sat, light],
    [h, sat * 0.5, 88],
    [h + 120, sat, 25],
  ]);
}

/** Return four hues spaced 90 degrees apart plus a neutral tint. */
export function generateTetradic(seed?: string): Palette {
  const [h, s, l] = seedHsl(seed);
  const sat = clamp(s, 45, 85);
  const light = clamp(l, 40, 60);
  return toPalette([
    [h, sat, light],
    [h + 90, sat, light + 8],
    [h + 180, sat, light],
    [h + 270, sat, light - 10],
    [h, sat * 0.3, 92],
  ]);
}

function spreadHues(h: number, sRange: [number, number], lRange: [number, number]): Palette {
  return toPalette(
    Array.from({ length: PALETTE_SIZE }, (_, i): Hsl3 => [h + i * 72 + rand(-12, 12), rand(...sRange), rand(...lRange)]),
  );
}

/** Return 5 soft, light colors with spread hues. */
export function generatePastel(seed?: string): Palette {
  return spreadHues(seedHsl(seed)[0], [55, 80], [78, 90]);
}

/** Return 5 saturated colors with spread hues. */
export function generateVibrant(seed?: string): Palette {
  return spreadHues(seedHsl(seed)[0], [80, 100], [45, 60]);
}

/** Return 5 deep, dark colors with spread hues. */
export function generateDark(seed?: string): Palette {
  return spreadHues(seedHsl(seed)[0], [30, 65], [10, 32]);
}

/** Return 5 colors with random hue, saturation, and lightness. */
export function generateRandomPalette(): Palette {
  const base = rand(0, 360);
  return toPalette(
    Array.from({ length: PALETTE_SIZE }, (_, i): Hsl3 => [base + i * 72 + rand(-30, 30), rand(30, 90), 15 + i * 17 + rand(-6, 6)]).sort(
      () => Math.random() - 0.5,
    ),
  );
}

const GENERATORS: Record<Exclude<HarmonyMode, "random">, (seed?: string) => Palette> = {
  monochromatic: generateMonochromatic,
  analogous: generateAnalogous,
  complementary: generateComplementary,
  triadic: generateTriadic,
  tetradic: generateTetradic,
  pastel: generatePastel,
  vibrant: generateVibrant,
  dark: generateDark,
};

/** Generate a 5-color palette for the given mode and optional seed. */
export function generatePalette({ mode, seed }: GenerateOptions): Palette {
  return mode === "random" ? generateRandomPalette() : GENERATORS[mode](seed);
}

/** Keep locked colors from the existing palette and take the rest from the new one. */
export function applyLocks(existingPalette: Palette, newPalette: Palette, lockedMap: boolean[]): Palette {
  return newPalette.map((color, i) => (lockedMap[i] ? existingPalette[i] : color));
}

/** Parse a comma-separated palette query value into valid hex colors (at most 5). */
export function parsePaletteParam(param: string): Palette {
  return param
    .split(",")
    .map((c) => normalizeHex(c))
    .filter((c): c is string => c !== null)
    .slice(0, PALETTE_SIZE);
}

/** Human-readable label for a harmony mode. */
export function modeLabel(mode: HarmonyMode): string {
  return mode.charAt(0).toUpperCase() + mode.slice(1);
}
