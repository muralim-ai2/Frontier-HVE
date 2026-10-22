"""Self-check a clickable prototype: lint its safety rules, screens and links, and save headless-browser screenshots as evidence."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "loop"))
from loop_paths import evidence_dir  # noqa: E402

FORBIDDEN = {
    "external URL": re.compile(r"""(?:src|href|action)\s*=\s*["']?(?:https?:)?//|(?:@import|url\()\s*["']?(?:https?:)?//""", re.I),
    "network call": re.compile(r"\bfetch\s*\(|\bXMLHttpRequest\b|\bnew\s+WebSocket\b|\bnew\s+EventSource\b|navigator\.sendBeacon"),
    "code from strings": re.compile(r"\beval\s*\(|\bnew\s+Function\s*\(|set(?:Timeout|Interval)\s*\(\s*[\"'`]"),
    "form that submits": re.compile(r"<form\b[^>]*\baction\s*=", re.I),
}
BROWSERS = ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser")
WINDOWS_BROWSERS = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def lint(folder: Path, screens: list[str]) -> dict[str, object]:
    """Return the prototype's problems: a missing index.html, unsafe code, screens not found and hash links without a route."""
    if not (folder / "index.html").is_file():
        raise FileNotFoundError(f"{folder / 'index.html'} missing: the prototype starts at index.html")
    files = {p: p.read_text(encoding="utf-8") for p in sorted(folder.rglob("*")) if p.suffix in (".html", ".css", ".js", ".ts")}
    problems = [f"{p.relative_to(folder).as_posix()}: {rule}" for p, text in files.items() for rule, rx in FORBIDDEN.items() if rx.search(text)]
    every = "\n".join(files.values())
    problems += [f"screen {s!r} not found in the prototype" for s in screens if s.lower() not in every.lower()]
    links = sorted(set(re.findall(r"""href\s*=\s*["']#/?([\w-]+)""", every)))
    scripts = "\n".join(t for p, t in files.items() if p.suffix in (".js", ".ts"))
    defined = set(re.findall(r"""\bid\s*=\s*["']([\w-]+)""", every)) | set(re.findall(r"""["'`]#?/?([\w-]+)["'`]""", scripts))
    problems += [f"link #{name} has no screen, route or element id" for name in links if name not in defined]
    return {"ok": not problems, "problems": problems, "screens": screens, "links": links}


def browser() -> str:
    """Return the path of an installed Edge or Chrome for headless screenshots."""
    found = [b for b in (*(shutil.which(n) for n in BROWSERS), *(w for w in WINDOWS_BROWSERS if Path(w).is_file())) if b]
    if not found:
        raise FileNotFoundError("no Edge or Chrome found for headless screenshots; install one, or review the prototype by hand")
    return found[0]


def shots(folder: Path, routes: list[str], workspace: Path, subfolder: str = "prototype") -> list[str]:
    """Save a 1280x800 screenshot of each hash route to the ask's evidence subfolder and return the image paths."""
    out = evidence_dir(workspace) / subfolder
    out.mkdir(parents=True, exist_ok=True)
    page = (folder / "index.html").resolve().as_uri()
    saved = []
    for route in routes:
        image = out / f"{re.sub(r'[^a-z0-9-]+', '-', route.lower()).strip('-') or 'index'}.png"
        image.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory() as profile:
            subprocess.run([browser(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                            "--window-size=1280,800", f"--screenshot={image}", f"{page}#{route}" if route else page],
                           check=True, capture_output=True, timeout=120)
        if not image.is_file():
            raise RuntimeError(f"the browser did not write {image} for route {route!r}")
        saved.append(image.relative_to(workspace).as_posix())
    return saved


def main() -> None:
    """Usage: check.py lint <prototype folder> [screen,screen] | shots <prototype folder> <route,route> [evidence subfolder, default
    prototype] (run from the workspace root)."""
    args = sys.argv[1:]
    if args[:1] == ["lint"] and len(args) in (2, 3):
        result = lint(Path(args[1]), [s.strip() for s in args[2].split(",") if s.strip()] if len(args) == 3 else [])
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["ok"] else 1)
    if args[:1] == ["shots"] and len(args) in (3, 4):
        print(json.dumps(shots(Path(args[1]), [r.strip() for r in args[2].split(",")], Path.cwd(), *args[3:]), indent=2))
        return
    raise SystemExit(main.__doc__)


if __name__ == "__main__":
    main()
