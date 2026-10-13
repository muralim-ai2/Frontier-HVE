"""Task-use gate hook: route the prompt to installed plugins, load the best library skills within the loadout budget, offer the rest,
and block other library and plugin skills."""

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, TypedDict

from interventions import record
from hve_paths import RUNS_DIR, STATE_DIR

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
OVERRIDE_FILE = SKILLS_DIR / "eval_override.json"
SESSION_ID = re.compile(r"^[\w-]+$")
SKILL_REF = re.compile(r"([^\s\"'/\\]+)[/\\]+SKILL\.md", re.I)
ASK_TOOL = "vscode_askQuestions"
LOAD_HEADER = "load-skills"
SELECT_HEADER = "select-plugin"
CORE_ONLY = "Core only"
sys.path[:0] = [str(ROOT / "tools" / "skills"), str(ROOT / "tools" / "plugins"), str(ROOT / "tools" / "templates")]
import store  # noqa: E402
from manage import KINDS  # noqa: E402
from recommend import rank  # noqa: E402
from route import candidates  # noqa: E402

Json = dict[str, Any]


class Loadout(TypedDict):
    """One session's skills and plugin routing: loaded skills, ranked skills over budget, selected plugins, candidates, a pending
    choice between several plugins, a one-time notice, the last prompt, and whether the loadout was announced."""

    categories: list[str]
    skills: list[str]
    recommended: list[str]
    plugins: list[str]
    candidates: list[str]
    pending: list[str]
    notice: str | None
    prompt: str
    announced: bool


def state_file(session_id: str) -> Path:
    """Return the session's loadout file after validating the session id."""
    if not SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    return RUNS_DIR / f"{session_id}.skills.json"


def library() -> set[str]:
    """Return the folder names of all library skills: admitted, candidate, the workspace's own, and installed plugin skills."""
    folders = [SKILLS_DIR / "admitted", SKILLS_DIR / "candidates", STATE_DIR / "skill-library"]
    names = {p.name for folder in folders if folder.is_dir() for p in folder.iterdir() if p.is_dir()}
    for name, entry in store.enabled().items():
        names |= {n for s in entry["manifest"]["skills"] for n in (s["name"], f"{name}__{s['name']}")}
    return names


def install_name(source: str) -> str:
    """Return the folder a skill is copied to under .hve/skills: '<plugin>__<skill>' for plugin skills, else the skill name."""
    path = Path(source)
    if path.is_absolute() and path.is_relative_to(store.home() / "plugins"):
        plugin_id = path.relative_to(store.home() / "plugins").parts[0]
        return f"{plugin_id.split('.', 1)[1]}__{path.name}"
    return path.name


def install(sources: list[str]) -> None:
    """Copy library skills into <workspace>/.hve/skills/<folder>/ so the agent reads them inside the workspace."""
    for source in sources:
        shutil.copytree(ROOT / source, STATE_DIR / "skills" / install_name(source), dirs_exist_ok=True)


def route(prompt: str, previous: Loadout | None) -> tuple[list[str], list[str], list[str], str | None]:
    """Return selected plugins, plugins awaiting the user's choice, the candidate set, and a notice for a named missing plugin."""
    fixed = os.environ.get("HARNESS_PLUGIN")
    if fixed is not None:
        store.plugin(fixed)
        return [fixed], [], [fixed], None
    found = candidates(prompt, Path.cwd())
    if found["missing"]:
        return [], [], [], (f"The user named plugin(s) {found['missing']}, which are not installed or are disabled. Stop and tell the "
                            "user to install or enable them (command Frontier HVE: Install plugin); do not continue with the core "
                            "harness instead.")
    if found["explicit"]:
        return found["explicit"], [], found["explicit"], None
    if previous is not None and not set(found["matched"]) - set(previous["candidates"]):
        return previous["plugins"], previous["pending"], previous["candidates"], None
    pool = sorted(set(found["matched"]) | set(previous["plugins"] if previous else []))
    return (pool, [], pool, None) if len(pool) <= 1 else ([], pool, pool, None)


def choose(prompt: str, plugins: list[str]) -> Json:
    """Return the eval override's skills if present, else the ranked core and plugin skills that fit the budget and the ranked rest."""
    if OVERRIDE_FILE.exists():
        return {"categories": [], "skills": json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))["skills"], "recommended": []}
    value = os.environ.get("HARNESS_REQUIRED_SKILLS")
    required = tuple(name.strip() for name in value.split(",")) if value is not None else ()
    ranked = rank(prompt, os.environ["HARNESS_SKILLS_MIN_STATUS"], required, tuple(plugins))  # type: ignore[arg-type]
    return {"categories": ranked["categories"], "skills": [r["path"] for r in ranked["load"]],
            "recommended": [r["path"] for r in ranked["recommend"]]}


def plugin_context(plugins: list[str]) -> str:
    """Return what the selected plugins offer: agents with capabilities, template kinds, flows and rubric contracts."""
    lines = []
    for name in plugins:
        entry = store.plugin(name)
        data, base = entry["manifest"], store.folder(entry)
        agents = ", ".join(f"{name}:{a['name']} ({', '.join(a['capabilities'])})" for a in data["agents"])
        kinds = ", ".join(f"{k} (as workspace source plugin:{name}/{k}@{spec['version']})" if k in KINDS else f"{name}:{k}"
                          for k, spec in data["templates"].items())
        flows = ", ".join(f"{name}:{f}" for f in data["flows"]) or "none"
        rubrics = (base / data["evaluation"]).as_posix() if data["evaluation"] else "none"
        lines.append(f"Plugin {name} {entry['version']}: agents {agents}; templates {kinds or 'none'}; flows {flows}; "
                     f"rubric contract {rubrics}.")
    return " ".join(lines)


def announcement(loadout: Loadout) -> str:
    """Return the one-time instruction: a missing-plugin stop, the plugin question, the plugin context, loaded and offered skills."""
    if loadout["notice"]:
        return loadout["notice"]
    text = ""
    if loadout["pending"]:
        text = (f"Several plugins match this task: {loadout['pending']}. Before using any plugin agent, skill or template, ask the user "
                f"with the ask-questions tool (header `{SELECT_HEADER}`, multi-select, labels = {loadout['pending'] + [CORE_ONLY]}) "
                "which to use; until then work with the core harness only. ")
    elif loadout["plugins"]:
        text = (plugin_context(loadout["plugins"]) + " Delegate matching sub-tasks to these agents and say which agent handles what "
                "before starting. ")
    if loadout["skills"]:
        paths = ", ".join(f".hve/skills/{install_name(s)}/SKILL.md" for s in loadout["skills"])
        text += f"Skills loaded for this task: read and follow {paths} before continuing. Do not use other library skills."
    if loadout["recommended"]:
        names = ", ".join(install_name(s) for s in loadout["recommended"])
        text += (f" Also relevant but over the loadout budget (ranked): {names}. Tell the user and ask with the ask-questions tool "
                 f"(header `{LOAD_HEADER}`, multi-select, labels = skill names) which to add; only ticked skills load.")
    return text.strip()


def pre_tool_output(session_id: str, loadout: Loadout, tool_input: Json) -> Json | None:
    """Return a deny for reading a library SKILL.md outside the loadout, the one-time announcement, or nothing."""
    allowed = {install_name(s) for s in loadout["skills"]} | {Path(s).name for s in loadout["skills"]}
    blocked = sorted({m for m in SKILL_REF.findall(json.dumps(tool_input)) if m in library() and m not in allowed})
    if blocked:
        reason = f"Skill(s) {blocked} are not loaded for this task. Use only: {sorted(allowed) or 'none'}."
        record(session_id, "skill_loader", "skill_denied", reason)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}
    if loadout["announced"]:
        return None
    text = announcement(loadout)
    loadout["announced"] = True
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}} if text else None


def answered(tool_input: Json, tool_response: Any, header: str) -> list[str] | None:
    """Return the labels ticked under a question header, or None when the call did not ask it."""
    if not any(q["header"] == header for q in tool_input["questions"]):
        return None
    answer = (json.loads(tool_response) if isinstance(tool_response, str) else tool_response)["answers"][header]
    return list(answer.get("selected") or [])


def add_ticked(loadout: Loadout, tool_input: Json, tool_response: Any) -> list[str]:
    """Move the skills the user ticked under the load-skills question from recommended into the loadout; return them."""
    ticked_names = answered(tool_input, tool_response, LOAD_HEADER)
    if ticked_names is None:
        return []
    ticked = [s for s in loadout["recommended"] if install_name(s) in ticked_names]
    loadout["skills"] += ticked
    loadout["recommended"] = [s for s in loadout["recommended"] if s not in ticked]
    loadout["announced"] = loadout["announced"] and not ticked
    return ticked


def apply_choice(loadout: Loadout, tool_input: Json, tool_response: Any) -> list[str]:
    """Record the plugins the user picked under select-plugin, recompute the loadout for them, and return the skills to install."""
    picked = answered(tool_input, tool_response, SELECT_HEADER)
    if picked is None or not loadout["pending"]:
        return []
    loadout["plugins"] = [] if CORE_ONLY in picked else [p for p in loadout["pending"] if p in picked]
    loadout["pending"] = []
    loadout.update(choose(loadout["prompt"], loadout["plugins"]))  # type: ignore[typeddict-item]
    loadout["announced"] = False
    return loadout["skills"]


def start(prompt: str, previous: Loadout | None) -> Loadout:
    """Route the prompt and rank its skills into a new, unannounced loadout, and install the loaded skills."""
    plugins, pending, pool, notice = route(prompt, previous)
    loadout = Loadout(plugins=plugins, candidates=pool, pending=pending, notice=notice, prompt=prompt, announced=False,
                      **choose(prompt, plugins))
    install(loadout["skills"])
    return loadout


def main() -> None:
    """Route and install the loadout on UserPromptSubmit; enforce and announce it on PreToolUse; apply answers on PostToolUse."""
    payload = json.load(sys.stdin)
    path = state_file(payload["session_id"])
    event = payload["hook_event_name"]
    if event == "UserPromptSubmit":
        previous: Loadout | None = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        path.write_text(json.dumps(start(payload["prompt"], previous)), encoding="utf-8")
        return
    if event not in ("PreToolUse", "PostToolUse"):
        raise ValueError(f"skill_loader.py does not handle hook event {event!r}")
    plugin_agent = os.environ.get("HARNESS_PLUGIN")
    if not path.exists():
        if plugin_agent is None:
            raise FileNotFoundError(f"{path} missing: the UserPromptSubmit skill_loader hook did not run for this session")
        # A plugin agent started as a sub-agent gets no prompt hook; its plugin's description stands in for the prompt.
        path.write_text(json.dumps(start(store.plugin(plugin_agent)["manifest"]["description"], None)), encoding="utf-8")
    loadout = json.loads(path.read_text(encoding="utf-8"))
    output = None
    if event == "PreToolUse":
        output = pre_tool_output(payload["session_id"], loadout, payload["tool_input"])
    elif payload["tool_name"] == ASK_TOOL:
        install(apply_choice(loadout, payload["tool_input"], payload["tool_response"]))
        install(add_ticked(loadout, payload["tool_input"], payload["tool_response"]))
    path.write_text(json.dumps(loadout), encoding="utf-8")
    if output:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
