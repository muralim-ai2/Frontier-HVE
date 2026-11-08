/** localStorage persistence for saved palettes. Call only on the client. */
import { normalizeHex } from "./color";
import { PALETTE_SIZE, type Palette } from "./palette";

export interface SavedPalette {
  id: string;
  colors: string[];
  createdAt: string;
}

export type SaveResult = { status: "saved" | "duplicate"; palettes: SavedPalette[] };

const KEY = "cpg:saved-palettes";
export const MAX_SAVED = 24;

/** Return whether localStorage can be written in this browser context. */
export function isStorageAvailable(): boolean {
  try {
    const probe = `${KEY}:probe`;
    window.localStorage.setItem(probe, "1");
    window.localStorage.removeItem(probe);
    return true;
  } catch {
    return false;
  }
}

function isSavedPalette(value: unknown): value is SavedPalette {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "string" &&
    typeof v.createdAt === "string" &&
    Array.isArray(v.colors) &&
    v.colors.length === PALETTE_SIZE &&
    v.colors.every((c) => typeof c === "string" && normalizeHex(c) === c)
  );
}

function write(palettes: SavedPalette[]): SavedPalette[] {
  window.localStorage.setItem(KEY, JSON.stringify(palettes));
  return palettes;
}

/** Return saved palettes, newest first, skipping malformed entries. */
export function getSavedPalettes(): SavedPalette[] {
  const raw = window.localStorage.getItem(KEY);
  if (raw === null) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed)) throw new Error(`Saved palettes in localStorage key "${KEY}" are not an array`);
  return parsed.filter(isSavedPalette);
}

/** Save a palette unless an identical one exists, keeping the 24 most recent. */
export function savePalette(palette: Palette): SaveResult {
  const existing = getSavedPalettes();
  const key = palette.join(",");
  if (existing.some((p) => p.colors.join(",") === key)) return { status: "duplicate", palettes: existing };
  const entry: SavedPalette = { id: `${Date.now().toString(36)}-${palette.join("")}`, colors: [...palette], createdAt: new Date().toISOString() };
  return { status: "saved", palettes: write([entry, ...existing].slice(0, MAX_SAVED)) };
}

/** Delete a saved palette by id and return the remaining list. */
export function deleteSavedPalette(id: string): SavedPalette[] {
  return write(getSavedPalettes().filter((p) => p.id !== id));
}

/** Remove all saved palettes. */
export function clearSavedPalettes(): void {
  window.localStorage.removeItem(KEY);
}
