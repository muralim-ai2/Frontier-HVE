/** Local five-color harmony generation. */
import { hexToRgb, hslToHex, normalizeHex, rgbToHsl } from "./color";
export const modes = ["Random", "Monochromatic", "Analogous", "Complementary", "Triadic", "Tetradic", "Pastel", "Vibrant", "Dark"] as const;
export type Mode = typeof modes[number];
const randomSeed = (): string => hslToHex(Math.random() * 360, 45 + Math.random() * 40, 35 + Math.random() * 30);
/** Generate five normalized HEX colors using the selected harmony. */
export function generatePalette(options: { mode: Mode; seed?: string }): string[] {
  if (!modes.includes(options.mode)) throw new Error("Unknown harmony mode."); const seed = options.seed === undefined ? randomSeed() : normalizeHex(options.seed); if (!seed) throw new Error("Enter a valid HEX color like #4F46E5.");
  const [hue, saturation, lightness] = rgbToHsl(...hexToRgb(seed)); const offsets: Record<Mode, number[]> = { Random: [0, 65, 145, 210, 290], Monochromatic: [0, 0, 0, 0, 0], Analogous: [0, -40, -20, 20, 40], Complementary: [0, 0, 180, 180, 0], Triadic: [0, 120, 240, 120, 240], Tetradic: [0, 90, 180, 270, 90], Pastel: [0, 45, 130, 210, 290], Vibrant: [0, 45, 130, 210, 290], Dark: [0, 45, 130, 210, 290] };
  return offsets[options.mode].map((offset: number, index: number): string => {
    if (index === 0 && !["Pastel", "Vibrant", "Dark"].includes(options.mode)) return seed;
    const sat = options.mode === "Pastel" ? 55 : options.mode === "Vibrant" ? 85 : Math.max(35, Math.min(85, saturation));
    const light = options.mode === "Monochromatic" ? [lightness, 18, 38, 65, 85][index] : options.mode === "Pastel" ? 78 + index * 3 : options.mode === "Dark" ? 12 + index * 6 : options.mode === "Vibrant" ? 43 + index * 5 : [lightness, 28, 48, 68, 85][index];
    return hslToHex(hue + offset + (options.mode === "Random" ? Math.random() * 30 - 15 : 0), sat, light);
  });
}
/** Generate a random palette. */
export function generateRandomPalette(): string[] { return generatePalette({ mode: "Random" }); }
/** Generate a monochromatic palette. */
export function generateMonochromatic(seed: string): string[] { return generatePalette({ mode: "Monochromatic", seed }); }
/** Generate an analogous palette. */
export function generateAnalogous(seed: string): string[] { return generatePalette({ mode: "Analogous", seed }); }
/** Generate a complementary palette. */
export function generateComplementary(seed: string): string[] { return generatePalette({ mode: "Complementary", seed }); }
/** Generate a triadic palette. */
export function generateTriadic(seed: string): string[] { return generatePalette({ mode: "Triadic", seed }); }
/** Generate a tetradic palette. */
export function generateTetradic(seed: string): string[] { return generatePalette({ mode: "Tetradic", seed }); }
/** Generate a pastel palette. */
export function generatePastel(seed?: string): string[] { return generatePalette({ mode: "Pastel", seed }); }
/** Generate a vibrant palette. */
export function generateVibrant(seed?: string): string[] { return generatePalette({ mode: "Vibrant", seed }); }
/** Generate a dark palette. */
export function generateDark(seed?: string): string[] { return generatePalette({ mode: "Dark", seed }); }
/** Preserve locked colors from an existing palette. */
export function applyLocks(existingPalette: string[], newPalette: string[], lockedMap: boolean[]): string[] { if ([existingPalette.length, newPalette.length, lockedMap.length].some((length: number): boolean => length !== 5)) throw new Error("Palettes and locks must contain five entries."); return newPalette.map((hex: string, index: number): string => { const color = normalizeHex(lockedMap[index] ? existingPalette[index] : hex); if (!color) throw new Error("Palette contains an invalid color."); return color; }); }
