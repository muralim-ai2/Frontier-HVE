/** Palette export formats: CSS variables, Tailwind config, JSON, and SVG. */
import type { Palette } from "./palette";

/** Return the palette as CSS custom properties on :root. */
export function paletteToCssVariables(palette: Palette): string {
  return `:root {\n${palette.map((c, i) => `  --color-${i + 1}: #${c};`).join("\n")}\n}`;
}

/** Return a Tailwind theme.extend.colors snippet for the palette. */
export function paletteToTailwindConfig(palette: Palette): string {
  const entries = palette.map((c, i) => `        ${i + 1}: '#${c}',`).join("\n");
  return `theme: {\n  extend: {\n    colors: {\n      palette: {\n${entries}\n      }\n    }\n  }\n}`;
}

/** Return the palette as pretty-printed JSON. */
export function paletteToJson(palette: Palette): string {
  return JSON.stringify({ colors: palette.map((c) => `#${c}`) }, null, 2);
}

/** Return an SVG swatch strip of the palette. */
export function paletteToSvg(palette: Palette): string {
  const w = 120;
  const rects = palette.map((c, i) => `  <rect x="${i * w}" y="0" width="${w}" height="120" fill="#${c}"/>`).join("\n");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w * palette.length}" height="120" viewBox="0 0 ${w * palette.length} 120">\n${rects}\n</svg>`;
}
