"""Export a clickable infographic to 1920x1080 PNGs with headless Edge or Chrome.

Usage: python export.py <infographic folder> [theme,theme] [out folder]
Themes: light, dark, hc, system (default light,dark). Writes <out>/<name>-<theme>.png.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)


def browser() -> str:
    """Return the first installed Edge or Chrome."""
    for name in ("msedge", "chrome", "google-chrome", "chromium"):
        if found := shutil.which(name):
            return found
    for path in CANDIDATES:
        if Path(path).is_file():
            return path
    raise SystemExit("No Edge or Chrome found: open index.html and take the screenshot by hand.")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    folder = Path(sys.argv[1]).resolve()
    themes = (sys.argv[2] if len(sys.argv) > 2 else "light,dark").split(",")
    out = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else folder
    out.mkdir(parents=True, exist_ok=True)
    page = (folder / "index.html").as_uri()
    exe = browser()
    for theme in themes:
        image = out / f"{folder.name}-{theme}.png"
        with tempfile.TemporaryDirectory() as profile:
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                            "--window-size=1920,1080", f"--screenshot={image}", f"{page}#/{theme}/export"],
                           check=True, capture_output=True, timeout=120)
        if not image.is_file():
            raise SystemExit(f"The browser did not write {image}")
        print(image)


if __name__ == "__main__":
    main()
