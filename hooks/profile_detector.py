"""Hook that learns typed user preferences from prompts into user_profile.json and applies them at session start."""

import json
import os
import re
import sys
from typing import Literal, TypedDict

from hve_paths import PROFILE_FILE

CHARS_PER_TOKEN = 4
OVER_SPEC_TOKENS = 500

BloatTrigger = Literal["md_state_files", "infinite_loop", "agent_swarm", "skip_verification"]
TechnicalLevel = Literal["executive", "partial", "developer"]


class Profile(TypedDict):
    """Persistent user preferences stored in user_profile.json."""

    prompt_style: Literal["simple", "over_specifier"] | None
    wants_evidence: Literal[True] | None
    verbosity: Literal["concise"] | None
    output_format: Literal["tables", "prose", "code"] | None
    technical_level: TechnicalLevel | None
    bloat_triggers: list[BloatTrigger]


ALLOWED: dict[str, tuple[object, ...]] = {
    "prompt_style": (None, "simple", "over_specifier"),
    "wants_evidence": (None, True),
    "verbosity": (None, "concise"),
    "output_format": (None, "tables", "prose", "code"),
    "technical_level": (None, "executive", "partial", "developer"),
}
ROLE = r"\b(?:i'?m|i am|as)\s+(?:an?\s+|the\s+)?(?:senior\s+|staff\s+|principal\s+|lead\s+)?"
LEVELS: dict[TechnicalLevel, re.Pattern[str]] = {
    "executive": re.compile(ROLE + r"(?:ceo|cto|cio|cfo|coo|vp|vice president|director|executive|business (?:owner|leader))\b"
                            r"|\bnon-?technical\b|\bnot (?:very )?technical\b", re.I),
    "partial": re.compile(ROLE + r"(?:tpm|technical program manager|program manager|product manager|product owner|"
                          r"solution architect|architect|business analyst)\b|\bpartially technical\b", re.I),
    "developer": re.compile(ROLE + r"(?:developer|software engineer|engineer|programmer|data scientist|ml engineer|ai engineer)\b", re.I),
}
LEVEL_CONTEXT: dict[TechnicalLevel, str] = {
    "executive": ("Technical level: executive (non-technical). Explain in business terms with the explain-walkthrough skill, avoid jargon, "
                  "and recommend the right experts (UI/UX, backend, full-stack, data scientist, AI engineer, solution architect, DevOps) "
                  "before moving from prototype to production."),
    "partial": ("Technical level: partially technical (for example TPM or architect). Explain new concepts briefly with the "
                "explain-walkthrough skill and recommend experts before production infrastructure."),
    "developer": "Technical level: developer. Skip basic explanations.",
}
EVIDENCE = re.compile(r"\b(with evidence|cite (your )?sources?|show me (the )?proof|with citations)\b", re.I)
CONCISE = re.compile(r"\b(in (under )?\d+ words|keep it (short|brief)|be (brief|concise)|briefly)\b", re.I)
FORMATS = {
    "tables": re.compile(r"\b(as|in) a table\b|\bin tables\b", re.I),
    "prose": re.compile(r"\bin prose\b", re.I),
    "code": re.compile(r"\b(just|only) (the )?code\b", re.I),
}
BLOAT: dict[BloatTrigger, re.Pattern[str]] = {
    "md_state_files": re.compile(r"(\bmarkdown\b|\.md\b)[^.\n]{0,60}\b(track|state|progress|status)|\b(track|state|progress|status)\b[^.\n]{0,60}(\bmarkdown\b|\.md\b)", re.I),
    "infinite_loop": re.compile(r"keep going until|until (it'?s )?(all )?done|loop (forever|until)|never stop", re.I),
    "agent_swarm": re.compile(r"\b([5-9]|[1-9]\d+|five|six|seven|eight|nine|ten)\s+(parallel\s+)?(sub-?)?agents\b", re.I),
    "skip_verification": re.compile(r"don'?t (stop to )?(check|verify|test)|skip (the )?(tests?|verification|checks?)|no need to (test|verify|check)", re.I),
}
CHALLENGES: dict[BloatTrigger, str] = {
    "md_state_files": "Markdown state files are re-read every turn and bloat context; JSON state (feature_list.json, user_profile.json) holds the same state in far fewer tokens.",
    "infinite_loop": "An open-ended loop grows history until context rot sets in and skips verification checkpoints; one feature at a time with verification in between is cheaper and catches errors early.",
    "agent_swarm": "Parallel agents cost about 15x the tokens of one agent on tightly coupled work; the harness caps sub-agents at 3, one role each, with minimal context.",
    "skip_verification": "Skipping verification lets 'looks done but is broken' work through; each feature is verified before it is marked done.",
}


def load_profile() -> Profile:
    """Return user_profile.json after checking every field against its allowed values."""
    data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    if set(data) != set(ALLOWED) | {"bloat_triggers"}:
        raise ValueError(f"{PROFILE_FILE} fields {sorted(data)} differ from {sorted(set(ALLOWED) | {'bloat_triggers'})}")
    for key, allowed in ALLOWED.items():
        if data[key] not in allowed:
            raise ValueError(f"{PROFILE_FILE} {key}={data[key]!r}, expected one of {allowed}")
    if not set(data["bloat_triggers"]) <= set(BLOAT):
        raise ValueError(f"{PROFILE_FILE} bloat_triggers {data['bloat_triggers']} not all in {sorted(BLOAT)}")
    return data  # type: ignore[return-value]


def save_profile(profile: Profile) -> None:
    """Atomically write the profile to user_profile.json."""
    tmp = PROFILE_FILE.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, PROFILE_FILE)


def detect(prompt: str, profile: Profile) -> tuple[Profile, list[BloatTrigger]]:
    """Return the profile updated from one prompt and the bloat triggers the prompt contains."""
    updated = Profile(**profile)
    updated["prompt_style"] = "over_specifier" if len(prompt) / CHARS_PER_TOKEN > OVER_SPEC_TOKENS else "simple"
    if EVIDENCE.search(prompt):
        updated["wants_evidence"] = True
    if CONCISE.search(prompt):
        updated["verbosity"] = "concise"
    for output_format, pattern in FORMATS.items():
        if pattern.search(prompt):
            updated["output_format"] = output_format  # type: ignore[typeddict-item]
    for level, pattern in LEVELS.items():
        if pattern.search(prompt):
            updated["technical_level"] = level
    triggers = [trigger for trigger, pattern in BLOAT.items() if pattern.search(prompt)]
    updated["bloat_triggers"] = sorted(set(profile["bloat_triggers"]) | set(triggers))
    return updated, triggers


def session_context(profile: Profile) -> str:
    """Return the instructions a session starts with for this profile, or '' when nothing is known."""
    lines: list[str] = []
    if profile["prompt_style"] == "over_specifier":
        lines.append("The user writes long specs: extract every requirement into a checklist and work through it feature by feature.")
    if profile["wants_evidence"]:
        lines.append("Back every claim with evidence: file paths with line numbers, command output with exit codes, or sources.")
    if profile["verbosity"] == "concise":
        lines.append("Keep replies short.")
    if profile["output_format"]:
        lines.append(f"Prefer {profile['output_format']} in replies.")
    if profile["technical_level"]:
        lines.append(LEVEL_CONTEXT[profile["technical_level"]])
    if profile["bloat_triggers"]:
        lines.append(f"The user has asked for token-wasteful patterns before ({', '.join(profile['bloat_triggers'])}): "
                     "challenge them with the token-cost reason and the better alternative instead of complying.")
    return "User profile (user_profile.json):\n- " + "\n- ".join(lines) if lines else ""


def main() -> None:
    """Handle SessionStart (apply the profile) and UserPromptSubmit (update it and challenge bloat)."""
    payload = json.load(sys.stdin)
    event = payload["hook_event_name"]
    profile = load_profile()
    if event == "SessionStart":
        context = session_context(profile)
        if context:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))
    elif event == "UserPromptSubmit":
        updated, triggers = detect(payload["prompt"], profile)
        save_profile(updated)
        if triggers:
            print(json.dumps({"systemMessage": "Harness challenge: " + " ".join(CHALLENGES[t] for t in triggers)}))
    else:
        raise ValueError(f"profile_detector.py does not handle hook event {event!r}")


if __name__ == "__main__":
    main()
