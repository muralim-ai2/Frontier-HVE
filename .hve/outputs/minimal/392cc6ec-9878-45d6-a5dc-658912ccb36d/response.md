I can provide source inline, but this mode cannot inspect or modify your workspace, install dependencies, or run checks. This standalone Next.js app belongs in a new `color-palette-generator` directory, leaving the existing project untouched. It is not build- or browser-verified.

### Configuration

color-palette-generator/package.json
```json
{
  "name": "color-palette-generator",
  "version": "1.0.0",
  "private": true,
  "scripts": { "dev": "next dev", "build": "next build", "start": "next start", "lint": "eslint .", "test": "tsx --test tests/*.test.ts" },
  "dependencies": { "next": "^16.0.0", "react": "^19.2.0", "react-dom": "^19.2.0", "lucide-react": "^0.468.0" },
  "devDependencies": { "@tailwindcss/postcss": "^4.1.0", "tailwindcss": "^4.1.0", "typescript": "^5.9.0", "@types/node": "^22.0.0", "@types/react": "^19.0.0", "@types/react-dom": "^19.0.0", "eslint": "^9.0.0", "eslint-config-next": "^16.0.0", "tsx": "^4.20.0" }
}
```

color-palette-generator/tsconfig.json
```json
{
  "compilerOptions": { "target": "ES2022", "lib": ["dom", "dom.iterable", "esnext"], "strict": true, "noEmit": true, "skipLibCheck": true, "esModuleInterop": true, "module": "esnext", "moduleResolution": "bundler", "resolveJsonModule": true, "isolatedModules": true, "jsx": "react-jsx", "incremental": true, "plugins": [{ "name": "next" }] },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts", ".next/dev/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

color-palette-generator/postcss.config.mjs
```javascript
export default { plugins: { "@tailwindcss/postcss": {} } };
```

color-palette-generator/eslint.config.mjs
```javascript
import { defineConfig, globalIgnores } from "eslint/config";
import next from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";
export default defineConfig([...next, ...typescript, globalIgnores([".next/**", "next-env.d.ts"])]);
```

color-palette-generator/.env.example
```dotenv
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

### Color, Generation, Export, and Storage

color-palette-generator/lib/color.ts
```typescript
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
```

color-palette-generator/lib/palette.ts
```typescript
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
```

color-palette-generator/lib/export.ts
```typescript
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
```

color-palette-generator/lib/storage.ts
```typescript
/** Browser-local favorite palette persistence. */
import { normalizeHex } from "./color";
export interface SavedPalette { id: string; colors: string[]; createdAt: string }
const key = "color-palette-generator:v1";
const validSaved = (value: unknown): value is SavedPalette => { if (!value || typeof value !== "object") return false; const item = value as Partial<SavedPalette>; return typeof item.id === "string" && typeof item.createdAt === "string" && Number.isFinite(Date.parse(item.createdAt)) && Array.isArray(item.colors) && item.colors.length === 5 && item.colors.every((color: unknown): boolean => typeof color === "string" && normalizeHex(color) === color); };
/** Read and validate locally saved palettes. */
export function getSavedPalettes(): SavedPalette[] { const raw = localStorage.getItem(key); if (raw === null) return []; const parsed: unknown = JSON.parse(raw); if (!Array.isArray(parsed) || !parsed.every(validSaved)) throw new Error("Saved palette data is invalid."); return parsed; }
/** Save a unique palette among the 24 most recent favorites. */
export function savePalette(palette: string[]): "Saved." | "Already saved." { if (palette.length !== 5) throw new Error("A palette must contain five colors."); const colors = palette.map((hex: string): string => { const normalized = normalizeHex(hex); if (!normalized) throw new Error("Invalid color."); return normalized; }); const saved = getSavedPalettes(); if (saved.some((item: SavedPalette): boolean => item.colors.join() === colors.join())) return "Already saved."; localStorage.setItem(key, JSON.stringify([{ id: crypto.randomUUID(), colors, createdAt: new Date().toISOString() }, ...saved].slice(0, 24))); return "Saved."; }
/** Delete a saved palette by its identifier. */
export function deleteSavedPalette(id: string): void { localStorage.setItem(key, JSON.stringify(getSavedPalettes().filter((item: SavedPalette): boolean => item.id !== id))); }
/** Remove all saved palettes. */
export function clearSavedPalettes(): void { localStorage.removeItem(key); }
```

### Interactive Tool

color-palette-generator/app/PaletteGenerator.tsx
```tsx
"use client";
import { useEffect, useState, type ReactElement } from "react";
import { Bookmark, Check, Copy, Download, Lock, Share2, Shuffle, Trash2, Unlock } from "lucide-react";
import { getBestTextColor, getContrastRatio, hexToRgb, normalizeHex, rgbToHsl } from "../lib/color";
import { applyLocks, generatePalette, generateRandomPalette, modes, type Mode } from "../lib/palette";
import { paletteToCssVariables, paletteToJson, paletteToSvg, paletteToTailwindConfig } from "../lib/export";
import { clearSavedPalettes, deleteSavedPalette, getSavedPalettes, savePalette, type SavedPalette } from "../lib/storage";
const initial = ["264653", "2A9D8F", "E9C46A", "F4A261", "E76F51"];
const exporters = { CSS: paletteToCssVariables, Tailwind: paletteToTailwindConfig, JSON: paletteToJson, SVG: paletteToSvg };
type Format = keyof typeof exporters;
const guidance = (ratio: number): string => ratio >= 4.5 ? "Good for text" : ratio >= 3 ? "Use carefully" : "Decorative only";
/** Render the palette generator, exports, and local favorites. */
export default function PaletteGenerator(): ReactElement {
  const [palette, setPalette] = useState(initial), [locks, setLocks] = useState<boolean[]>(Array(5).fill(false)), [seed, setSeed] = useState("#2A9D8F"), [mode, setMode] = useState<Mode>("Analogous");
  const [saved, setSaved] = useState<SavedPalette[]>([]), [storageReady, setStorageReady] = useState(false), [storageError, setStorageError] = useState(""), [message, setMessage] = useState(""), [copied, setCopied] = useState(""), [format, setFormat] = useState<Format>("CSS"), [seedError, setSeedError] = useState("");
  useEffect((): void => {
    const query = new URL(window.location.href).searchParams.get("palette");
    if (query !== null) { const colors = query.split(",").map(normalizeHex); if (colors.length === 5 && colors.every((color: string | null): color is string => color !== null)) setPalette(colors); else { setPalette(generateRandomPalette()); setMessage("Invalid shared palette. Generated a new palette."); } }
    try { setSaved(getSavedPalettes()); setStorageReady(true); } catch (error: unknown) { setStorageError(`Saving is unavailable in this browser mode. ${error instanceof Error ? error.message : "Storage access failed."}`); }
  }, []);
  useEffect((): (() => void) | undefined => { if (!copied) return; const timer = window.setTimeout((): void => setCopied(""), 1800); return (): void => window.clearTimeout(timer); }, [copied]);
  const copy = async (text: string): Promise<void> => { setCopied(""); if (!navigator.clipboard?.writeText) { setMessage("Copy not available in this browser."); return; } try { await navigator.clipboard.writeText(text); setCopied(text); setMessage("Copied!"); } catch { setMessage("Copy not available in this browser. Check clipboard permissions."); } };
  const generate = (random: boolean): void => { if (locks.every(Boolean)) { setMessage("Unlock a color to generate new options."); return; } const normalized = seed.trim() ? normalizeHex(seed) : undefined; if (!random && normalized === null) { setSeedError("Enter a valid HEX color like #4F46E5."); return; } setSeedError(""); const next = random ? generateRandomPalette() : generatePalette({ mode, seed: normalized === null ? undefined : normalized }); setPalette(applyLocks(palette, next, locks)); setMessage("Palette generated."); };
  const store = (action: () => string | void): void => { try { const result = action(); setSaved(getSavedPalettes()); setMessage(result || "Saved palettes updated."); } catch (error: unknown) { setStorageReady(false); setStorageError(`Saving is unavailable in this browser mode. ${error instanceof Error ? error.message : "Storage access failed."}`); } };
  const share = (): void => { const url = new URL(window.location.href); url.searchParams.set("palette", palette.join(",")); url.hash = ""; void copy(url.toString()); };
  const download = (): void => { const url = URL.createObjectURL(new Blob([paletteToSvg(palette)], { type: "image/svg+xml" })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = "color-palette.svg"; document.body.append(anchor); anchor.click(); anchor.remove(); window.setTimeout((): void => URL.revokeObjectURL(url), 1000); setMessage("SVG download started."); };
  const output = exporters[format](palette);
  return <section aria-label="Palette workspace">
    <div className="controls"><label>Harmony<select value={mode} onChange={(event): void => setMode(event.target.value as Mode)}>{modes.map((name): ReactElement => <option key={name}>{name}</option>)}</select></label><label>Seed color<div className="seed"><input aria-label="Seed color picker" type="color" value={`#${normalizeHex(seed) || "2A9D8F"}`} onChange={(event): void => { setSeed(event.target.value.toUpperCase()); setSeedError(""); }} /><input aria-label="Seed HEX color" aria-invalid={Boolean(seedError)} aria-describedby={seedError ? "seed-error" : undefined} value={seed} placeholder="Random seed" maxLength={7} spellCheck={false} onChange={(event): void => { setSeed(event.target.value); setSeedError(""); }} /></div></label><button className="primary" onClick={(): void => generate(false)}><Shuffle size={18} />Generate palette</button><button onClick={(): void => generate(true)}><Shuffle size={18} />Randomize</button><button aria-label="Clear locks" title="Clear locks" onClick={(): void => { setLocks(Array(5).fill(false)); setMessage("All colors unlocked."); }}><Unlock size={18} /></button></div>
    {seedError && <p id="seed-error" role="alert" className="error">{seedError}</p>}
    <div className="palette">{palette.map((hex: string, index: number): ReactElement => { const rgb = hexToRgb(hex), hsl = rgbToHsl(...rgb).map(Math.round), best = getBestTextColor(hex); const black = getContrastRatio(hex, "000000"), white = getContrastRatio(hex, "FFFFFF"); const values = [`#${hex}`, `rgb(${rgb.join(", ")})`, `hsl(${hsl[0]}, ${hsl[1]}%, ${hsl[2]}%)`]; return <article key={index} className="color-card"><div className="swatch" style={{ backgroundColor: `#${hex}`, color: best }}><span className="number">0{index + 1}</span><button className="lock" aria-label={`${locks[index] ? "Unlock" : "Lock"} color ${index + 1}`} aria-pressed={locks[index]} title={`${locks[index] ? "Unlock" : "Lock"} color ${index + 1}`} onClick={(): void => setLocks(locks.map((locked: boolean, position: number): boolean => position === index ? !locked : locked))}>{locks[index] ? <Lock size={20} /> : <Unlock size={20} />}</button><span className="sample">Aa</span><span>{best === "black" ? "Black" : "White"} text recommended</span></div><div className="color-details">{values.map((value: string, position: number): ReactElement => <button className={`code ${position === 0 ? "hex" : ""}`} key={value} aria-label={`Copy ${value}`} title={`Copy ${value}`} onClick={(): void => { void copy(value); }}><span>{value}</span>{copied === value ? <Check size={16} /> : <Copy size={16} />}</button>)}<details><summary>Contrast guidance</summary><p>Black: {black.toFixed(2)}:1<br />{guidance(black)}</p><p>White: {white.toFixed(2)}:1<br />{guidance(white)}</p><small>4.5:1 for normal text; 3:1 for large text.</small></details></div></article>; })}</div>
    <div className="actions"><button disabled={!storageReady} onClick={(): void => store((): string => savePalette(palette))}><Bookmark size={18} />Save palette</button><button onClick={share}><Share2 size={18} />Share palette</button><span role="status" aria-live="polite" aria-atomic="true">{message}</span></div><p className="muted">Contrast guidance is a helpful starting point, not a full accessibility audit.</p>{storageError && <p role="alert" className="error">{storageError}</p>}
    <section className="section"><div className="section-heading"><h2>Export your palette</h2><div className="actions"><button aria-label="Copy export" title="Copy export" onClick={(): void => { void copy(output); }}>{copied === output ? <Check size={18} /> : <Copy size={18} />}</button><button aria-label="Download SVG" title="Download SVG" onClick={download}><Download size={18} /></button></div></div><div className="formats" role="group" aria-label="Export format">{(Object.keys(exporters) as Format[]).map((name: Format): ReactElement => <button key={name} aria-pressed={name === format} onClick={(): void => setFormat(name)}>{name}</button>)}</div><pre tabIndex={0} aria-label={`${format} export`}><code>{output}</code></pre>{format === "Tailwind" && <p className="muted">JavaScript config for Tailwind v3, or v4 with an explicit @config directive. CSS variables work independently.</p>}<small>Coming soon: Pro exports and brand kits</small></section>
    <section className="section"><div className="section-heading"><h2>Saved palettes</h2>{saved.length > 0 && <button title="Clear saved palettes" aria-label="Clear saved palettes" disabled={!storageReady} onClick={(): void => { if (window.confirm("Delete all saved palettes?")) store(clearSavedPalettes); }}><Trash2 size={18} /></button>}</div>{saved.length === 0 ? <p className="muted">No saved palettes yet. Save your favorite combinations here.</p> : <div className="saved-grid">{saved.map((item: SavedPalette): ReactElement => <div className="saved" key={item.id}><button className="saved-preview" aria-label={`Load palette ${item.colors.map((color: string): string => `#${color}`).join(", ")}`} title="Load palette" onClick={(): void => { setPalette(item.colors); setLocks(Array(5).fill(false)); setMessage("Saved palette loaded. Locks cleared."); }}>{item.colors.map((color: string, index: number): ReactElement => <span key={index} style={{ background: `#${color}` }} />)}</button><button disabled={!storageReady} aria-label={`Delete palette ${item.colors.join(", ")}`} title="Delete palette" onClick={(): void => store((): void => deleteSavedPalette(item.id))}><Trash2 size={18} /></button></div>)}</div>}</section>
  </section>;
}
```

### Pages and SEO

color-palette-generator/lib/seo.ts
```typescript
/** Shared site metadata and public frequently asked questions. */
const configuredUrl = process.env.NEXT_PUBLIC_SITE_URL;
if (!configuredUrl) throw new Error("Set NEXT_PUBLIC_SITE_URL to the public site origin.");
const parsedUrl = new URL(configuredUrl);
if (!["http:", "https:"].includes(parsedUrl.protocol) || parsedUrl.username || parsedUrl.password || parsedUrl.pathname !== "/" || parsedUrl.search || parsedUrl.hash) throw new Error("NEXT_PUBLIC_SITE_URL must be an HTTP(S) origin without a path, credentials, query, or fragment.");
export const siteUrl = parsedUrl.origin;
export const title = "Color Palette Generator | Create Beautiful Color Schemes";
export const description = "Generate beautiful color palettes for websites, brands, apps, and creative projects. Copy HEX, RGB, HSL, CSS variables, Tailwind config, and more.";
export const faq: [string, string][] = [
  ["What is a color palette generator?", "A tool for creating coordinated color combinations for creative projects."],
  ["Can I use these palettes for commercial projects?", "Yes. Colors are not exclusive, and palettes are not legal brand advice. Check your project's requirements."],
  ["Are the generated palettes accessible?", "Not automatically. Contrast depends on the foreground, background, text size, and surrounding design. Verify your final layouts."],
  ["What color formats does this tool support?", "HEX, RGB, HSL, CSS variables, a Tailwind configuration fragment, JSON, and SVG."],
  ["Can I save my palettes?", "Yes, up to 24 distinct palettes in this browser. Clearing browser data can remove them."],
  ["Can I use this with Tailwind CSS?", "Yes. Export the JavaScript theme configuration, or use the CSS variables in your styles."],
  ["Does this tool store my palettes online?", "No. Favorites stay in localStorage. Shared links contain the palette's color values."],
  ["How many colors are in each palette?", "Each palette contains five colors."]
];
```

color-palette-generator/app/layout.tsx
```tsx
import type { Metadata } from "next";
import type { ReactNode, ReactElement } from "react";
import Link from "next/link";
import { description, siteUrl, title } from "../lib/seo";
import "./globals.css";
export const metadata: Metadata = { metadataBase: new URL(siteUrl), title, description, alternates: { canonical: "/" }, openGraph: { title, description, url: "/", type: "website", images: [{ url: "/og-image.svg", width: 1200, height: 630, alt: "Color Palette Generator: five color swatches" }] }, twitter: { card: "summary_large_image", title, description, images: ["/og-image.svg"] }, icons: { icon: "/og-image.svg" } };
/** Render the shared accessible page shell. */
export default function RootLayout({ children }: { children: ReactNode }): ReactElement { return <html lang="en"><body><a className="skip" href="#main">Skip to content</a><header><Link className="brand" href="/"><span className="brand-mark" aria-hidden="true" />Color Palette Generator</Link><span className="eyebrow">A little color. A lot of possibility.</span></header><main id="main">{children}</main><footer><p>Runs in your browser. No signup required. Saved palettes stay on this device.</p><nav aria-label="Legal"><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></nav></footer></body></html>; }
```

color-palette-generator/app/page.tsx
```tsx
import type { ReactElement } from "react";
import PaletteGenerator from "./PaletteGenerator";
import { faq, siteUrl } from "../lib/seo";
/** Render the palette workspace and supporting design information. */
export default function Home(): ReactElement {
  const structured = [{ "@context": "https://schema.org", "@type": "WebApplication", name: "Color Palette Generator", url: siteUrl, applicationCategory: "DesignApplication", operatingSystem: "Any", offers: { "@type": "Offer", price: "0", priceCurrency: "USD" } }, { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: faq.map(([question, answer]: [string, string]): object => ({ "@type": "Question", name: question, acceptedAnswer: { "@type": "Answer", text: answer } })) }];
  return <><div className="intro"><p className="eyebrow">Your next project starts here</p><h1>Color Palette Generator</h1><p>Create beautiful, accessible color palettes for websites, brands, apps, and creative projects in seconds.</p></div><noscript><p>JavaScript is required for generation, copying, and saving. The example palette and design information remain available below.</p></noscript><PaletteGenerator /><div className="editorial section"><section><h2>Why color palettes matter</h2><p>Consistent colors make products recognizable, polished, and easier to navigate. A balanced palette gives primary actions, supporting information, and backgrounds distinct roles.</p></section><section><h2>Tips for choosing accessible colors</h2><p>Test text against its actual background. Aim for at least 4.5:1 contrast for body text and 3:1 for large text. Reserve low-contrast combinations for decoration, and never use color as the only signal.</p><p>Generated colors are not guaranteed to be unique. Palettes are not legal brand advice. Simplified contrast labels must be verified in real layouts.</p></section></div><section className="section faq"><h2>Frequently asked questions</h2>{faq.map(([question, answer]: [string, string]): ReactElement => <details key={question}><summary>{question}</summary><p>{answer}</p></details>)}</section><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structured).replaceAll("<", "\\u003c") }} /></>;
}
```

color-palette-generator/app/[legal]/page.tsx
```tsx
import type { Metadata } from "next";
import type { ReactElement } from "react";
import { notFound } from "next/navigation";
const pages: Record<string, { title: string; paragraphs: string[] }> = {
  privacy: { title: "Privacy", paragraphs: ["No account is required, and the app does not require users to submit personal information. Palette generation happens in your browser.", "Saved palettes use localStorage on this device, not an online palette database. Clearing browser data may remove saved palettes.", "Shared palette URLs include color values in the URL. Those values may appear in browser history and hosting access logs. Do not put sensitive information into palette names if naming is added in the future.", "This app includes no analytics or advertising scripts. Any future analytics must be disclosed before launch. Your hosting provider may process routine request information under its own policies."] },
  terms: { title: "Terms", paragraphs: ["This free tool is provided for general creative and design use, without guarantees of availability or suitability for a particular purpose.", "Generated palettes may be used in commercial projects, but are not guaranteed to be suitable for every brand, accessibility requirement, or legal use case.", "Users are responsible for testing colors in their own context. Accessibility guidance is a helpful starting point, not a full audit.", "Generated colors are not guaranteed to be unique. Generated palettes are not exclusive intellectual property, and this tool does not provide legal brand advice."] }
};
export const dynamicParams = false;
/** Enumerate the static legal pages. */
export function generateStaticParams(): { legal: string }[] { return Object.keys(pages).map((legal: string): { legal: string } => ({ legal })); }
/** Return page-specific legal metadata. */
export async function generateMetadata({ params }: { params: Promise<{ legal: string }> }): Promise<Metadata> { const { legal } = await params; const page = pages[legal]; if (!page) notFound(); return { title: `${page.title} | Color Palette Generator`, alternates: { canonical: `/${legal}` }, openGraph: { title: `${page.title} | Color Palette Generator`, url: `/${legal}` } }; }
/** Render the requested legal policy. */
export default async function LegalPage({ params }: { params: Promise<{ legal: string }> }): Promise<ReactElement> { const { legal } = await params; const page = pages[legal]; if (!page) notFound(); return <article className="legal"><h1>{page.title}</h1>{page.paragraphs.map((paragraph: string): ReactElement => <p key={paragraph}>{paragraph}</p>)}</article>; }
```

color-palette-generator/app/robots.ts
```typescript
import type { MetadataRoute } from "next";
import { siteUrl } from "../lib/seo";
/** Return crawler directives. */
export default function robots(): MetadataRoute.Robots { return { rules: { userAgent: "*", allow: "/" }, sitemap: `${siteUrl}/sitemap.xml` }; }
```

color-palette-generator/app/sitemap.ts
```typescript
import type { MetadataRoute } from "next";
import { siteUrl } from "../lib/seo";
/** List the public canonical pages. */
export default function sitemap(): MetadataRoute.Sitemap { return ["", "/privacy", "/terms"].map((path: string): MetadataRoute.Sitemap[number] => ({ url: `${siteUrl}${path}` })); }
```

### Styling and Asset

color-palette-generator/app/globals.css
```css
@import "tailwindcss";
:root{--ink:#172321;--muted:#53635e;--line:#dce3de;--accent:#165c49;--paper:#f7f9f6}*{box-sizing:border-box;letter-spacing:0}body{margin:0;color:var(--ink);background:radial-gradient(#c9d5cc 0.6px,transparent 0.6px) 0 0/18px 18px,var(--paper);font-family:"Avenir Next","Trebuchet MS",sans-serif;font-size:16px;line-height:1.6}header,main,footer{width:min(1280px,100% - 48px);margin:auto}header{min-height:88px;display:flex;align-items:center;justify-content:space-between;gap:24px;border-bottom:1px solid var(--line)}a{color:inherit;text-underline-offset:4px}.brand{display:flex;align-items:center;gap:12px;text-decoration:none;font-weight:800}.brand-mark{width:28px;height:28px;border-radius:6px;background:conic-gradient(#264653 0 20%,#2a9d8f 20% 40%,#e9c46a 40% 60%,#f4a261 60% 80%,#e76f51 80%);flex:none}.eyebrow{font-size:12px;text-transform:uppercase;font-weight:700}.intro{padding:38px 0 26px;max-width:800px}.intro p{margin:8px 0;color:var(--muted)}h1{font-family:"Palatino Linotype",Palatino,serif;font-weight:600;font-size:46px;line-height:1.12;margin:12px 0 16px;overflow-wrap:anywhere}h2{font-size:23px;font-weight:750;line-height:1.3;margin:0 0 16px}button,input,select{font:inherit}button,select,input:not([type=color]){min-height:44px;border:1px solid #b9c8bf;border-radius:6px;background:white;color:var(--ink)}button{display:inline-flex;align-items:center;justify-content:center;gap:9px;padding:9px 14px;cursor:pointer;font-weight:650}button:hover{background:#eaf1ed}button:disabled{opacity:.55;cursor:not-allowed}button svg{flex:none}button[aria-pressed=true]{background:#e0eee5;border-color:var(--accent)}button.primary{color:white;background:var(--accent);border-color:var(--accent)}button.primary:hover{background:#104433}:focus-visible{outline:3px solid #145bcc;outline-offset:4px}.skip{position:absolute;top:-80px;left:20px;z-index:10;background:white;padding:12px}.skip:focus{top:12px}
.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin-bottom:24px}.controls label{font-size:12px;text-transform:uppercase;font-weight:750;display:grid;gap:6px}.controls select{min-width:180px;padding:8px 12px;text-transform:none}.seed{display:flex;align-items:center;gap:8px}.seed input[type=color]{width:44px;height:44px;border:0;padding:0;background:transparent;cursor:pointer}.seed input:not([type=color]){width:132px;padding:8px 10px;font-family:monospace}.palette{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}.color-card{min-width:0;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:white;box-shadow:0 4px 10px #142a1910}.swatch{height:258px;position:relative;padding:16px;display:flex;flex-direction:column;justify-content:end;gap:8px;font-size:12px}.number{position:absolute;top:18px;left:16px;font-family:monospace}.sample{font-family:"Palatino Linotype",Palatino,serif;font-size:66px;line-height:1}.lock{position:absolute;top:9px;right:8px;background:transparent!important;color:inherit;border-color:transparent!important;padding:10px}.lock[aria-pressed=true]{border-color:currentColor!important}.color-details{padding:12px}.code{width:100%;border:0;justify-content:space-between;padding:6px 2px;font-family:monospace;font-size:11px;white-space:normal;text-align:left;min-width:0}.code span{overflow-wrap:anywhere}.code.hex{font-size:19px;font-weight:750}.color-details details{font-size:12px;border-top:1px solid var(--line);margin-top:8px;padding-top:12px}.color-details p{margin:8px 0}.actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:18px}.actions [role=status]{font-size:14px;color:var(--accent)}.muted,small{color:var(--muted);font-size:13px}.error{color:#a01826;font-size:14px}.section{padding:34px 0;border-top:1px solid var(--line);margin-top:28px}.section-heading{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:16px}.section-heading h2{margin:0}.section-heading .actions{margin:0}.formats{display:flex;gap:6px;flex-wrap:wrap}pre{background:#edf2ed;border:1px solid var(--line);border-radius:6px;padding:20px;font-size:13px;overflow:auto;max-height:310px;min-height:200px;margin:14px 0}.saved-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.saved{display:flex;gap:8px;min-width:0}.saved-preview{flex:1;display:flex;gap:0;padding:0;overflow:hidden;height:64px;min-width:0}.saved-preview span{height:100%;flex:1}.editorial{display:grid;grid-template-columns:1fr 1fr;gap:64px}.editorial p,.legal p{color:var(--muted)}summary{cursor:pointer;min-height:32px}.faq details{padding:16px 0;border-bottom:1px solid var(--line)}.faq summary{font-weight:700}.faq p{max-width:800px;color:var(--muted)}footer{display:flex;justify-content:space-between;gap:24px;border-top:1px solid var(--line);padding:28px 0 40px;font-size:12px}footer nav{display:flex;gap:20px}.legal{max-width:760px;min-height:65vh;padding:48px 0}
@media(min-width:701px) and (max-width:1050px){.palette{grid-template-columns:repeat(3,minmax(0,1fr))}.saved-grid{grid-template-columns:repeat(2,minmax(0,1fr))}header>.eyebrow{display:none}}@media(max-width:700px){header,main,footer{width:calc(100% - 32px)}header{min-height:72px}header>.eyebrow{display:none}h1{font-size:36px}.intro{padding-top:24px}.palette,.editorial,.saved-grid{grid-template-columns:1fr}.swatch{height:220px}.code{font-size:14px}.controls{gap:10px}.controls label{flex:1;min-width:0}.controls select{width:100%;min-width:0}.seed input:not([type=color]){width:100%;min-width:0}.controls .primary{flex:1 1 100%}.editorial{gap:24px}footer{flex-direction:column;gap:8px}.brand{font-size:14px}.section-heading h2{font-size:21px}}
@media(prefers-reduced-motion:no-preference){.intro,.palette{animation:appear .35s ease-out both}@keyframes appear{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}} 
```

color-palette-generator/public/og-image.svg
```svg
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="#f7f9f6"/><text x="60" y="105" font-family="Georgia,serif" font-size="60" fill="#172321">Color Palette Generator</text><text x="64" y="157" font-family="sans-serif" font-size="26" fill="#53635e">Five colors. Your next creative direction.</text><path fill="#264653" d="M60 210h216v330H60z"/><path fill="#2a9d8f" d="M276 210h216v330H276z"/><path fill="#e9c46a" d="M492 210h216v330H492z"/><path fill="#f4a261" d="M708 210h216v330H708z"/><path fill="#e76f51" d="M924 210h216v330H924z"/><text x="60" y="592" font-family="sans-serif" font-size="22" fill="#172321">Generate · Lock · Export · Save</text></svg>
```

### Focused Tests

color-palette-generator/tests/palette.test.ts
```typescript
import { test } from "node:test";
import assert from "node:assert/strict";
import { getBestTextColor, getContrastRatio, hexToRgb, hslToHex, normalizeHex, rgbToHsl } from "../lib/color";
import { applyLocks, generatePalette, modes } from "../lib/palette";
import { paletteToCssVariables, paletteToJson, paletteToSvg } from "../lib/export";
test("HEX normalization and known color conversions", (): void => { assert.equal(normalizeHex(" #abc "), "AABBCC"); assert.equal(normalizeHex("#xyz"), null); assert.deepEqual(hexToRgb("FFFFFF"), [255, 255, 255]); assert.deepEqual(rgbToHsl(255, 0, 0), [0, 100, 50]); assert.equal(hslToHex(-120, 100, 50), "0000FF"); assert.equal(hslToHex(720, 200, 100), "FFFFFF"); });
test("WCAG black and white contrast", (): void => { assert.equal(getContrastRatio("000000", "FFFFFF"), 21); assert.equal(getBestTextColor("FFFFFF"), "black"); assert.equal(getBestTextColor("000000"), "white"); });
test("every mode returns five valid, varied colors", (): void => { for (const mode of modes) for (const seed of ["000000", "FFFFFF", "2A9D8F"]) { const palette = generatePalette({ mode, seed }); assert.equal(palette.length, 5); assert.ok(palette.every((color: string): boolean => /^[0-9A-F]{6}$/.test(color))); assert.ok(new Set(palette).size >= 4); } });
test("locks preserve exact selected colors", (): void => { const original = ["111111", "222222", "333333", "444444", "555555"], next = Array<string>(5).fill("FFFFFF"); assert.deepEqual(applyLocks(original, next, [true, false, true, false, true]), ["111111", "FFFFFF", "333333", "FFFFFF", "555555"]); assert.deepEqual(applyLocks(original, next, Array<boolean>(5).fill(true)), original); });
test("exports contain valid normalized values", (): void => { const palette = ["264653", "2A9D8F", "E9C46A", "F4A261", "E76F51"]; assert.equal(JSON.parse(paletteToJson(palette)).length, 5); assert.match(paletteToCssVariables(palette), /--color-5: #E76F51;/); assert.equal((paletteToSvg(palette).match(/<text /g) || []).length, 5); });
```

**Run Locally**
Use Node.js 20.9 or newer. In the app directory:

1. Check repository `.npmrc` settings and run `npm config get registry`. Preserve an existing Azure Artifacts feed; otherwise use `npm config set registry https://packagefeedproxy.microsoft.io/npm/`. Verify the registry again.
2. Set `NEXT_PUBLIC_SITE_URL` in your environment using the example value for development and your real origin for deployment.
3. Run `npm install`, then `npm run test`, `npm run lint`, and `npm run build`.
4. Run `npm run dev -- --port 3001`, then open `http://localhost:3001`.

**Limitations**
No files were created and no checks were executed. Browser interaction, storage failure, responsive layout, and clipboard tests remain necessary. Some social platforms reject SVG preview images; replace the OG asset with PNG before launch. A dedicated how-to section is not included.

Next priorities are Playwright coverage, a dependency lockfile, and deployment-specific privacy review.
