"""Find, pick and contract delivery lifecycles, track each ask's skills, personas, milestones and tasks, brief sub-agents, and report expected against actual."""

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "skills"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recommend import rank, stems  # noqa: E402
from environment import environment  # noqa: E402
from loop_paths import ASK_ID, loop_dir  # noqa: E402

WORKSPACE = Path.cwd()
ASKS = WORKSPACE / ".hve" / "asks"
SOURCES = [ROOT / "templates" / "lifecycles", *sorted(ROOT.glob("plugins/*/lifecycles")), *sorted(WORKSPACE.glob("plugins/*/lifecycles")),
           WORKSPACE / ".hve" / "lifecycles"]
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
STAGE_FIELDS = {"name", "goal", "agent", "skills", "plugin_skills", "templates", "exit", "skip_when"}
SKILLS_BLOCK = re.compile(r"<!-- hve:skills -->.*?<!-- /hve:skills -->\n?", re.S)
SUBAGENT_RULES = ("Do not edit the loop files (feature_list.json, progress.txt, tracker.json) or loop state (.harness/ or the ask's loop/ "
                  "folder). Checks save screenshots and logs to $HVE_EVIDENCE/<feature>/. No file over 500 lines, no hidden errors, no TODO "
                  "in shipped code. Never commit, push or bypass git hooks. Reply in under 2,000 tokens: files changed, commands and exit codes.")
CREATE = re.compile(r"^\s*(?:please\s+|(?:can|could|would)\s+you\s+)?(build|creat\w*|develop\w*|make|writ\w*|draft\w*|design\w*|"
                    r"generat\w*|prepar\w*|start\w*)\b", re.I)
SHIFT_MIN_WORDS = 3
SHIFT_OVERLAP = 0.2
Status = Literal["planned", "active", "done", "skipped"]

Json = dict[str, Any]


def validate(lifecycle: Json, source: Path) -> Json:
    """Return the lifecycle after checking its fields and stages, or raise naming the file."""
    missing = {"name", "title", "summary", "fits", "stages"} - set(lifecycle)
    if missing or not lifecycle["stages"]:
        raise ValueError(f"{source}: lifecycle needs name, title, summary, fits and non-empty stages; missing {sorted(missing)}")
    for stage in lifecycle["stages"]:
        if not STAGE_FIELDS <= set(stage):
            raise ValueError(f"{source}: stage {stage.get('name')!r} needs {sorted(STAGE_FIELDS - set(stage))}")
    return lifecycle | {"source": source.as_posix()}


def catalog() -> dict[str, Json]:
    """Return every lifecycle by name; a later source (plugin, then workspace) overrides an earlier one of the same name."""
    found: dict[str, Json] = {}
    for folder in SOURCES:
        for path in sorted(folder.glob("*.json")):
            lifecycle = validate(json.loads(path.read_text(encoding="utf-8")), path)
            found[lifecycle["name"]] = lifecycle | ({"overrides": found[lifecycle["name"]]["source"]} if lifecycle["name"] in found else {})
    return found


def pick(request: str) -> list[Json]:
    """Return lifecycles ranked by the request words they fit, with the matched words as the reason."""
    words = stems(request)
    ranked = [{"name": c["name"], "title": c["title"], "summary": c["summary"], "source": c["source"],
               "matched": sorted(words & stems(" ".join(c["fits"])))} for c in catalog().values()]
    return sorted(ranked, key=lambda r: -len(r["matched"]))


def ask_dir(ask: str) -> Path:
    """Return the folder of an ask after checking its id (<YYYYMMDD>-<HHMM>-<slug>, UTC)."""
    if not ASK_ID.match(ask):
        raise ValueError(f"ask id {ask!r} must match {ASK_ID.pattern}")
    return ASKS / ask


def active(workspace: Path = WORKSPACE) -> tuple[Path, Json]:
    """Return the active ask's contract path and contract."""
    asks = workspace / ".hve" / "asks"
    ask = json.loads((asks / "active.json").read_text(encoding="utf-8"))["active"]
    if not ASK_ID.match(ask):
        raise ValueError(f"ask id {ask!r} must match {ASK_ID.pattern}")
    path = asks / ask / "contract.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def deliverable(text: str) -> str | None:
    """Return the lifecycle (kind of deliverable) whose fit words the text matches most, or None when none match."""
    ranked = [p for p in pick(text) if p["matched"] and p["name"] != "direct"]
    return ranked[0]["name"] if ranked else None


def subject(text: str) -> set[str]:
    """Return the text's word stems without creation verbs and lifecycle fit words (app, report, deck), leaving what the work is about."""
    generic = stems(" ".join(f for c in catalog().values() for f in c["fits"]) + " build create develop make write draft design generate "
                    "prepare start formal new simple")
    return stems(text) - generic


def topic_shift(previous: str, prompt: str) -> Json | None:
    """Return a recommendation when a prompt starts different work from the open ask: a new workspace when the kind of deliverable
    differs, a new session for new work of the same kind; None for a follow-up."""
    new = subject(prompt)
    overlap = len(new & subject(previous)) / len(new) if new else 1.0
    kinds = (deliverable(previous), deliverable(prompt))
    if None not in kinds and kinds[0] != kinds[1] and overlap < SHIFT_OVERLAP:
        return {"recommend": "new-workspace", "overlap": round(overlap, 2), "kinds": list(kinds),
                "reason": f"this is {kinds[1]} work and the open ask is {kinds[0]} work: their files, skills and checks belong apart"}
    if CREATE.match(prompt) and len(new) >= SHIFT_MIN_WORDS and overlap < SHIFT_OVERLAP:
        return {"recommend": "new-session", "overlap": round(overlap, 2), "kinds": list(kinds),
                "reason": "this starts new work that shares little with the open ask; a fresh chat keeps both contexts small"}
    return None


def shift_message(shift: Json, ask: str) -> str:
    """Return the one-line recommendation to show the user for a topic shift away from an open ask."""
    where = "a new workspace (open another folder)" if shift["recommend"] == "new-workspace" else "a new chat"
    return (f"Frontier HVE: this looks like a different piece of work from ask {ask}; {shift['reason']}. Recommended: continue in {where}. "
            "You can also stay: the agent then opens a new ask here and records your choice.")


def install(paths: list[str]) -> None:
    """Copy library skills into <workspace>/.hve/skills/<name>/ so every harness reads them inside the workspace."""
    for source in paths:
        shutil.copytree(ROOT / source, WORKSPACE / ".hve" / "skills" / Path(source).name, dirs_exist_ok=True)


def skills_block(data: Json) -> str:
    """Return the generated plan.md block listing the ask's skills (with a set under the guideline) and MCP tool load."""
    s = data["skills"]
    rows = "\n".join(f"| {r['name']} | {r['status']} | {r['reason']} | {r['skill_tokens']:,} | {'yes' if r['name'] in s['suggested'] else 'no'} |"
                     for r in s["selected"]) or "| none | | | | |"
    warning = (f"\n**Over the loadout guideline** ({s['budget']['max_skills']} skills, {s['budget']['max_tokens']:,} tokens): these skills "
               f"add their tokens to every turn of this ask. Suggested set: {len(s['suggested'])} skills, {s['suggested_tokens']:,} tokens "
               "(`lifecycle.py skills suggested`); keep all with `lifecycle.py skills all`.\n" if s["over_budget"] else "")
    choice = (f"\nChoice: {s['choice']['choice']} ({s['choice']['tokens']:,} tokens, {s['choice']['over_guideline_tokens']:,} over the "
              "guideline; the report records how much of it was cached).\n" if s.get("choice") else "")
    load = data["environment"]["tool_load"]
    servers = "\n".join(f"- {h}: {', '.join(v['servers'])} (about {v['estimated_tokens']:,} tokens of tool definitions)"
                        for h, v in load["harnesses"].items()) or "- none configured"
    tool_warning = "".join(f"\n**Tool load over {load['warn_tokens']:,} tokens**: {w}. Disable MCP servers this ask does not need.\n"
                           for w in load["warnings"])
    return (f"<!-- hve:skills -->\n## Skills and tools (generated by lifecycle.py)\n\n{len(s['selected'])} skills, {s['tokens']:,} tokens.\n"
            f"{warning}{choice}\n| Skill | Status | Why | Tokens | Suggested |\n|---|---|---|---|---|\n{rows}\n\n"
            f"MCP servers per harness:\n{servers}\n{tool_warning}<!-- /hve:skills -->\n")


def write_skills_block(folder: Path, data: Json) -> None:
    """Write or refresh the generated skills block in the ask's plan.md, keeping everything else."""
    plan = folder / "plan.md"
    text = plan.read_text(encoding="utf-8") if plan.is_file() else ""
    block = skills_block(data)
    text = SKILLS_BLOCK.sub(lambda _: block, text) if SKILLS_BLOCK.search(text) else (text.rstrip() + "\n\n" if text.strip() else "") + block
    plan.write_text(text, encoding="utf-8")


def contract(name: str, slug: str, agent: str, request: str, skips: dict[str, str], required: tuple[str, ...] = ()) -> Json:
    """Write a new timestamped ask from a lifecycle with its skills, personas, milestones and environment, install the skills, make it
    active, and recommend a new session or workspace when it is different work from the ask it replaces."""
    if not SLUG.match(slug):
        raise ValueError(f"slug {slug!r} must match {SLUG.pattern}")
    lifecycle = catalog()[name]
    unknown = set(skips) - {s["name"] for s in lifecycle["stages"]}
    if unknown:
        raise ValueError(f"cannot skip unknown stages {sorted(unknown)} of lifecycle {name!r}")
    previous = active()[1] if (ASKS / "active.json").is_file() else None
    wanted = tuple(dict.fromkeys([*required, *(k for s in lifecycle["stages"] if s["name"] not in skips for k in s["skills"])]))
    ranked = rank(request, "provisional", wanted)
    install([r["path"] for r in ranked["load"]])
    stamp = datetime.now(timezone.utc)
    now = stamp.isoformat(timespec="seconds")
    ask = f"{stamp:%Y%m%d-%H%M}-{slug}"
    folder = ask_dir(ask)
    if folder.exists():
        raise FileExistsError(f"ask {ask} already exists; use another slug or `lifecycle.py open {ask}`")
    stages = [{k: s[k] for k in ("name", "goal", "agent", "skills", "plugin_skills", "templates", "exit")}
              | {"status": "skipped" if s["name"] in skips else "planned", "note": skips.get(s["name"], "")} for s in lifecycle["stages"]]
    personas: dict[str, list[str]] = {}
    for s in stages:
        if s["status"] != "skipped":
            personas.setdefault(agent if s["agent"] == "self" else s["agent"], []).append(s["name"])
    shift = topic_shift(previous["request"], request) if previous else None
    decisions = [{"ts": now, "stage": s, "choice": "skipped", "why": why} for s, why in skips.items()]
    if shift:
        decisions.append({"ts": now, "stage": "ask", "choice": f"recommended {shift['recommend']}", "why": shift["reason"]})
    relative = folder.relative_to(WORKSPACE).as_posix()
    data = {"ask": ask, "slug": slug, "request": request, "lifecycle": name, "source": lifecycle["source"], "agent": agent, "created": now,
            "paths": {"ask": relative, "plan": f"{relative}/plan.md", "loop": f"{relative}/loop",
                      "feature_list": f"{relative}/loop/feature_list.json", "evidence": f"{relative}/loop/evidence"},
            "previous_ask": {"ask": previous["ask"], **shift} if previous and shift else None,
            "current": None, "stages": stages,
            "skills": {"selected": [{k: r[k] for k in ("name", "status", "reason", "relevance", "skill_tokens", "path")} for r in ranked["load"]],
                       "tokens": ranked["load_tokens"], "over_budget": ranked["over_budget"], "budget": ranked["budget"],
                       "suggested": ranked["suggested"], "suggested_tokens": ranked["suggested_tokens"], "choice": None},
            "personas": [{"agent": a, "stages": names} for a, names in personas.items()], "tasks": [],
            "environment": environment(WORKSPACE), "delegations": [], "reported": [],
            "plan": {"sha256": None, "revisions": []}, "decisions": decisions}
    (folder / "loop").mkdir(parents=True)
    (folder / "request.md").write_text(request + "\n", encoding="utf-8")
    (folder / "contract.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (ASKS / "active.json").write_text(json.dumps({"active": ask}), encoding="utf-8")
    write_skills_block(folder, data)
    return data


def choose_skills(choice: str) -> Json:
    """Keep the suggested skill set, all skills, or the named ones (comma-separated), and record the choice and its token cost."""
    path, data = active()
    s = data["skills"]
    names = s["suggested"] if choice == "suggested" else [r["name"] for r in s["selected"]] if choice == "all" else \
        [n.strip() for n in choice.split(",")]
    unknown = sorted(set(names) - {r["name"] for r in s["selected"]})
    if unknown:
        raise ValueError(f"skills {unknown} are not in the ask's skills; choose from {[r['name'] for r in s['selected']]}")
    s["selected"] = [r for r in s["selected"] if r["name"] in names]
    s["tokens"] = sum(r["skill_tokens"] for r in s["selected"])
    s["over_budget"] = len(s["selected"]) > s["budget"]["max_skills"] or s["tokens"] > s["budget"]["max_tokens"]
    s["choice"] = {"choice": choice, "tokens": s["tokens"], "over_guideline_tokens": max(0, s["tokens"] - s["budget"]["max_tokens"])}
    data["decisions"].append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": "skills", "choice": choice,
                              "why": f"{len(s['selected'])} skills, {s['tokens']:,} tokens"})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    write_skills_block(path.parent, data)
    return s["choice"] | {"skills": [r["name"] for r in s["selected"]]}


def set_stage(stage: str, status: Status, note: str) -> Json:
    """Record a stage's status with a one-line note in the active contract; an active stage becomes current."""
    path, data = active()
    match = next((s for s in data["stages"] if s["name"] == stage), None)
    if match is None:
        raise ValueError(f"stage {stage!r} is not in the contract: {[s['name'] for s in data['stages']]}")
    match |= {"status": status, "note": note}
    if status == "active":
        data["current"] = stage
    data["decisions"].append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": stage, "choice": status, "why": note})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return match


def close() -> Json:
    """Close the active ask so workspace and user-level hooks stop acting in this workspace; its files stay."""
    ask = active()[1]["ask"]
    (ASKS / "active.json").unlink()
    return {"closed": ask}


def reopen(ask: str) -> Json:
    """Make an existing ask active again."""
    if not (ask_dir(ask) / "contract.json").is_file():
        raise FileNotFoundError(f"no ask {ask!r} in {ASKS}")
    (ASKS / "active.json").write_text(json.dumps({"active": ask}), encoding="utf-8")
    return {"active": ask}


def current_skills() -> list[str]:
    """Return the active ask's current stage skills and contract skills, or none when no ask is active."""
    if not (ASKS / "active.json").exists():
        return []
    data = active()[1]
    stage = next((s["skills"] for s in data["stages"] if s["name"] == data["current"]), [])
    return list(dict.fromkeys([*stage, *(r["name"] for r in data["skills"]["selected"])]))


def plan_hash(contract_path: Path) -> str | None:
    """Return the SHA-256 of the ask's plan.md without its generated skills block, or None before the plan is written."""
    plan = contract_path.parent / "plan.md"
    text = SKILLS_BLOCK.sub("", plan.read_text(encoding="utf-8")).strip() if plan.is_file() else ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def plan_sync(note: str) -> Json:
    """Refresh the plan's skills block and record the current plan.md as a new plan revision with a one-line note of what changed."""
    path, data = active()
    write_skills_block(path.parent, data)
    digest = plan_hash(path)
    if digest is None:
        raise FileNotFoundError(f"{path.parent / 'plan.md'} does not exist: write the plan first")
    data["plan"]["sha256"] = digest
    data["plan"]["revisions"].append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sha256": digest, "note": note})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"revision": len(data["plan"]["revisions"]), "note": note}


def plan_status(workspace: Path = WORKSPACE) -> Json | None:
    """Return whether the active ask's plan.md changed since its last sync, or None when there is no active ask or plan."""
    if not (workspace / ".hve" / "asks" / "active.json").is_file():
        return None
    path, data = active(workspace)
    digest = plan_hash(path)
    if digest is None:
        return None
    return {"plan": (path.parent / "plan.md").relative_to(workspace).as_posix(), "changed": digest != data["plan"]["sha256"],
            "revisions": len(data["plan"]["revisions"])}


def stage_row(data: Json, name: str | None) -> Json:
    """Return the named stage, else the current one, else the first stage that is not skipped."""
    wanted = name or data["current"] or next(s["name"] for s in data["stages"] if s["status"] != "skipped")
    match = next((s for s in data["stages"] if s["name"] == wanted), None)
    if match is None:
        raise ValueError(f"stage {wanted!r} is not in the contract: {[s['name'] for s in data['stages']]}")
    return match


def tasks_sync(project: Path) -> list[Json]:
    """Map the project's features to the ask as tasks: new ones get the current milestone, its persona and skills; all get their pass state."""
    path, data = active()
    features = json.loads((loop_dir(project) / "feature_list.json").read_text(encoding="utf-8"))
    stage = stage_row(data, None)
    fresh = {"milestone": stage["name"], "persona": data["agent"] if stage["agent"] == "self" else stage["agent"],
             "skills": stage["skills"] or [r["name"] for r in data["skills"]["selected"]]}
    known = {t["name"]: t for t in data["tasks"]}
    data["tasks"] = [known.get(f["name"], {"name": f["name"]} | fresh) | {"passes": f["passes"]} for f in features]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data["tasks"]


def brief(stage: str | None, task: str | None, persona: str) -> str:
    """Return the delegation brief for a sub-agent (skills, plugin skills, MCP servers, rules, reply format) and log the delegation."""
    path, data = active()
    row = stage_row(data, stage)
    task_row = next((t for t in data["tasks"] if t["name"] == task), None) if task else None
    if task and task_row is None:
        raise ValueError(f"task {task!r} is not in the contract; run `lifecycle.py tasks-sync` after loop.py init or amend")
    skills = task_row["skills"] if task_row else list(dict.fromkeys([*row["skills"], *(r["name"] for r in data["skills"]["selected"])]))
    install([r["path"] for r in data["skills"]["selected"] if r["name"] in skills])
    servers = sorted({s["name"] for s in data["environment"]["mcp_servers"]})
    data["delegations"].append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "persona": persona, "stage": row["name"],
                                "task": task, "skills": skills})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return "\n".join([
        f"Frontier HVE brief: ask {data['ask']}, stage {row['name']}" + (f", task {task}" if task else ""),
        f"- Ask folder: {data['paths']['ask']}/ (prototypes and drafts go there, never in the workspace root)",
        "- Read and follow before you start: " + (", ".join(f".hve/skills/{s}/SKILL.md" for s in skills) or "no library skills"),
        "- Plugin skills you may use: " + (", ".join(row["plugin_skills"]) or "none"),
        "- MCP servers available: " + (", ".join(servers) or "none"),
        f"- Rules: {SUBAGENT_RULES}",
        "- End your reply with one line: SKILLS-USED: <the skills you actually followed, comma-separated, or none>"])


def used(persona: str, task: str | None, skills: list[str]) -> Json:
    """Record the skills a sub-agent reported in its SKILLS-USED line (self-reported evidence)."""
    path, data = active()
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "persona": persona, "task": task, "skills": skills}
    data["reported"].append(entry)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return entry


def main() -> None:
    """CLI: list | pick <request> | show <name> | contract <name> <slug> <agent> <request-file> [stage=why ...] [+skill ...] | stage <name> <status> <note>
    | skills suggested|all|<skill,...> | shift <prompt> | plan-sync <note> | plan-status | tasks-sync [project]
    | brief <persona> [stage=<s>] [task=<t>] | used <persona> <task|-> <skill,...|none> | report <session> | close | open <ask-id>."""
    args = sys.argv[1:]
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # Windows pipes default to cp1252
    if args[:1] == ["list"]:
        out: Any = [{k: c[k] for k in ("name", "title", "summary", "source")} for c in catalog().values()]
    elif args[:1] == ["pick"] and len(args) == 2:
        out = pick(args[1])
    elif args[:1] == ["show"] and len(args) == 2:
        out = catalog()[args[1]]
    elif args[:1] == ["contract"] and len(args) >= 5:
        skips = dict(a.split("=", 1) for a in args[5:] if not a.startswith("+"))
        required = tuple(a[1:] for a in args[5:] if a.startswith("+"))
        out = contract(args[1], args[2], args[3], Path(args[4]).read_text(encoding="utf-8").strip(), skips, required)
    elif args[:1] == ["stage"] and len(args) == 4 and args[2] in ("planned", "active", "done", "skipped"):
        out = set_stage(args[1], args[2], args[3])  # type: ignore[arg-type]
    elif args[:1] == ["skills"] and len(args) == 2:
        out = choose_skills(args[1])
    elif args[:1] == ["shift"] and len(args) == 2:
        out = topic_shift(active()[1]["request"], args[1])
    elif args[:1] == ["plan-sync"] and len(args) == 2:
        out = plan_sync(args[1])
    elif args[:1] == ["plan-status"] and len(args) == 1:
        out = plan_status()
    elif args[:1] == ["tasks-sync"] and len(args) <= 2:
        out = tasks_sync(Path(args[1] if len(args) == 2 else "."))
    elif args[:1] == ["brief"] and len(args) >= 2:
        options = dict(a.split("=", 1) for a in args[2:])
        unknown = set(options) - {"stage", "task"}
        if unknown:
            raise SystemExit(f"brief takes stage=<name> and task=<name>; got {sorted(unknown)}")
        print(brief(options.get("stage"), options.get("task"), args[1]))
        return
    elif args[:1] == ["used"] and len(args) == 4:
        out = used(args[1], None if args[2] == "-" else args[2], [] if args[3] == "none" else [s.strip() for s in args[3].split(",")])
    elif args[:1] == ["close"] and len(args) == 1:
        out = close()
    elif args[:1] == ["open"] and len(args) == 2:
        out = reopen(args[1])
    elif args[:1] == ["report"] and len(args) == 2:
        from ask_report import report  # ask_report imports this module
        print(report(args[1]))
        return
    else:
        raise SystemExit(main.__doc__)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
