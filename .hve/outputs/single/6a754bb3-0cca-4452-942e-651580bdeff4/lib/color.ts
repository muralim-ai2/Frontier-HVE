/** Color parsing, conversion, and WCAG contrast helpers. Hex values are 6-char uppercase without '#'. */

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

export interface Hsl {
  h: number;
  s: number;
  l: number;
}

export type TextColor = "black" | "white";
export type ContrastLabel = "Good for text" | "Use carefully" | "Decorative only";

const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value));

/** Wrap a hue into the range [0, 360). */
export function wrapHue(h: number): number {
  return ((h % 360) + 360) % 360;
}

/** Return a 6-char uppercase hex without '#' from 3- or 6-digit input, or null if invalid. */
export function normalizeHex(input: string): string | null {
  const raw = input.trim().replace(/^#/, "");
  if (/^[0-9a-fA-F]{6}$/.test(raw)) return raw.toUpperCase();
  if (/^[0-9a-fA-F]{3}$/.test(raw)) return raw.split("").map((c) => c + c).join("").toUpperCase();
  return null;
}

/** Return whether the input is a valid 3- or 6-digit hex color. */
export function isValidHex(input: string): boolean {
  return normalizeHex(input) !== null;
}

/** Convert a hex color to RGB channels. */
export function hexToRgb(hex: string): Rgb {
  const n = normalizeHex(hex);
  if (n === null) throw new Error(`Invalid hex color: "${hex}"`);
  return { r: parseInt(n.slice(0, 2), 16), g: parseInt(n.slice(2, 4), 16), b: parseInt(n.slice(4, 6), 16) };
}

/** Convert RGB channels to a 6-char uppercase hex. */
export function rgbToHex(r: number, g: number, b: number): string {
  return [r, g, b]
    .map((c) => Math.round(clamp(c, 0, 255)).toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
}

/** Convert RGB channels to HSL (h 0-360, s/l 0-100). */
export function rgbToHsl(r: number, g: number, b: number): Hsl {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return { h: 0, s: 0, l: Math.round(l * 100) };
  const s = d / (1 - Math.abs(2 * l - 1));
  let h: number;
  if (max === rn) h = ((gn - bn) / d) % 6;
  else if (max === gn) h = (bn - rn) / d + 2;
  else h = (rn - gn) / d + 4;
  return { h: Math.round(wrapHue(h * 60)), s: Math.round(s * 100), l: Math.round(l * 100) };
}

/** Convert HSL (h any degrees, s/l 0-100, clamped) to RGB channels. */
export function hslToRgb(h: number, s: number, l: number): Rgb {
  const hh = wrapHue(h);
  const ss = clamp(s, 0, 100) / 100;
  const ll = clamp(l, 0, 100) / 100;
  const c = (1 - Math.abs(2 * ll - 1)) * ss;
  const x = c * (1 - Math.abs(((hh / 60) % 2) - 1));
  const m = ll - c / 2;
  const [r1, g1, b1] =
    hh < 60 ? [c, x, 0] : hh < 120 ? [x, c, 0] : hh < 180 ? [0, c, x] : hh < 240 ? [0, x, c] : hh < 300 ? [x, 0, c] : [c, 0, x];
  return { r: Math.round((r1 + m) * 255), g: Math.round((g1 + m) * 255), b: Math.round((b1 + m) * 255) };
}

/** Convert HSL to a 6-char uppercase hex. */
export function hslToHex(h: number, s: number, l: number): string {
  const { r, g, b } = hslToRgb(h, s, l);
  return rgbToHex(r, g, b);
}

/** Convert a hex color to HSL. */
export function hexToHsl(hex: string): Hsl {
  const { r, g, b } = hexToRgb(hex);
  return rgbToHsl(r, g, b);
}

/** Return the WCAG relative luminance of an RGB color. */
export function getRelativeLuminance({ r, g, b }: Rgb): number {
  const lin = (c: number): number => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** Return the WCAG contrast ratio between two hex colors. */
export function getContrastRatio(colorA: string, colorB: string): number {
  const la = getRelativeLuminance(hexToRgb(colorA));
  const lb = getRelativeLuminance(hexToRgb(colorB));
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Return the more readable text color (black or white) on the given background. */
export function getBestTextColor(hex: string): TextColor {
  return getContrastRatio(hex, "000000") >= getContrastRatio(hex, "FFFFFF") ? "black" : "white";
}

/** Return a simplified readability label for a contrast ratio. */
export function getContrastLabel(ratio: number): ContrastLabel {
  if (ratio >= 7) return "Good for text";
  if (ratio >= 4.5) return "Use carefully";
  return "Decorative only";
}

/** Format a hex color as a CSS rgb() string. */
export function formatRgb(hex: string): string {
  const { r, g, b } = hexToRgb(hex);
  return `rgb(${r}, ${g}, ${b})`;
}

/** Format a hex color as a CSS hsl() string. */
export function formatHsl(hex: string): string {
  const { h, s, l } = hexToHsl(hex);
  return `hsl(${h}, ${s}%, ${l}%)`;
}
