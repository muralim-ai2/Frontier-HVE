/** Clipboard helper with explicit unavailable state. */

export type CopyResult = "copied" | "unavailable";

/** Copy text to the clipboard, or report that the Clipboard API is unavailable. */
export async function copyText(text: string): Promise<CopyResult> {
  if (typeof navigator === "undefined" || !navigator.clipboard || !window.isSecureContext) return "unavailable";
  await navigator.clipboard.writeText(text);
  return "copied";
}
