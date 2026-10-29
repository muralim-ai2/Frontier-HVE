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
from recommend import rank, skill_dir  # noqa: E402
from environment import environment  # noqa: E402
from loop_paths import ASK_ID, loop_dir, project_folder, state_file  # noqa: E402
from ask_plan import CHECKLIST_BLOCK, SKILLS_BLOCK, items, plugin_skills, record, refresh, ticked, unfinished  # noqa: E402
from lifecycle_catalog import catalog, pick, route  # noqa: E402
from ask_project import (CREATE, SCOPE_NOTE, SHIFT_OVERLAP, deliverable, ledger, overlap, project_status, project_text,  # noqa: E402,F401
                         record_project, shift_message, topic_shift)
import ask_packs  # noqa: E402
import personas  # noqa: E402
import stage_evidence  # noqa: E402

WORKSPACE = Path.cwd()
ASKS = WORKSPACE / ".hve" / "asks"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
SUBAGENT_RULES = ("Do not edit the loop files (feature_list.json, progress.txt, tracker.json) or loop state (.harness/ or the ask's loop/ "
                  "folder). Checks save screenshots and logs to $HVE_EVIDENCE/<feature>/. No file over 500 lines, no hidden errors, no TODO "
                  "in shipped code. Never commit, push or bypass git hooks. Reply in under 2,000 tokens: files changed, commands and exit codes.")
Status = Literal["planned", "active", "done", "skipped"]

Json = dict[str, Any]


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
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("checklist", "checklist_rendered"):  # asks contracted before 0.13.0 have no checklist yet
        data.setdefault(key, {})
    data["skills"].setdefault("plugin", {})  # asks contracted before the plugin list
    data.setdefault("packs", [])  # asks contracted before expertise packs
    return path, data


def where(prompt: str | None) -> Json:
    """Return the project, the open ask with its paths, and for a prompt the recommended step: continue the open ask, open a new ask in
    the project, start the project, or move to a new workspace. The agent confirms the step with the user."""
    project = project_status()
    data = active()[1] if (ASKS / "active.json").is_file() else None
    out: Json = {"project": project, "open_ask": {k: data[k] for k in ("ask", "request", "created", "paths")} | {"unfinished": unfinished(data)}
                 if data else None}
    if prompt is None:
        return out
    shift = topic_shift(project_text(), prompt) if project else None
    follow_up = data is not None and (not CREATE.match(prompt) or overlap(" ".join([data["request"], *(t["name"] for t in data["tasks"])]),
                                                                           prompt) >= SHIFT_OVERLAP)
    verdict, why = (("new-workspace", shift["reason"]) if shift else ("continue", f"a follow-up to ask {data['ask']}") if follow_up
                    else ("new-ask", "new work in this workspace's project") if project else ("new-project", "no project here yet"))
    return out | {"verdict": verdict, "why": why}


def install(rows: list[Json]) -> None:
    """Copy skills into <workspace>/.hve/skills/<name>/ ('<pack>:<skill>' into '<pack>__<skill>') so every harness reads them in the
    workspace."""
    for row in rows:
        shutil.copytree(ROOT / row["path"], WORKSPACE / ".hve" / "skills" / skill_dir(row["name"]), dirs_exist_ok=True)


def contract(name: str, slug: str, agent: str, request: str, skips: dict[str, str], required: tuple[str, ...] = (),
             pack_names: tuple[str, ...] = (), scope: tuple[str, ...] = (), for_stage: str | None = None, gates: str = "all") -> Json:
    """Write a new timestamped ask from a lifecycle with its skills, expertise packs, personas, milestones, checklist and environment,
    install the skills, make it active, recommend a new session or workspace when it is different work, and record an ask it leaves open.
    A scope runs only the named stages; for_stage records the stage of another lifecycle this ask delivers; gates=ticked pauses only
    after the milestones the user ticks."""
    if not SLUG.match(slug):
        raise ValueError(f"slug {slug!r} must match {SLUG.pattern}")
    if gates not in ("all", "ticked"):
        raise ValueError(f"gates must be all or ticked, not {gates!r}")
    lifecycle = catalog()[name]
    names = [s["name"] for s in lifecycle["stages"]]
    unknown = (set(skips) | set(scope)) - set(names)
    if unknown:
        raise ValueError(f"unknown stages {sorted(unknown)} of lifecycle {name!r}: {names}")
    if for_stage and (for_stage.count(":") < 1 or for_stage.rsplit(":", 1)[1] not in {s["name"] for s in catalog()[for_stage.rsplit(":", 1)[0]]["stages"]}):
        raise ValueError(f"for={for_stage!r} must name <lifecycle>:<stage> of a known lifecycle")
    skips = skips | {s: f"{SCOPE_NOTE} ({', '.join(scope)})" for s in names if scope and s not in scope and s not in skips}
    routed = route(request)["packs"]
    packs = ask_packs.chosen(WORKSPACE, routed, list(pack_names), lifecycle)
    previous = active()[1] if (ASKS / "active.json").is_file() else None
    open_reasons = unfinished(previous) if previous else []
    wanted = tuple(dict.fromkeys([*required, *(k for s in lifecycle["stages"] if s["name"] not in skips for k in s["skills"])]))
    ranked = rank(request, "provisional", wanted, tuple(packs))
    install(ranked["load"])
    stamp = datetime.now(timezone.utc)
    now = stamp.isoformat(timespec="seconds")
    ask = f"{stamp:%Y%m%d-%H%M}-{slug}"
    folder = ask_dir(ask)
    if folder.exists():
        raise FileExistsError(f"ask {ask} already exists; use another slug or `lifecycle.py open {ask}`")
    stages = [{k: s[k] for k in ("name", "goal", "agent", "skills", "plugin_skills", "templates", "exit")}
              | {k: s[k] for k in ("evidence", "rework", "loop") if k in s}
              | {"status": "skipped" if s["name"] in skips else "planned", "note": skips.get(s["name"], "")} for s in lifecycle["stages"]]
    personas: dict[str, list[str]] = {}
    for s in stages:
        if s["status"] != "skipped":
            personas.setdefault(agent if s["agent"] == "self" else s["agent"], []).append(s["name"])
    shift = topic_shift(project_text(), request) if project_status() else None
    decisions = [{"ts": now, "stage": s, "choice": "skipped", "why": why} for s, why in skips.items() if not why.startswith(SCOPE_NOTE)]
    if scope:
        decisions.append({"ts": now, "stage": "scope", "choice": ", ".join(scope), "why": "the user came in at these stages"})
    if for_stage:
        decisions.append({"ts": now, "stage": "scope", "choice": f"delivers {for_stage}", "why": f"{name} runs in place of that stage"})
    if pack_names:
        decisions.append({"ts": now, "stage": "packs", "choice": ", ".join(p["name"] for p in packs) or "core only",
                          "why": f"offered {routed['explicit'] + [m['name'] for m in routed['matched']] or 'none'}"})
    if shift:
        decisions.append({"ts": now, "stage": "ask", "choice": f"recommended {shift['recommend']}", "why": shift["reason"]})
    if open_reasons:
        decisions.append({"ts": now, "stage": "ask", "choice": f"opened while ask {previous['ask']} was still open", "why": "; ".join(open_reasons)})
    relative = folder.relative_to(WORKSPACE).as_posix()
    project = project_folder(WORKSPACE).relative_to(WORKSPACE).as_posix()
    data = {"ask": ask, "slug": slug, "request": request, "lifecycle": name, "source": lifecycle["source"], "agent": agent, "created": now,
            "paths": {"ask": relative, "plan": f"{relative}/plan.md", "loop": f"{relative}/loop", "evidence": f"{relative}/loop/evidence",
                      "project": project, "feature_list": f"{project}/feature_list.json",
                      "feature_list_add": f"{project}/feature_list.add.json"},
            "previous_ask": {"ask": previous["ask"] if previous else None, **shift} if shift else None,
            "previous_open": {"ask": previous["ask"], "why": open_reasons} if open_reasons else None,
            "current": None, "stages": stages, "scope": list(scope), "for_stage": for_stage, "gates": gates,
            "packs": [ask_packs.record(p, routed, lifecycle, stages) for p in packs],
            "skills": {"selected": [{k: r[k] for k in ("name", "description", "status", "reason", "relevance", "skill_tokens", "path")}
                                    for r in ranked["load"]],
                       "tokens": ranked["load_tokens"], "over_budget": ranked["over_budget"], "budget": ranked["budget"],
                       "suggested": ranked["suggested"], "suggested_tokens": ranked["suggested_tokens"], "choice": None,
                       "plugin": plugin_skills(stages, request)},
            "personas": [{"agent": a, "stages": names} for a, names in personas.items()], "tasks": [],
            "environment": environment(WORKSPACE), "delegations": [], "reported": [],
            "plan": {"sha256": None, "revisions": []}, "checklist": {}, "checklist_rendered": {}, "decisions": decisions}
    (folder / "loop").mkdir(parents=True)
    (folder / "request.md").write_text(request + "\n", encoding="utf-8")
    refresh(folder, data)
    (folder / "contract.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (ASKS / "active.json").write_text(json.dumps({"active": ask}), encoding="utf-8")
    record_project(slug, request, ask, now, WORKSPACE)
    return data | {"project": project_status()}


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
    refresh(path.parent, data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return s["choice"] | {"skills": [r["name"] for r in s["selected"]]}


def score_skills(scores: dict[str, Json]) -> Json:
    """Record the agent's 0-10 relevance score for this ask ({name: {score, why}}) on every shortlisted skill, rank the shortlist by it, and
    suggest the required skills plus the top-scored up to the loadout's skill count for the user to confirm."""
    path, data = active()
    s = data["skills"]
    names = {r["name"] for r in s["selected"]}
    if set(scores) != names:
        raise ValueError(f"score every shortlisted skill once: missing {sorted(names - set(scores))}, unknown {sorted(set(scores) - names)}")
    bad = [n for n, v in scores.items() if not isinstance(v["score"], int) or not 0 <= v["score"] <= 10 or not v["why"].strip()]
    if bad:
        raise ValueError(f"skills {bad} need an integer score from 0 to 10 and a one-line why")
    s["selected"] = sorted((r | scores[r["name"]] for r in s["selected"]),
                           key=lambda r: (r["reason"] != "required", -r["score"], -r["relevance"]))
    room = s["budget"]["max_skills"]
    top = [r for i, r in enumerate(s["selected"]) if r["reason"] == "required" or (r["score"] > 0 and i < room)]
    s["suggested"], s["suggested_tokens"] = [r["name"] for r in top], sum(r["skill_tokens"] for r in top)
    refresh(path.parent, data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"shortlist": len(s["selected"]), "tokens": s["tokens"], "suggested_tokens": s["suggested_tokens"],
            "suggested": [{k: r[k] for k in ("name", "score", "why", "skill_tokens")} for r in top]}


def set_stage(stage: str, status: Status, note: str) -> Json:
    """Record a stage's status with a one-line note in the active contract; an active stage becomes current, and a stage set back to
    planned (a new sprint, a change of direction) loses its sign-off."""
    path, data = active()
    match = next((s for s in data["stages"] if s["name"] == stage), None)
    if match is None:
        raise ValueError(f"stage {stage!r} is not in the contract: {[s['name'] for s in data['stages']]}")
    missing = stage_evidence.check(WORKSPACE, data["paths"]["ask"], match) if status == "done" else []
    if missing:
        raise ValueError(f"stage {stage} cannot be done: its evidence is missing: {'; '.join(missing)}")
    match |= {"status": status, "note": note}
    if status == "active":
        data["current"] = stage
    if status == "planned":
        data["checklist"].pop(f"stage:{stage}", None)
    data["decisions"].append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage": stage, "choice": status, "why": note})
    refresh(path.parent, data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return match


def rework(stage: str, why: str) -> Json:
    """Take the stage's capped rework step back to its earlier stage and record it; past the cap the user decides."""
    path, data = active()
    result = stage_evidence.rework(data, stage_row(data, stage), why, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    refresh(path.parent, data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return result


def tick(item: str, value: str, note: str) -> Json:
    """Record the user's sign-off of a checklist item (from the agent's form), after taking in any ticks they made in plan.md."""
    path, data = active()
    return _write_tick(path, data, item, value, note)


def _write_tick(path: Path, data: Json, item: str, value: str, note: str) -> Json:
    refresh(path.parent, data)
    entry = record(data, item, value, note, "form")
    refresh(path.parent, data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return entry


def review_revision(path: Path) -> str:
    """Return a digest of the selected ask's review inputs and evidence metadata without writing state."""
    files = [ASKS / "active.json", path, path.parent / "plan.md", project_folder(WORKSPACE) / "feature_list.json",
             state_file(WORKSPACE)]
    files += sorted((path.parent / "loop" / "prs").glob("*.json"))
    files += sorted((path.parent / "loop" / "attempts").glob("*.jsonl"))
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.relative_to(WORKSPACE).as_posix().encode() + b"\0")
        digest.update(file.read_bytes() if file.is_file() else b"<absent>")
        digest.update(b"\0")
    for file in sorted((path.parent / "loop" / "evidence").rglob("*")):
        stat = file.stat()
        digest.update(f"{file.relative_to(WORKSPACE).as_posix()}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}\n".encode())
    return digest.hexdigest()


def review_status(expected_ask: str) -> Json:
    """Return a read-only review ticket for the expected active ask."""
    path, data = active()
    if data["ask"] != expected_ask:
        raise RuntimeError("active ask changed; refresh the UI before reviewing")
    return {"ask": data["ask"], "revision": review_revision(path)}


def tick_for(expected_ask: str, revision: str, item: str, value: str, note: str) -> Json:
    """Record a human review only for the expected ask and unchanged review inputs."""
    path, data = active()
    if data["ask"] != expected_ask or review_revision(path) != revision:
        raise RuntimeError("ask or review inputs changed; refresh the UI and review again")
    if item not in items(data) or not item.startswith(("stage:", "task:")) or value not in ("accepted", "changes") or not note.strip():
        raise ValueError("guarded review needs a stage/task, accepted/changes, and a non-empty human note")
    return {"ask": expected_ask, **_write_tick(path, data, item, value, note)}


def checklist() -> Json:
    """Return the active ask's checklist after taking in ticks made in plan.md: each item's sign-off, and why the ask is not finished."""
    path, data = active()
    applied = refresh(path.parent, data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ask": data["ask"], "ticked_in_plan": applied, "open": unfinished(data),
            "items": {i: data["checklist"].get(i, {"value": "open"}) | {"ticked": ticked(data, i)} for i in items(data)}}


def close() -> Json:
    """Close the active ask so workspace and user-level hooks stop acting in this workspace; its files stay."""
    ask = active()[1]["ask"]
    (ASKS / "active.json").unlink()
    return {"closed": ask}


def reopen(ask: str) -> Json:
    """Make an existing ask active again and return its paths, current milestone and unfinished items."""
    if not (ask_dir(ask) / "contract.json").is_file():
        raise FileNotFoundError(f"no ask {ask!r} in {ASKS}")
    (ASKS / "active.json").write_text(json.dumps({"active": ask}), encoding="utf-8")
    data = active()[1]
    return {"active": ask, "paths": data["paths"], "current": data["current"], "unfinished": unfinished(data)}


def forget(ask: str) -> Json:
    """Remove an ask whose files were deleted from the project record and the active pointer, and its empty folder; refuse an ask that
    still has its contract or owns features."""
    if (ask_dir(ask) / "contract.json").is_file():
        raise ValueError(f"ask {ask} still has its contract.json; only an ask whose files were deleted can be forgotten")
    path = project_folder(WORKSPACE) / "project.json"
    project = json.loads(path.read_text(encoding="utf-8"))
    if ask not in project["asks"]:
        raise ValueError(f"ask {ask} is not in {path}")
    state = state_file(WORKSPACE)
    owned = [name for name, row in json.loads(state.read_text(encoding="utf-8"))["lock"].items() if row.get("ask") == ask] if state.is_file() else []
    if owned:
        raise ValueError(f"ask {ask} owns features {', '.join(owned)}; restore its folder (for example from git) instead of forgetting it")
    project["asks"].remove(ask)
    path.write_text(json.dumps(project, indent=2), encoding="utf-8")
    pointer = ASKS / "active.json"
    was_active = pointer.is_file() and json.loads(pointer.read_text(encoding="utf-8"))["active"] == ask
    if was_active:
        pointer.unlink()
    folder = ask_dir(ask)
    removed = folder.is_dir() and not any(folder.iterdir())
    if removed:
        folder.rmdir()
    return {"forgotten": ask, "was_active": was_active, "folder_removed": removed}


def current_skills() -> list[str]:
    """Return the active ask's current stage skills and contract skills, or none when no ask is active."""
    if not (ASKS / "active.json").exists():
        return []
    data = active()[1]
    stage = next((s["skills"] for s in data["stages"] if s["name"] == data["current"]), [])
    return list(dict.fromkeys([*stage, *(r["name"] for r in data["skills"]["selected"])]))


def plan_hash(contract_path: Path) -> str | None:
    """Return the SHA-256 of the ask's plan.md without its generated skills and checklist blocks, or None before the plan is written."""
    plan = contract_path.parent / "plan.md"
    text = CHECKLIST_BLOCK.sub("", SKILLS_BLOCK.sub("", plan.read_text(encoding="utf-8"))).strip() if plan.is_file() else ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def plan_sync(note: str) -> Json:
    """Refresh the plan's generated blocks and record the current plan.md as a new plan revision with a one-line note of what changed."""
    path, data = active()
    refresh(path.parent, data)
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
    """Map the features this ask added to the project's feature list as its tasks: new ones get the current milestone, its persona and
    skills; all get their pass state."""
    path, data = active()
    features = json.loads((loop_dir(project) / "feature_list.json").read_text(encoding="utf-8"))
    lock = json.loads(state_file(project).read_text(encoding="utf-8"))["lock"] if state_file(project).is_file() else None
    features = [f for f in features if lock is None or lock[f["name"]].get("ask") == data["ask"]]
    stage = stage_row(data, None)
    fresh = {"milestone": stage["name"], "persona": data["agent"] if stage["agent"] == "self" else stage["agent"],
             "skills": stage["skills"] or [r["name"] for r in data["skills"]["selected"]]}
    known = {t["name"]: t for t in data["tasks"]}
    data["tasks"] = [known.get(f["name"], {"name": f["name"]} | fresh) | {"passes": f["passes"]} for f in features]
    refresh(path.parent, data)
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
    install([r for r in data["skills"]["selected"] if r["name"] in skills])
    servers = sorted({s["name"] for s in data["environment"]["mcp_servers"]})
    role = personas.by_agent().get(persona)
    data["delegations"].append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "persona": persona, "stage": row["name"],
                                "task": task, "skills": skills})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return "\n".join([
        f"Frontier HVE brief: ask {data['ask']}, stage {row['name']}" + (f", task {task}" if task else ""),
        *([f"- Your role: {role['title']}. {role['goal']}"] if role else []),
        f"- Stage goal: {row['goal']} Gate: {row['exit']}",
        f"- Ask folder: {data['paths']['ask']}/ (prototypes and drafts go there, never in the workspace root)",
        "- Read and follow before you start: " + (", ".join(f".hve/skills/{skill_dir(s)}/SKILL.md" for s in skills) or "no library skills"),
        "- Plugin skills you may use: " + (", ".join(dict.fromkeys([*row["plugin_skills"], *data["skills"]["plugin"]])) or "none"),
        *ask_packs.brief_lines(data, row),
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
    """CLI: list | pick <request> | route <request-file> | show <name>
    | contract <name> <slug> <agent> <request-file> [stage=why ...] [+skill ...] [@pack ... | @core] [only=<s,s>] [for=<lc>:<s>] [gates=ticked]
    | stage <name> <status> <note> | rework <stage> <why> | tick <item> <value> [note] | checklist | ledger [lifecycle]
    | review-status <expected-ask> | tick-for <expected-ask> <revision> <item> <accepted|changes> <note>
    | skills suggested|all|<skill,...> | skills score <scores.json> | shift <prompt>
    | where [request-file]
    | plan-sync <note> | plan-status | tasks-sync [project] | brief <persona> [stage=<s>] [task=<t>] | used <persona> <task|-> <skill,...|none>
    | report <session> | close | open <ask-id> | forget <ask-id>."""
    args = sys.argv[1:]
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # Windows pipes default to cp1252
    if args[:1] == ["list"]:
        out: Any = [{k: c[k] for k in ("name", "title", "summary", "source")} for c in catalog().values()]
    elif args[:1] == ["pick"] and len(args) == 2:
        out = pick(args[1])
    elif args[:1] == ["route"] and len(args) == 2:
        out = route(Path(args[1]).read_text(encoding="utf-8").strip())
    elif args[:1] == ["show"] and len(args) == 2:
        out = catalog()[args[1]]
    elif args[:1] == ["contract"] and len(args) >= 5:
        options = dict(a.split("=", 1) for a in args[5:] if a.split("=", 1)[0] in ("only", "for", "gates"))
        skips = dict(a.split("=", 1) for a in args[5:] if a[:1] not in "+@" and a.split("=", 1)[0] not in options)
        required = tuple(a[1:] for a in args[5:] if a.startswith("+"))
        packs = tuple(a[1:] for a in args[5:] if a.startswith("@"))
        out = contract(args[1], args[2], args[3], Path(args[4]).read_text(encoding="utf-8").strip(), skips, required, packs,
                       tuple(s.strip() for s in options.get("only", "").split(",") if s.strip()), options.get("for"), options.get("gates", "all"))
    elif args[:1] == ["ledger"] and len(args) <= 2:
        out = ledger(args[1] if len(args) == 2 else "team-delivery", WORKSPACE)
    elif args[:1] == ["stage"] and len(args) == 4 and args[2] in ("planned", "active", "done", "skipped"):
        out = set_stage(args[1], args[2], args[3])  # type: ignore[arg-type]
    elif args[:1] == ["rework"] and len(args) == 3:
        out = rework(args[1], args[2])
    elif args[:1] == ["tick"] and len(args) in (3, 4):
        out = tick(args[1], args[2], args[3] if len(args) == 4 else "")
    elif args[:1] == ["review-status"] and len(args) == 2:
        out = review_status(args[1])
    elif args[:1] == ["tick-for"] and len(args) == 6:
        out = tick_for(*args[1:])
    elif args[:1] == ["checklist"] and len(args) == 1:
        out = checklist()
    elif args[:1] == ["skills"] and len(args) == 3 and args[1] == "score":
        out = score_skills(json.loads(Path(args[2]).read_text(encoding="utf-8")))
    elif args[:1] == ["skills"] and len(args) == 2:
        out = choose_skills(args[1])
    elif args[:1] == ["shift"] and len(args) == 2:
        out = topic_shift(project_text(), args[1])
    elif args[:1] == ["where"] and len(args) <= 2:
        out = where(Path(args[1]).read_text(encoding="utf-8").strip() if len(args) == 2 else None)
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
    elif args[:1] == ["forget"] and len(args) == 2:
        out = forget(args[1])
    elif args[:1] == ["report"] and len(args) == 2:
        from ask_report import report  # ask_report imports this module
        print(report(args[1]))
        return
    else:
        raise SystemExit(main.__doc__)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
