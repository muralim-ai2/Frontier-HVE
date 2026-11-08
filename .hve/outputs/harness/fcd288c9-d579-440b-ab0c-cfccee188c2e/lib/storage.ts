/** Local palette persistence. */

export interface SavedPalette {
  id: string;
  colors: string[];
  createdAt: string;
}

const STORAGE_KEY = "color-palette-generator-favorites";

/** Return saved palettes from local storage. */
export function getSavedPalettes(): SavedPalette[] {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (!stored) return [];
  const parsed: unknown = JSON.parse(stored);
  if (!Array.isArray(parsed)) throw new Error("Saved palette data is malformed.");
  return parsed as SavedPalette[];
}

/** Save a unique palette and return its persisted record. */
export function savePalette(colors: string[]): SavedPalette | null {
  const saved = getSavedPalettes();
  if (saved.some((palette) => palette.colors.join() === colors.join())) return null;
  const palette: SavedPalette = { id: crypto.randomUUID(), colors: [...colors], createdAt: new Date().toISOString() };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify([palette, ...saved].slice(0, 24)));
  return palette;
}

/** Delete a saved palette by identifier. */
export function deleteSavedPalette(id: string): SavedPalette[] {
  const remaining = getSavedPalettes().filter((palette) => palette.id !== id);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(remaining));
  return remaining;
}

/** Remove all saved palettes. */
export function clearSavedPalettes(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}