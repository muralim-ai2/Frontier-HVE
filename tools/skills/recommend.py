"""Rank library skills for a task and split them into an auto-load set within the loadout budget and a ranked list to recommend."""

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Literal

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
USER_REGISTRY = Path.cwd() / ".hve" / "skills-registry.json"
STATUS_ORDER = {"admitted": 0, "provisional": 1}
STOP_WORDS = {"the", "and", "for", "then", "with", "from", "that", "this", "our", "your", "into", "each", "before", "after", "are",
              "was", "not", "can", "how", "what", "why", "all", "any", "one", "use", "make", "want", "need", "please"}
SKILLSBENCH = "https://www.skillsbench.ai (arXiv 2602.12670): paired with/without-skill evaluation; focused skills beat exhaustive bundles"
MinStatus = Literal["admitted", "provisional"]

Json = dict[str, Any]


def read(name: str) -> Json:
    """Return a JSON file from the skills folder."""
    return json.loads((SKILLS_DIR / name).read_text(encoding="utf-8"))


def task_categories(prompt: str, config: Json) -> list[str]:
    """Return the categories whose task pattern matches the prompt."""
    return [name for name, cat in config["categories"].items() if re.search(cat["task_pattern"], prompt, re.I)]


def stems(text: str) -> set[str]:
    """Return the 6-letter prefixes of the words of 3+ letters in text (so 'accessible' meets 'accessibility')."""
    return {w[:6] for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOP_WORDS}


def skill_stems(entry: Json) -> set[str]:
    """Return the word stems of a registry entry's name and description."""
    return stems(f"{entry['name'].replace('-', ' ')} {entry['description']}")


def relevance(prompt: str, entry: Json, categories: list[str], frequency: Counter[str]) -> float:
    """Return the skill's shared categories plus its shared word stems, each weighted by rarity (stems missing from frequency are too common)."""
    shared = stems(prompt) & skill_stems(entry) & set(frequency)
    return len(set(entry["task_categories"]) & set(categories)) + sum(1 / frequency[s] for s in shared)


def library_entries() -> list[Json]:
    """Return harness library entries and the workspace's own admitted skills, each with the folder to load it from."""
    entries = [e | {"path": f"skills/admitted/{e['name']}"} for e in read("registry.json")["admitted"]]
    if USER_REGISTRY.is_file():
        own = json.loads(USER_REGISTRY.read_text(encoding="utf-8"))["admitted"]
        entries += [e | {"path": (USER_REGISTRY.parent / "skill-library" / e["name"]).as_posix()} for e in own]
    return entries


def rank(prompt: str, min_status: MinStatus, required: tuple[str, ...] = ()) -> Json:
    """Reserve required skills within budget, then rank task-matching skills for loading or recommendation."""
    if min_status not in STATUS_ORDER:
        raise ValueError(f"min_status {min_status!r}, expected one of {list(STATUS_ORDER)}")
    config = read("categories.json")
    budget = config["loadout"]
    categories = task_categories(prompt, config)
    allowed = {s for s, order in STATUS_ORDER.items() if order <= STATUS_ORDER[min_status]}
    library = library_entries()
    reserved: list[Json] = []
    for name in required:
        matches = [e for e in library if e["name"] == name]
        if len(matches) != 1 or matches[0]["status"] not in allowed:
            found = [f"{e['path']} ({e['status']})" for e in matches] or "none"
            raise ValueError(f"required skill {name!r} must resolve uniquely with status allowed by {min_status}; found {found}. "
                             f"A workspace skill (.hve/skills-registry.json) with the same name as a library skill is ambiguous")
        if name not in {e["name"] for e in reserved}:
            reserved.append(matches[0])
    tokens = sum(e["skill_tokens"] for e in reserved)
    if len(reserved) > budget["max_skills"] or tokens > budget["max_tokens"]:
        raise ValueError(f"required skills {list(required)} exceed the loadout budget: {budget}")
    frequency = Counter(s for e in library for s in skill_stems(e))
    frequency = Counter({s: n for s, n in frequency.items() if n <= len(library) / 2})
    matching = [e for e in library if e["status"] in allowed and set(e["task_categories"]) & set(categories)
                and e["name"] not in required]
    matching.sort(key=lambda e: (STATUS_ORDER[e["status"]], -relevance(prompt, e, categories, frequency), -(e["quality_lift_pp"] or 0),
                                 e["skill_tokens"]))
    load: list[Json] = []
    recommend: list[Json] = []
    for e in reserved + matching:
        row = {k: e[k] for k in ("name", "status", "task_categories", "skill_tokens", "quality_lift_pp", "path")}
        if e in reserved:
            load.append(row)
        elif len(load) < budget["max_skills"] and tokens + e["skill_tokens"] <= budget["max_tokens"]:
            load.append(row)
            tokens += e["skill_tokens"]
        else:
            recommend.append(row)
    return {"categories": categories, "load": load, "load_tokens": tokens, "recommend": recommend, "budget": budget,
            "evidence": SKILLSBENCH}


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in STATUS_ORDER:
        raise SystemExit("usage: recommend.py {admitted|provisional} <task description>")
    print(json.dumps(rank(" ".join(args[1:]), args[0]), indent=2))  # type: ignore[arg-type]
