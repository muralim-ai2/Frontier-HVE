/** Color conversion and contrast helpers. */

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

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value));

/** Return a normalized six-character uppercase hex value without a hash. */
export function normalizeHex(input: string): string | null {
  const value = input.trim().replace(/^#/, "");
  if (/^[0-9a-f]{3}$/i.test(value)) {
    return value
      .split("")
      .map((character) => character + character)
      .join("")
      .toUpperCase();
  }
  return /^[0-9a-f]{6}$/i.test(value) ? value.toUpperCase() : null;
}

/** Return whether a value is a valid three- or six-character hex color. */
export function isValidHex(input: string): boolean {
  return normalizeHex(input) !== null;
}

/** Convert a hex color to RGB channels. */
export function hexToRgb(hex: string): Rgb {
  const value = normalizeHex(hex);
  if (!value) throw new Error(`Invalid hex color: ${hex}`);
  return {
    r: Number.parseInt(value.slice(0, 2), 16),
    g: Number.parseInt(value.slice(2, 4), 16),
    b: Number.parseInt(value.slice(4, 6), 16),
  };
}

/** Convert RGB channels to a hex color. */
export function rgbToHex(r: number, g: number, b: number): string {
  const channel = (value: number): string =>
    Math.round(clamp(value, 0, 255)).toString(16).padStart(2, "0");
  return `#${channel(r)}${channel(g)}${channel(b)}`.toUpperCase();
}

/** Convert RGB channels to HSL values. */
export function rgbToHsl(r: number, g: number, b: number): Hsl {
  const red = clamp(r, 0, 255) / 255;
  const green = clamp(g, 0, 255) / 255;
  const blue = clamp(b, 0, 255) / 255;
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const delta = max - min;
  let hue = 0;

  if (delta) {
    if (max === red) hue = ((green - blue) / delta) % 6;
    else if (max === green) hue = (blue - red) / delta + 2;
    else hue = (red - green) / delta + 4;
    hue = (hue * 60 + 360) % 360;
  }

  const lightness = (max + min) / 2;
  const saturation = delta ? delta / (1 - Math.abs(2 * lightness - 1)) : 0;
  return { h: hue, s: saturation * 100, l: lightness * 100 };
}

/** Convert HSL values to RGB channels. */
export function hslToRgb(h: number, s: number, l: number): Rgb {
  const hue = ((h % 360) + 360) % 360;
  const saturation = clamp(s, 0, 100) / 100;
  const lightness = clamp(l, 0, 100) / 100;
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
  const section = hue / 60;
  const intermediate = chroma * (1 - Math.abs((section % 2) - 1));
  const values =
    section < 1 ? [chroma, intermediate, 0] :
    section < 2 ? [intermediate, chroma, 0] :
    section < 3 ? [0, chroma, intermediate] :
    section < 4 ? [0, intermediate, chroma] :
    section < 5 ? [intermediate, 0, chroma] : [chroma, 0, intermediate];
  const match = lightness - chroma / 2;
  return { r: (values[0] + match) * 255, g: (values[1] + match) * 255, b: (values[2] + match) * 255 };
}

/** Convert HSL values to a hex color. */
export function hslToHex(h: number, s: number, l: number): string {
  const rgb = hslToRgb(h, s, l);
  return rgbToHex(rgb.r, rgb.g, rgb.b);
}

/** Return WCAG relative luminance for an RGB color. */
export function getRelativeLuminance(rgb: Rgb): number {
  const channels = [rgb.r, rgb.g, rgb.b].map((value) => {
    const channel = value / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

/** Return the contrast ratio between two hex colors. */
export function getContrastRatio(colorA: string, colorB: string): number {
  const luminances = [getRelativeLuminance(hexToRgb(colorA)), getRelativeLuminance(hexToRgb(colorB))];
  return (Math.max(...luminances) + 0.05) / (Math.min(...luminances) + 0.05);
}

/** Return the more readable black or white text color. */
export function getBestTextColor(hex: string): "#000000" | "#FFFFFF" {
  return getContrastRatio(hex, "#000000") >= getContrastRatio(hex, "#FFFFFF") ? "#000000" : "#FFFFFF";
}

/** Format a hex color as an RGB string. */
export function formatRgb(hex: string): string {
  const { r, g, b } = hexToRgb(hex);
  return `rgb(${r}, ${g}, ${b})`;
}

/** Format a hex color as an HSL string. */
export function formatHsl(hex: string): string {
  const { h, s, l } = rgbToHsl(...Object.values(hexToRgb(hex)) as [number, number, number]);
  return `hsl(${Math.round(h)}, ${Math.round(s)}%, ${Math.round(l)}%)`;
}