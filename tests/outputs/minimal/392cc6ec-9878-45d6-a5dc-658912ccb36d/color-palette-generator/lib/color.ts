/** Color conversion and WCAG contrast utilities. */
export type RGB = [number, number, number];
export type HSL = [number, number, number];
const clamp = (value: number, maximum: number): number => { if (!Number.isFinite(value)) throw new Error("Color components must be finite."); return Math.min(maximum, Math.max(0, value)); };
/** Normalize three- or six-digit HEX input. */
export function normalizeHex(input: string): string | null { const hex = input.trim().replace(/^#/, ""); return /^[\da-f]{3}$/i.test(hex) ? hex.split("").map((digit: string): string => digit + digit).join("").toUpperCase() : /^[\da-f]{6}$/i.test(hex) ? hex.toUpperCase() : null; }
/** Check whether input is a HEX color. */
export function isValidHex(input: string): boolean { return normalizeHex(input) !== null; }
/** Convert HEX to RGB channels. */
export function hexToRgb(hex: string): RGB { const normalized = normalizeHex(hex); if (!normalized) throw new Error(`Invalid HEX color: ${hex}`); return [0, 2, 4].map((offset: number): number => parseInt(normalized.slice(offset, offset + 2), 16)) as RGB; }
/** Convert RGB channels to uppercase HEX. */
export function rgbToHex(red: number, green: number, blue: number): string { return [red, green, blue].map((channel: number): string => Math.round(clamp(channel, 255)).toString(16).padStart(2, "0")).join("").toUpperCase(); }
/** Convert RGB channels to HSL degrees and percentages. */
export function rgbToHsl(red: number, green: number, blue: number): HSL {
  const channels = [red, green, blue].map((channel: number): number => clamp(channel, 255) / 255); const [rr, gg, bb] = channels; const maximum = Math.max(...channels), minimum = Math.min(...channels), delta = maximum - minimum, lightness = (maximum + minimum) / 2;
  const hue = delta === 0 ? 0 : maximum === rr ? ((gg - bb) / delta) % 6 : maximum === gg ? (bb - rr) / delta + 2 : (rr - gg) / delta + 4;
  return [((hue * 60) + 360) % 360, delta === 0 ? 0 : delta / (1 - Math.abs(2 * lightness - 1)) * 100, lightness * 100];
}
/** Convert HSL degrees and percentages to RGB channels. */
export function hslToRgb(hue: number, saturation: number, lightness: number): RGB {
  if (!Number.isFinite(hue)) throw new Error("Hue must be finite."); const wrapped = ((hue % 360) + 360) % 360, sat = clamp(saturation, 100) / 100, light = clamp(lightness, 100) / 100;
  const amplitude = sat * Math.min(light, 1 - light); return [0, 8, 4].map((offset: number): number => { const position = (offset + wrapped / 30) % 12; return Math.round(255 * (light - amplitude * Math.max(-1, Math.min(position - 3, 9 - position, 1)))); }) as RGB;
}
/** Convert HSL to uppercase HEX. */
export function hslToHex(hue: number, saturation: number, lightness: number): string { return rgbToHex(...hslToRgb(hue, saturation, lightness)); }
/** Calculate WCAG relative luminance. */
export function getRelativeLuminance(rgb: RGB): number { return rgb.map((channel: number): number => { const value = clamp(channel, 255) / 255; return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4; }).reduce((sum: number, channel: number, index: number): number => sum + channel * [0.2126, 0.7152, 0.0722][index], 0); }
/** Calculate contrast between two HEX colors. */
export function getContrastRatio(colorA: string, colorB: string): number { const first = getRelativeLuminance(hexToRgb(colorA)), second = getRelativeLuminance(hexToRgb(colorB)); return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05); }
/** Return the higher-contrast black or white text color. */
export function getBestTextColor(hex: string): "black" | "white" { return getContrastRatio(hex, "000000") >= getContrastRatio(hex, "FFFFFF") ? "black" : "white"; }
