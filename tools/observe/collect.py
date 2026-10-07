"""Collect each finished benchmark session's output into .hve/outputs/<mode>/<session_id>/ and write .hve/runs/<session_id>.run.json."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, TypedDict

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / ".hve" / "runs"
OUTPUTS_DIR = ROOT / ".hve" / "outputs"
PROMPT_FILE = ROOT / "tests" / "prompts" / "color-palette.md"
STOP_EVENTS = ("Stop", "SubagentStop")
SKIP_DIRS = {"node_modules", ".next", ".git", ".worktrees"}
FILE_BLOCK = re.compile(r"^[ \t#*`]*(?P<path>[\w./-]+\.\w+)[ \t*`:]*\n```[^\n]*\n(?P<code>.*?)\n```", re.MULTILINE | re.DOTALL)
PASTED_ATTACHMENT = re.compile(r"^#attachment:Pasted text #\d+$")
TERMINAL_NOTIFICATION = re.compile(r"^\[Terminal [\w-]+ notification: ")

Json = dict[str, Any]


class RunManifest(TypedDict):
    """One .hve/runs/<session_id>.run.json."""

    session_id: str
    mode: str
    prompt_file: str
    prompt_sha256: str
    started: str
    ended: str
    output_dir: str
    files: list[str]


def read_jsonl(path: Path) -> list[Json]:
    """Return the records of a JSONL file."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def normalize(text: str) -> str:
    """Return text with unified newlines and no surrounding whitespace."""
    return text.replace("\r\n", "\n").strip()


def chat_variable_values(store: Path) -> set[str]:
    """Return the values of all chat variables (attachments) recorded in a VS Code chat session store."""
    values: set[str] = set()
    stack: list[Any] = read_jsonl(store)
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if isinstance(node.get("variableData"), dict):
                values |= {v["value"] for v in node["variableData"]["variables"] if isinstance(v.get("value"), str)}
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return values


def sent_prompt(message: str, transcript_path: Path) -> str:
    """Return the text the user sent: the message itself, or the pasted-text attachment it consists of (D-019)."""
    if not PASTED_ATTACHMENT.match(message.strip()):
        return message
    store = transcript_path.parents[2] / "chatSessions" / f"{transcript_path.stem}.jsonl"
    values = chat_variable_values(store)
    if len(values) != 1:
        raise ValueError(f"{store} holds {len(values)} attachment values; expected exactly the one pasted prompt")
    return values.pop()


def write_reply_files(reply: str, out: Path) -> list[str]:
    """Write each path-labelled code block of a reply under out and return the relative paths."""
    files: list[str] = []
    for block in FILE_BLOCK.finditer(reply):
        rel = Path(block["path"])
        target = (out / rel).resolve()
        if rel.is_absolute() or not target.is_relative_to(out.resolve()):
            raise ValueError(f"unsafe file path {block['path']!r} in the reply written to {out}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(block["code"] + "\n", encoding="utf-8")
        files.append(rel.as_posix())
    return files


def list_files(out: Path) -> list[str]:
    """Return the relative paths of all files under out, excluding dependency and build folders."""
    files: list[str] = []
    for folder, dirs, names in os.walk(out):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        files += [(Path(folder) / name).relative_to(out).as_posix() for name in names]
    return sorted(files)


def collect(events_path: Path, prompt: str) -> RunManifest:
    """Move or extract one finished session's output into .hve/outputs/<mode>/<session_id>/ and return its manifest."""
    session_id = events_path.name.removesuffix(".events.jsonl")
    events = read_jsonl(events_path)
    stops = [e for e in events if e["event"] in STOP_EVENTS]
    if not stops:
        raise LookupError(f"{events_path.name} has no Stop event: the session has not finished")
    mode = events[0]["mode"]
    transcript_path = Path(stops[-1]["transcript_path"])
    transcript = read_jsonl(transcript_path)
    messages = [r["data"]["content"] for r in transcript
                if r["type"] == "user.message" and not TERMINAL_NOTIFICATION.match(r["data"]["content"])]  # Copilot injects these
    if len(messages) != 1 or normalize(sent_prompt(messages[0], transcript_path)) != normalize(prompt):
        raise ValueError(f"session {session_id} is not a benchmark run: it needs exactly one user message equal to {PROMPT_FILE.name}; "
                         "move its .events.jsonl and .jsonl to .hve/runs/smoke/ or .hve/runs/invalid/")
    out = OUTPUTS_DIR / mode / session_id
    if mode == "minimal":
        reply = "\n\n".join(r["data"]["content"] for r in transcript if r["type"] == "assistant.message" and r["data"]["content"])
        out.mkdir(parents=True)
        (out / "response.md").write_text(reply + "\n", encoding="utf-8")
        files = write_reply_files(reply, out)
    else:
        current = OUTPUTS_DIR / mode / "current"
        if not current.is_dir():
            raise FileNotFoundError(f"{current} missing: the {mode} agent wrote no output there")
        try:
            current.rename(out)
        except PermissionError as locked:
            raise PermissionError(f"cannot move {current}: a process still uses it, usually a terminal the agent left open there. Close that "
                                  "terminal in VS Code's terminal panel (or end its node/npm process), then run `python tools/observe/collect.py`") from locked
        files = list_files(out)
    return RunManifest(session_id=session_id, mode=mode, prompt_file=PROMPT_FILE.relative_to(ROOT).as_posix(),
                       prompt_sha256=hashlib.sha256(PROMPT_FILE.read_bytes()).hexdigest(),
                       started=transcript[0]["timestamp"], ended=transcript[-1]["timestamp"],
                       output_dir=out.relative_to(ROOT).as_posix(), files=files)


def main() -> None:
    """Collect every session in .hve/runs/ that has no run manifest yet."""
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    pending = [p for p in sorted(RUNS_DIR.glob("*.events.jsonl"))
               if not (RUNS_DIR / p.name.replace(".events.jsonl", ".run.json")).exists()]
    modes = [read_jsonl(p)[0]["mode"] for p in pending]
    repeated = sorted({m for m in modes if modes.count(m) > 1})
    if repeated:
        raise RuntimeError(f"more than one uncollected session for mode(s) {repeated}: run collect after every run so "
                           ".hve/outputs/<mode>/current/ belongs to exactly one session")
    for path in pending:
        manifest = collect(path, prompt)
        (RUNS_DIR / f"{manifest['session_id']}.run.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"collected {manifest['session_id']} ({manifest['mode']}): {len(manifest['files'])} files -> {manifest['output_dir']}")


if __name__ == "__main__":
    main()
