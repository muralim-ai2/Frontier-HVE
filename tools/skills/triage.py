"""Scan every skill under a source directory and shortlist candidates per harness category into skills/triage.json."""

import json
import re
import sys
from pathlib import Path
from typing import Any

from scan import ScanReport, scan

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES_FILE = ROOT / "skills" / "categories.json"
OUT_FILE = ROOT / "skills" / "triage.json"

Json = dict[str, Any]


def load_categories() -> Json:
    """Return skills/categories.json."""
    return json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))


def skill_categories(report: ScanReport, categories: Json) -> list[str]:
    """Return the categories whose skill_pattern matches the skill's name or description."""
    text = f"{report['name'].replace('-', ' ')} {report['description']}"
    return [name for name, cat in categories["categories"].items() if re.search(cat["skill_pattern"], text, re.I)]


def triage(source: Path) -> Json:
    """Return per-category candidates (passing scans first, then smallest SKILL.md) with a shortlist of the top N passing ones."""
    categories = load_categories()
    reports = [scan(p.parent) for p in sorted(source.rglob("SKILL.md"))]
    if not reports:
        raise FileNotFoundError(f"no SKILL.md under {source}")
    by_category: dict[str, list[Json]] = {name: [] for name in categories["categories"]}
    uncategorized = []
    for report in reports:
        entry = {"name": report["name"], "path": report["path"], "ok": report["ok"], "skill_tokens": report["skill_tokens"],
                 "blocking_rules": sorted({f["rule"] for f in report["findings"]})}
        matched = skill_categories(report, categories)
        for name in matched:
            by_category[name].append(entry)
        if not matched:
            uncategorized.append(report["name"])
    limit = categories["max_skills_per_session"]
    result: Json = {"source": source.as_posix(), "skills_scanned": len(reports), "passing": sum(r["ok"] for r in reports),
                    "categories": {}, "uncategorized": uncategorized}
    for name, entries in by_category.items():
        entries.sort(key=lambda e: (not e["ok"], e["skill_tokens"]))
        result["categories"][name] = {"shortlist": [e["name"] for e in entries if e["ok"]][:limit], "candidates": entries}
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: triage.py <skills_source_dir>   (for example a local clone's .github/skills)")
    out = triage(Path(sys.argv[1]))
    OUT_FILE.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"{out['skills_scanned']} skills scanned, {out['passing']} pass; shortlist per category in {OUT_FILE.relative_to(ROOT)}")
    for name, cat in out["categories"].items():
        print(f"  {name}: {len(cat['candidates'])} candidates, shortlist {cat['shortlist']}")
