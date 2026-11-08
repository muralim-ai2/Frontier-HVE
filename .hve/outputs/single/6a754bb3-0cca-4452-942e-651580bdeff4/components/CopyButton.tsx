"use client";

import { useState } from "react";
import { copyText } from "@/lib/clipboard";

interface CopyButtonProps {
  text: string;
  label: string;
  children?: string;
  className?: string;
}

/** Button that copies text and shows Copied! or an unavailable message. */
export default function CopyButton({ text, label, children = "Copy", className = "" }: CopyButtonProps) {
  const [status, setStatus] = useState<string | null>(null);

  async function handleClick(): Promise<void> {
    try {
      const result = await copyText(text);
      setStatus(result === "copied" ? "Copied!" : "Copy not available in this browser");
    } catch (error) {
      setStatus(`Copy failed: ${error instanceof Error ? error.message : String(error)}`);
    }
    window.setTimeout(() => setStatus(null), 1800);
  }

  return (
    <button type="button" onClick={handleClick} aria-label={label} className={`rounded-lg px-2.5 py-1.5 text-sm font-medium transition ${className}`}>
      <span aria-live="polite">{status ?? children}</span>
    </button>
  );
}
