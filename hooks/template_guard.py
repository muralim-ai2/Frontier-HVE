"""Announce template policy and gate registered deliverables at session stop."""

import json
import re
import sys
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "templates"))
from manage import KINDS, check_session, configuration, request  # noqa: E402

AUTHOR = re.compile(r"^\s*(?:please\s+|(?:can|could|would)\s+you\s+(?:please\s+)?)?"
                    r"(?:create|write|draft|prepare|generate|produce|author|update|revise)\s+"
                    r"(?:(?:a|an|the|my|our|new|updated)\s+)*", re.I)
NEGATIVE = re.compile(r"\b(don't|do not|not|no|without|avoid|cancel)\b", re.I)
TYPES = {
    "prd": re.compile(r"\b(prd|product requirements? document)\b", re.I),
    "technicalDesign": re.compile(r"\b(tds|technical design(?: specification)?|technical (?:design )?specification)\b", re.I),
    "testStrategy": re.compile(r"\btest strateg(?:y|ies)\b", re.I),
}


class Payload(TypedDict, total=False):
    """Lifecycle fields needed by the template guard."""

    session_id: str
    hook_event_name: str
    prompt: str
    stop_hook_active: bool


def requested_types(prompt: str) -> list[str]:
    """Identify explicit authoring clauses rather than informational mentions."""
    kinds: set[str] = set()
    for clause in re.split(r"[.!?;]", prompt.replace("\u2019", "'")):
        if NEGATIVE.search(clause):
            continue
        for kind, pattern in TYPES.items():
            if re.search(AUTHOR.pattern + pattern.pattern
                         + r"(?:\s+(?:document|doc))?(?=\s*(?:$|[,:\n]|\b(?:and|for|about|on|to|of|with)\b))", clause, re.I):
                kinds.add(kind)
        listed = re.search(AUTHOR.pattern + r"(?:these|the following)(?: documents)?\s*:\s*(.+)\Z", clause, re.I | re.S)
        if listed:
            names = [line.strip(" \t-*") for line in listed[1].splitlines() if line.strip()]
            if all(any(pattern.fullmatch(name) for pattern in TYPES.values()) for name in names):
                kinds.update(kind for kind, pattern in TYPES.items() if any(pattern.fullmatch(name) for name in names))
    return [kind for kind in KINDS if kind in kinds]


def handle(payload: Payload, workspace: Path) -> dict[str, object] | None:
    """Return policy context or explicit, bounded validation failure feedback."""
    event = payload["hook_event_name"]
    session = payload["session_id"]
    if event == "Stop":
        try:
            policy = configuration(workspace)
            errors = check_session(workspace, session) if policy["enforce"] else []
        except (OSError, ValueError) as error:
            errors = [f"template validation error: {error}"]
        if not errors:
            return None
        reason = ("Deliverables are not complete: " + "; ".join(errors)
                  + ". Correct these errors or explicitly report them as unresolved; do not claim completion.")
        if payload["stop_hook_active"]:
            return {"systemMessage": reason}
        return {"hookSpecificOutput": {"hookEventName": "Stop", "decision": "block", "reason": reason}}
    policy = configuration(workspace)
    command = f'python "{(ROOT / "tools" / "templates" / "manage.py").as_posix()}"'
    context = (f"Frontier HVE deliverable templates: session {session}. "
               f"For PRD, technical design or test strategy authoring use the deliverable-templates skill. "
               f"Register every requested type with {command} request <types> --session {session}; "
               f"init/register and validate documents with the same session. "
               f"Configured sources: {json.dumps(policy['templates'])}. "
               "Do not invent content, approvals or executed test results.")
    if event == "SessionStart":
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}
    if event == "UserPromptSubmit":
        kinds = requested_types(payload["prompt"])
        if not kinds:
            return None
        request(workspace, session, kinds)
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}
    raise ValueError(f"unsupported template hook event: {event}")


def main() -> None:
    """Handle one Frontier HVE lifecycle payload from stdin."""
    payload: Payload = json.load(sys.stdin)
    output = handle(payload, Path.cwd())
    if output:
        print(json.dumps(output))


if __name__ == "__main__":
    main()