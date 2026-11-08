"use client";

import { useEffect, useState } from "react";
import { Check, Clipboard, Download, Heart, Lock, RefreshCw, Share2, Trash2, Unlock } from "lucide-react";
import { formatHsl, formatRgb, getBestTextColor, getContrastRatio, normalizeHex } from "@/lib/color";
import { paletteToCssVariables, paletteToJson, paletteToSvg, paletteToTailwindConfig } from "@/lib/export";
import { applyLocks, generatePalette, HARMONY_MODES, type HarmonyMode } from "@/lib/palette";
import { deleteSavedPalette, getSavedPalettes, savePalette, type SavedPalette } from "@/lib/storage";

const INITIAL = ["#264653", "#2A9D8F", "#E9C46A", "#F4A261", "#E76F51"];
const FAQ = [
  ["What is a color palette generator?", "A tool that creates coordinated color combinations for visual projects."],
  ["Can I use these palettes for commercial projects?", "Yes. Generated palettes are not exclusive intellectual property."],
  ["Are the generated palettes accessible?", "Contrast guidance is a starting point; always test the final layout."],
  ["What color formats does this tool support?", "HEX, RGB, HSL, CSS variables, Tailwind, JSON, and SVG."],
  ["Can I save my palettes?", "Yes, up to 24 palettes stay in this browser."],
  ["Can I use this with Tailwind CSS?", "Yes. The export panel provides a ready-to-use theme snippet."],
  ["Does this tool store my palettes online?", "No. Saved palettes use localStorage on this device."],
  ["How many colors are in each palette?", "Every generated palette contains five colors."],
];

/** Render the interactive color palette application. */
export default function Home(): React.ReactElement {
  const [colors, setColors] = useState(INITIAL);
  const [locks, setLocks] = useState([false, false, false, false, false]);
  const [mode, setMode] = useState<HarmonyMode>("Analogous");
  const [seed, setSeed] = useState("#4F46E5");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saved, setSaved] = useState<SavedPalette[]>([]);
  const [tab, setTab] = useState("CSS");

  useEffect(() => {
    const query = new URLSearchParams(window.location.search).get("palette");
    const parsed = query?.split(",").map((value) => normalizeHex(value)).filter(Boolean) as string[] | undefined;
    if (parsed?.length === 5) setColors(parsed.map((value) => `#${value}`));
    try { setSaved(getSavedPalettes()); } catch { setNotice("Saving is unavailable in this browser mode."); }
  }, []);

  const generate = (random = false): void => {
    if (locks.every(Boolean)) { setNotice("Unlock a color to generate new options."); return; }
    const normalized = normalizeHex(seed);
    if (!random && !normalized) { setError("Enter a valid HEX color like #4F46E5."); return; }
    setError(""); setNotice("");
    setColors(applyLocks(colors, generatePalette({ mode: random ? "Random" : mode, seed: normalized ? `#${normalized}` : undefined }), locks));
  };
  const copy = async (value: string): Promise<void> => {
    try { await navigator.clipboard.writeText(value); setNotice("Copied!"); } catch { setNotice("Copy not available in this browser."); }
  };
  const save = (): void => {
    try { const item = savePalette(colors); if (!item) { setNotice("Already saved."); return; } setSaved([item, ...saved]); setNotice("Palette saved."); }
    catch { setNotice("Saving is unavailable in this browser mode."); }
  };
  const share = async (): Promise<void> => {
    const url = `${location.origin}${location.pathname}?palette=${colors.map((color) => color.slice(1)).join(",")}`;
    history.replaceState(null, "", url); await copy(url); setNotice("Share URL copied.");
  };
  const exports: Record<string, string> = { CSS: paletteToCssVariables(colors), Tailwind: paletteToTailwindConfig(colors), JSON: paletteToJson(colors), SVG: paletteToSvg(colors) };
  const download = (): void => { const anchor = document.createElement("a"); anchor.href = URL.createObjectURL(new Blob([exports.SVG], { type: "image/svg+xml" })); anchor.download = "palette.svg"; anchor.click(); URL.revokeObjectURL(anchor.href); };
  const schema = { "@context": "https://schema.org", "@graph": [{ "@type": "WebApplication", name: "Color Palette Generator", applicationCategory: "DesignApplication", operatingSystem: "Any", offers: { "@type": "Offer", price: "0" } }, { "@type": "FAQPage", mainEntity: FAQ.map(([name, text]) => ({ "@type": "Question", name, acceptedAnswer: { "@type": "Answer", text } })) }] };

  return <>
    <header><a className="brand" href="/">Chromakit</a><nav><a href="#saved">Saved</a><a href="#guide">Guide</a></nav></header>
    <main>
      <section className="hero">
        <p className="eyebrow">A fast color workspace</p><h1>Color Palette Generator</h1>
        <p className="lede">Create beautiful, accessible color palettes for websites, brands, apps, and creative projects in seconds.</p>
        <div className="controls">
          <label>Harmony<select value={mode} onChange={(event) => setMode(event.target.value as HarmonyMode)}>{HARMONY_MODES.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>Seed color<div className="seed"><input type="color" value={normalizeHex(seed) ? seed : "#4F46E5"} onChange={(event) => setSeed(event.target.value.toUpperCase())}/><input value={seed} onChange={(event) => setSeed(event.target.value)} aria-invalid={!!error}/></div></label>
          <button className="primary" onClick={() => generate()}><RefreshCw/>Generate palette</button><button onClick={() => generate(true)}>Randomize</button>
        </div>
        {error && <p className="error">{error}</p>}
        <div className="palette">{colors.map((color, index) => { const black = getContrastRatio(color, "#000000"); const white = getContrastRatio(color, "#FFFFFF"); const best = getBestTextColor(color); const ratio = Math.max(black, white); return <article className="color" key={`${index}-${color}`} style={{ background: color, color: best }}>
          <button className="icon" title={locks[index] ? "Unlock color" : "Lock color"} onClick={() => setLocks(locks.map((locked, position) => position === index ? !locked : locked))}>{locks[index] ? <Lock/> : <Unlock/>}<span>{locks[index] ? "Locked" : "Lock"}</span></button>
          <div className="values"><button onClick={() => copy(color)}><strong>{color}</strong><Clipboard/></button><button onClick={() => copy(formatRgb(color))}>{formatRgb(color)}</button><button onClick={() => copy(formatHsl(color))}>{formatHsl(color)}</button><small>Use {best === "#000000" ? "black" : "white"} · {ratio.toFixed(1)}:1 · {ratio >= 7 ? "Good for text" : ratio >= 4.5 ? "Use carefully" : "Decorative only"}</small><small>Black {black.toFixed(1)} · White {white.toFixed(1)}</small></div>
        </article>; })}</div>
        <div className="actions"><button className="primary" onClick={save}><Heart/>Save palette</button><button onClick={share}><Share2/>Share palette</button><button onClick={() => setLocks(locks.map(() => false))}>Clear locks</button></div>
        <p className="notice" aria-live="polite">{notice}</p><p className="trust">Runs in your browser. No signup required. Saved palettes stay on this device.</p>
      </section>
      <section className="export"><div><p className="eyebrow">Developer ready</p><h2>Export your palette</h2><p>Coming soon: Pro exports and brand kits.</p></div><div className="exportbox"><div className="tabs">{Object.keys(exports).map((name) => <button className={tab === name ? "active" : ""} key={name} onClick={() => setTab(name)}>{name}</button>)}</div><pre>{exports[tab]}</pre><div className="actions"><button onClick={() => copy(exports[tab])}><Clipboard/>Copy {tab}</button>{tab === "SVG" && <button onClick={download}><Download/>Download</button>}</div></div></section>
      <section id="saved"><div className="sectionhead"><div><p className="eyebrow">Your library</p><h2>Saved palettes</h2></div>{saved.length > 0 && <span>{saved.length}/24</span>}</div>{saved.length === 0 ? <p className="empty">No saved palettes yet. Save your favorite combinations here.</p> : <div className="savedgrid">{saved.map((palette) => <article key={palette.id}><button className="minipalette" onClick={() => setColors(palette.colors)} aria-label="Load saved palette">{palette.colors.map((color) => <span key={color} style={{ background: color }}/>)}</button><button className="delete" title="Delete palette" onClick={() => { try { setSaved(deleteSavedPalette(palette.id)); } catch { setNotice("Saving is unavailable in this browser mode."); } }}><Trash2/>Delete</button></article>)}</div>}</section>
      <section id="guide" className="content"><article><h2>How to use this color palette generator</h2><p>Start with a random palette or seed color, choose a harmony, lock the colors you like, and regenerate the rest. Copy any value, export project-ready code, then save or share the result.</p></article><article><h2>Why color palettes matter</h2><p>Consistent color makes products more recognizable, polished, and easier to use. A considered palette creates hierarchy and gives every interface a coherent visual voice.</p></article><article><h2>Tips for choosing accessible colors</h2><p>Use high contrast for body text, reserve lower contrast for decoration, and test colors in their real context. Contrast guidance is a helpful starting point, not a full accessibility audit.</p></article></section>
      <section className="faq"><p className="eyebrow">Quick answers</p><h2>Frequently asked questions</h2>{FAQ.map(([question, answer]) => <details key={question}><summary>{question}</summary><p>{answer}</p></details>)}</section>
    </main>
    <footer><span>Chromakit · Free color tools</span><span><a href="/privacy">Privacy</a><a href="/terms">Terms</a></span></footer>
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}/>
  </>;
}