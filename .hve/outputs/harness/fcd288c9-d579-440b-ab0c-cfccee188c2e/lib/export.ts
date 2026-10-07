/** Palette export formatters. */

/** Format a palette as CSS custom properties. */
export function paletteToCssVariables(palette: string[]): string {
  return `:root {\n${palette.map((color, index) => `  --color-${index + 1}: ${color};`).join("\n")}\n}`;
}

/** Format a palette as a Tailwind theme extension. */
export function paletteToTailwindConfig(palette: string[]): string {
  const colors = palette.map((color, index) => `        ${index + 1}: '${color}',`).join("\n");
  return `theme: {\n  extend: {\n    colors: {\n      palette: {\n${colors}\n      }\n    }\n  }\n}`;
}

/** Format a palette as JSON. */
export function paletteToJson(palette: string[]): string {
  return JSON.stringify({ colors: palette }, null, 2);
}

/** Format a palette as an accessible SVG swatch strip. */
export function paletteToSvg(palette: string[]): string {
  const width = 1000 / palette.length;
  const swatches = palette.map((color, index) => `<rect x="${index * width}" width="${width}" height="240" fill="${color}"/>`).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="240" viewBox="0 0 1000 240" role="img" aria-label="Color palette">${swatches}</svg>`;
}