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
