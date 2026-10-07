"""Assemble the extension's runtime/ (Python hooks, loop tools and the skill library) and skills/ from the repository, and check every agent template."""

import py_compile
import re
import shutil
import sys
from pathlib import Path

EXTENSION = Path(__file__).resolve().parent
REPO = EXTENSION.parent
RUNTIME = EXTENSION / "runtime"
SKILLS = EXTENSION / "skills"
PLUGIN_SRC = REPO / "plugins" / "harness-assist"
FILES = {
    "hooks": ["hve_paths.py", "interventions.py", "profile_detector.py", "compaction.py", "loop_guard.py", "flow_guard.py",
              "module_guard.py", "no_fallback.py", "skill_loader.py"],
    "tools/loop": ["loop.py", "diagnose.py", "flow.py"],
    "tools/git": ["branch_workflow.py", "parallel_options.py"],
    "tools/skills": ["recommend.py", "scan.py", "triage.py", "onboard.py", "micro_eval.py", "evaluate.py", "context_load.py"],
    "skills": ["registry.json", "categories.json"],
}
SCRIPTS = ["choice_recorder.py", "guardrail.py", "enterprise_catalog.json"]
RUNTIME_REF = re.compile(r"\{\{RUNTIME\}\}/([\w./-]+\.py)")


def build() -> list[str]:
    """Recreate runtime/ and skills/, compile every Python file, and return the runtime files the agent templates reference."""
    for folder in (RUNTIME, SKILLS):
        if folder.exists():
            shutil.rmtree(folder)
    for folder, names in FILES.items():
        (RUNTIME / folder).mkdir(parents=True)
        for name in names:
            shutil.copy2(REPO / folder / name, RUNTIME / folder / name)
    (RUNTIME / "scripts").mkdir()
    for name in SCRIPTS:
        shutil.copy2(PLUGIN_SRC / "scripts" / name, RUNTIME / "scripts" / name)
    shutil.copytree(PLUGIN_SRC / "skills", SKILLS)
    shutil.copytree(REPO / "skills" / "admitted", RUNTIME / "skills" / "admitted")
    shutil.copy2(REPO / "skills" / "authored" / "NOTICE", RUNTIME / "skills" / "NOTICE")
    (RUNTIME / "skills" / "licenses" / "agentx").mkdir(parents=True)
    for name in ("LICENSE", "NOTICE"):
        shutil.copy2(REPO / "skills" / "imported" / "agentx" / name, RUNTIME / "skills" / "licenses" / "agentx" / name)
    for path in RUNTIME.rglob("*.py"):
        if RUNTIME / "skills" not in path.parents:
            py_compile.compile(str(path), doraise=True)
    for cache in list(RUNTIME.rglob("__pycache__")):
        shutil.rmtree(cache)
    referenced = sorted({ref for agent in (EXTENSION / "agents").glob("*.agent.md")
                         for ref in RUNTIME_REF.findall(agent.read_text(encoding="utf-8"))})
    missing = [ref for ref in referenced if not (RUNTIME / ref).is_file()]
    if missing:
        raise FileNotFoundError(f"agent templates reference runtime files that the build did not copy: {missing}")
    return referenced


if __name__ == "__main__":
    if sys.argv[1:]:
        raise SystemExit("usage: build.py")
    refs = build()
    print(f"runtime and skills assembled in {EXTENSION}; agents reference {len(refs)} runtime files, all present")
