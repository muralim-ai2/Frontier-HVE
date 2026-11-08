/** Portable palette export formats. */
import { normalizeHex } from "./color";
const validate = (palette: string[]): string[] => { if (palette.length !== 5) throw new Error("A palette must contain five colors."); return palette.map((hex: string): string => { const color = normalizeHex(hex); if (!color) throw new Error("Invalid palette color."); return `#${color}`; }); };
/** Export CSS custom properties. */
export function paletteToCssVariables(palette: string[]): string { return `:root {\n${validate(palette).map((hex: string, index: number): string => `  --color-${index + 1}: ${hex};`).join("\n")}\n}`; }
/** Export a Tailwind JavaScript configuration fragment. */
export function paletteToTailwindConfig(palette: string[]): string { return `theme: {\n  extend: {\n    colors: {\n      palette: ${JSON.stringify(Object.fromEntries(validate(palette).map((hex: string, index: number): [number, string] => [index + 1, hex])), null, 2).replaceAll("\n", "\n      ")}\n    }\n  }\n}`; }
/** Export a JSON color array. */
export function paletteToJson(palette: string[]): string { return JSON.stringify(validate(palette), null, 2); }
/** Export a labeled SVG swatch strip. */
export function paletteToSvg(palette: string[]): string { return `<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="280" viewBox="0 0 1000 280" role="img"><title>Five-color palette</title>${validate(palette).map((hex: string, index: number): string => `<rect x="${index * 200}" width="200" height="230" fill="${hex}"/><rect x="${index * 200}" y="230" width="200" height="50" fill="white"/><text x="${index * 200 + 100}" y="262" text-anchor="middle" font-family="monospace" font-size="20" fill="black">${hex}</text>`).join("")}</svg>`; }
