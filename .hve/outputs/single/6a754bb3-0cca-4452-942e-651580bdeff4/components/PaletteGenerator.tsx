"use client";

import { useEffect, useState } from "react";
import ColorCard from "./ColorCard";
import CopyButton from "./CopyButton";
import ExportPanel from "./ExportPanel";
import SavedPalettes from "./SavedPalettes";
import { normalizeHex } from "@/lib/color";
import {
  HARMONY_MODES,
  PALETTE_SIZE,
  applyLocks,
  generatePalette,
  generateRandomPalette,
  modeLabel,
  parsePaletteParam,
  type HarmonyMode,
  type Palette,
} from "@/lib/palette";
import { deleteSavedPalette, getSavedPalettes, isStorageAvailable, savePalette, type SavedPalette } from "@/lib/storage";

const DEFAULT_PALETTE: Palette = ["264653", "2A9D8F", "E9C46A", "F4A261", "E76F51"];
const NO_LOCKS: boolean[] = Array<boolean>(PALETTE_SIZE).fill(false);
const STORAGE_UNAVAILABLE = "Saving is unavailable in this browser mode. The generator still works.";

const errorText = (error: unknown): string => (error instanceof Error ? error.message : String(error));

/** Interactive palette generator with controls, cards, export, and saved palettes. */
export default function PaletteGenerator() {
  const [palette, setPalette] = useState<Palette>(DEFAULT_PALETTE);
  const [locks, setLocks] = useState<boolean[]>(NO_LOCKS);
  const [mode, setMode] = useState<HarmonyMode>("random");
  const [seedInput, setSeedInput] = useState<string>("");
  const [message, setMessage] = useState<string>("");
  const [saved, setSaved] = useState<SavedPalette[]>([]);
  const [storageMessage, setStorageMessage] = useState<string | null>(null);
  const [ready, setReady] = useState<boolean>(false);

  useEffect(() => {
    const param = new URLSearchParams(window.location.search).get("palette");
    if (param === null) {
      setPalette(generateRandomPalette());
    } else {
      const fromUrl = parsePaletteParam(param);
      if (fromUrl.length === PALETTE_SIZE) setPalette(fromUrl);
      else if (fromUrl.length === 0) {
        setPalette(generateRandomPalette());
        setMessage("The shared link had no valid colors, so a new palette was generated.");
      } else {
        setPalette([...fromUrl, ...generateRandomPalette().slice(fromUrl.length)]);
        setMessage("Some colors in the shared link were invalid and were replaced.");
      }
    }
    if (!isStorageAvailable()) setStorageMessage(STORAGE_UNAVAILABLE);
    else {
      try {
        setSaved(getSavedPalettes());
      } catch (error) {
        setStorageMessage(`Could not read saved palettes: ${errorText(error)}`);
      }
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (ready) window.history.replaceState(null, "", `?palette=${palette.join(",")}`);
  }, [palette, ready]);

  const seed = seedInput.trim() === "" ? undefined : normalizeHex(seedInput);
  const seedInvalid = seed === null;
  const allLocked = locks.every(Boolean);

  function regenerate(next: Palette): void {
    if (allLocked) {
      setMessage("Unlock a color to generate new options.");
      return;
    }
    setPalette(applyLocks(palette, next, locks));
    setMessage("");
  }

  function handleGenerate(): void {
    if (seedInvalid) {
      setMessage("Enter a valid HEX color like #4F46E5.");
      return;
    }
    regenerate(generatePalette({ mode, seed }));
  }

  function toggleLock(index: number): void {
    setLocks((prev) => prev.map((l, i) => (i === index ? !l : l)));
  }

  function loadPalette(colors: Palette): void {
    setPalette(colors);
    setLocks(NO_LOCKS);
    setMessage("Saved palette loaded.");
  }

  function handleSave(): void {
    if (storageMessage === STORAGE_UNAVAILABLE) {
      setMessage(STORAGE_UNAVAILABLE);
      return;
    }
    try {
      const result = savePalette(palette);
      setSaved(result.palettes);
      setMessage(result.status === "saved" ? "Palette saved." : "Already saved.");
    } catch (error) {
      setMessage(`Could not save palette: ${errorText(error)}`);
    }
  }

  function handleDelete(id: string): void {
    try {
      setSaved(deleteSavedPalette(id));
      setMessage("Palette deleted.");
    } catch (error) {
      setMessage(`Could not delete palette: ${errorText(error)}`);
    }
  }

  const shareUrl = ready ? `${window.location.origin}${window.location.pathname}?palette=${palette.join(",")}` : "";
  const secondary = "rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-800 hover:bg-slate-50";

  return (
    <div className="space-y-8">
      <section aria-label="Palette controls" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="mode" className="text-sm font-medium text-slate-700">Harmony mode</label>
            <select
              id="mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as HarmonyMode)}
              className="h-11 rounded-xl border border-slate-300 bg-white px-3 text-sm"
            >
              {HARMONY_MODES.map((m) => (
                <option key={m} value={m}>{modeLabel(m)}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="seed" className="text-sm font-medium text-slate-700">Seed color (optional)</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                aria-label="Seed color picker"
                value={`#${seed ?? "4F46E5"}`}
                onChange={(e) => setSeedInput(e.target.value.toUpperCase())}
                className="h-11 w-12 cursor-pointer rounded-xl border border-slate-300 bg-white p-1"
              />
              <input
                id="seed"
                type="text"
                inputMode="text"
                autoComplete="off"
                spellCheck={false}
                placeholder="#4F46E5"
                value={seedInput}
                onChange={(e) => setSeedInput(e.target.value)}
                aria-invalid={seedInvalid}
                aria-describedby={seedInvalid ? "seed-error" : undefined}
                className={`h-11 w-32 rounded-xl border px-3 font-mono text-sm ${seedInvalid ? "border-red-500" : "border-slate-300"}`}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleGenerate}
              className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:from-indigo-700 hover:to-violet-700"
            >
              Generate palette
            </button>
            <button type="button" onClick={() => regenerate(generateRandomPalette())} className={secondary}>Randomize</button>
            <button type="button" onClick={() => setLocks(NO_LOCKS)} disabled={!locks.some(Boolean)} className={`${secondary} disabled:opacity-50`}>
              Clear locks
            </button>
            <button type="button" onClick={handleSave} className={secondary}>Save palette</button>
            <CopyButton text={shareUrl} label="Copy shareable palette link" className={secondary}>Share palette</CopyButton>
          </div>
        </div>
        {seedInvalid && <p id="seed-error" className="mt-2 text-sm text-red-700">Enter a valid HEX color like #4F46E5.</p>}
        <p role="status" aria-live="polite" className="mt-2 min-h-5 text-sm font-medium text-indigo-800">{message}</p>
      </section>

      <ul aria-label="Current palette" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {palette.map((hex, i) => (
          <ColorCard key={i} hex={hex} index={i} locked={locks[i]} onToggleLock={toggleLock} />
        ))}
      </ul>
      <p className="text-sm text-slate-600">Contrast guidance is a helpful starting point, not a full accessibility audit.</p>

      <ExportPanel palette={palette} />
      <SavedPalettes palettes={saved} storageMessage={storageMessage} onLoad={loadPalette} onDelete={handleDelete} />
    </div>
  );
}
