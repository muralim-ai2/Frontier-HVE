"""Import source skills verbatim into the library: copy them with their license, draft 3 tasks each, micro-evaluate, and apply the strict gate."""

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import micro_eval
from onboard import onboard

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "research" / "findings" / "phase-9-source-skill-manifest.json"
IMPORTED = ROOT / "skills" / "imported" / "agentx"
TASKS_DIR = ROOT / "tests" / "skill_tasks" / "imported"
TASKS_PER_SKILL = 3
SOURCE = "AgentX fc39b29, verbatim (Apache-2.0, skills/imported/agentx/LICENSE and NOTICE)"
TASK_WRITER = ("You write evaluation tasks for a coding-assistant skill. From the skill's name and description only, write "
               f"{TASKS_PER_SKILL} small, realistic requests a user might make where this skill should help. Each must be answerable in "
               "at most 250 words and have 3-4 concrete, checkable criteria of a good answer. Do not mention the skill. "
               'Reply with JSON only: [{"prompt": "...", "checks": ["...", "..."]}]')

Json = dict[str, Any]


def candidates(extra: list[str]) -> list[Json]:
    """Return tier-1 manifest skills without an authored counterpart or script dependency, plus the named extras."""
    skills = json.loads(MANIFEST.read_text(encoding="utf-8"))["skills"]
    return [s for s in skills if (s["disposition"] == "tier 1: requested area" and not s["authored_counterpart"]) or s["name"] in extra]


def copy_verbatim(source_root: Path, skill: Json) -> Path:
    """Copy one source skill folder unchanged into skills/imported/agentx/<group>/<name>/ and return it."""
    target = IMPORTED / skill["group"] / skill["name"]
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source_root / skill["path"], target)
    return target


def draft_tasks(client: micro_eval.Client, model: str, skill_dir: Path) -> list[Json]:
    """Return the skill's task suite, drafted once from its name and description by the task-writer model and saved."""
    path = TASKS_DIR / f"{skill_dir.name}.json"
    if not path.exists():
        head = (skill_dir / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        reply = client.chat(model, [{"role": "system", "content": TASK_WRITER}, {"role": "user", "content": head.strip()}])["content"]
        tasks = json.loads(reply[reply.index("["):reply.rindex("]") + 1])[:TASKS_PER_SKILL]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([{"id": f"{skill_dir.name}-{i}"} | t for i, t in enumerate(tasks, 1)], indent=1) + "\n", encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def run(source_root: Path, extra: list[str]) -> list[Json]:
    """Copy, draft tasks for, evaluate and onboard every candidate; return the onboarding results."""
    for name in ("LICENSE", "NOTICE"):
        IMPORTED.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / name, IMPORTED / name)
    dirs = {s["name"]: copy_verbatim(source_root, s) for s in candidates(extra)}
    config = json.loads((micro_eval.SKILLS_DIR / "categories.json").read_text(encoding="utf-8"))["micro_eval"]
    client = micro_eval.Client(micro_eval.read_env(ROOT / ".env.local")["AZURE_OPENAI_ENDPOINT"], micro_eval.access_token(), config["models"])
    suites = {n: draft_tasks(client, config["judge"], d) for n, d in dirs.items()}
    texts = {n: (d / "SKILL.md").read_text(encoding="utf-8") for n, d in dirs.items()}
    evals = micro_eval.run(suites, texts, ROOT / ".env.local", micro_eval.EVALS_DIR)
    for e in evals:
        e["eval_method"] = "micro-strict"
        (micro_eval.EVALS_DIR / f"{e['skill']}.json").write_text(json.dumps(e, indent=2) + "\n", encoding="utf-8")
    return [onboard(dirs[e["skill"]], SOURCE, "eval") | {"eval": e} for e in evals]


def admit_untested(source_root: Path, extra: list[str]) -> list[Json]:
    """Copy every candidate and admit it as provisional with its evaluation pending (scan and category checks only)."""
    for name in ("LICENSE", "NOTICE"):
        IMPORTED.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / name, IMPORTED / name)
    return [onboard(copy_verbatim(source_root, s), SOURCE, "untested") for s in candidates(extra)]


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in ("eval", "untested"):
        raise SystemExit("usage: import_eval.py eval|untested <source repo clone> [extra skill name ...]   (run from the repository root)")
    if args[0] == "untested":
        for r in admit_untested(Path(args[1]), args[2:]):
            print(f"{r['name']:<28} {'provisional (eval pending)' if r['admitted'] else 'rejected'}  {r['skill_tokens']} tokens  "
                  f"{'; '.join(r['reasons'])}")
        raise SystemExit(0)
    for r in run(Path(args[1]), args[2:]):
        e = r["eval"]
        print(f"{r['name']:<28} {'ADMIT' if r['admitted'] else 'reject':<6} lift {e['quality_lift_pp']:>6} pp  wins {e['wins']}/{len(e['per_task'])}  "
              f"checks +{e['check_gains']}/-{e['check_losses']} p={e['check_sign_test_p']}  {'; '.join(r['reasons'])}")
