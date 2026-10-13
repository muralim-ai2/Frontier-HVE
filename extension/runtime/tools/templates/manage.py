"""Resolve, initialize and validate configured Frontier HVE deliverables."""

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[2]
BUNDLED = ROOT / "templates" / "deliverables"
CONFIG_NAME = "frontier-hve.templates.json"
KINDS = ("prd", "technicalDesign", "testStrategy")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SESSION = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
IDENTITY = re.compile(r"^<!-- hve-template: ([\w-]+)@([1-9]\d*) -->$", re.M)
SECTION = re.compile(r"^<!-- hve-section: ([a-z0-9-]+) -->$", re.M)
METADATA = re.compile(r"^<!-- hve-document: (.+) -->$", re.M)
PLACEHOLDER = re.compile(r"\{\{\s*FILL:[^{}]*\}\}")


def linked(path: Path) -> bool:
    """Identify symbolic links and Windows reparse points."""
    return path.is_symlink() or (os.name == "nt" and path.exists()
                                and bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT))


class Entry(TypedDict):
    """A template source and its workspace-relative output pattern."""

    source: str
    output: str


class Config(TypedDict):
    """The versioned workspace template policy."""

    version: int
    enforce: bool
    templates: dict[str, Entry]


class Document(TypedDict):
    """A session's registered deliverable identity."""

    kind: str
    slug: str


class State(TypedDict):
    """Requested types and initialized documents in one session."""

    requested: list[str]
    documents: list[Document]


def safe_path(workspace: Path, value: str) -> Path:
    """Return a contained, non-state path without traversal or links."""
    if (not value or "\\" in value or ":" in value or Path(value).is_absolute()
             or any(part.lower() in ("", ".", "..", ".git", ".hve", ".harness")
                 or part.endswith((".", " "))
                   for part in value.split("/"))):
        raise ValueError(f"unsafe workspace path: {value!r}")
    current = workspace.resolve()
    for part in value.split("/"):
        current /= part
        if linked(current):
            raise ValueError(f"linked workspace path: {current}")
    if not current.resolve().is_relative_to(workspace.resolve()):
        raise ValueError(f"path leaves workspace: {value}")
    return current


def configuration(workspace: Path) -> Config:
    """Read workspace policy or the explicitly bundled default policy."""
    config_path = safe_path(workspace, CONFIG_NAME)
    if not config_path.exists():
        config_path = BUNDLED / "catalog.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or set(data) != {"version", "enforce", "templates"}
            or type(data["version"]) is not int or data["version"] != 1
            or type(data["enforce"]) is not bool
            or not isinstance(data["templates"], dict)
            or set(data["templates"]) != set(KINDS)):
        raise ValueError(f"invalid template policy: {config_path}")
    for kind, entry in data["templates"].items():
        if (not isinstance(entry, dict) or set(entry) != {"source", "output"}
                or not all(isinstance(value, str) and value for value in entry.values())):
            raise ValueError(f"invalid template entry: {kind}")
        pattern = entry["output"]
        if pattern.count("{slug}") != 1 or "{" in pattern.replace("{slug}", "") or "}" in pattern.replace("{slug}", ""):
            raise ValueError(f"output must contain exactly one {{slug}}: {kind}")
        if not pattern.endswith(".md"):
            raise ValueError(f"output must be Markdown: {kind}")
        safe_path(workspace, pattern.replace("{slug}", "example"))
    return data


def resolve(workspace: Path, kind: str) -> tuple[Entry, str, str]:
    """Return the entry, template text and exact-byte SHA-256 digest."""
    entry = configuration(workspace)["templates"][kind]
    source = entry["source"]
    builtin = {"prd": "prd", "technicalDesign": "technical-design", "testStrategy": "test-strategy"}[kind]
    if source.startswith("builtin:"):
        if source != f"builtin:{builtin}@1":
            raise ValueError(f"unknown bundled template: {source}")
        template = BUNDLED / f"{builtin}-v1.md"
    else:
        template = safe_path(workspace, source)
    raw = template.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    identities = IDENTITY.findall(text)
    sections = SECTION.findall(text)
    if (len(identities) != 1 or identities[0][0] != kind or not sections
            or len(set(sections)) != len(sections) or METADATA.search(text)):
        raise ValueError(f"invalid template identity or section markers: {template}")
    return entry, text, hashlib.sha256(raw).hexdigest()


def output_path(workspace: Path, entry: Entry, slug: str) -> Path:
    """Return the configured document path for a validated slug."""
    if not SLUG.fullmatch(slug) or len(slug) > 80:
        raise ValueError("slug must be 1-80 lowercase letters/digits separated by hyphens")
    return safe_path(workspace, entry["output"].replace("{slug}", slug))


def state_path(workspace: Path, session: str) -> Path:
    """Return the session registry path without following linked state directories."""
    if not SESSION.fullmatch(session):
        raise ValueError("unsafe session id")
    current = workspace.resolve()
    for part in (".hve", "deliverables", f"{session}.json"):
        current /= part
        if linked(current):
            raise ValueError(f"linked session state: {current}")
    return current


def load_state(workspace: Path, session: str) -> State:
    """Read a session registry or return an explicitly empty new registry."""
    path = state_path(workspace, session)
    if not path.exists():
        return State(requested=[], documents=[])
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or set(data) != {"requested", "documents"}
            or not isinstance(data["requested"], list)
            or any(kind not in KINDS for kind in data["requested"])
            or not isinstance(data["documents"], list)
            or any(not isinstance(doc, dict) or set(doc) != {"kind", "slug"}
                   or doc["kind"] not in KINDS or not isinstance(doc["slug"], str)
                   for doc in data["documents"])):
        raise ValueError(f"invalid session registry: {path}")
    return data


def save_state(workspace: Path, session: str, state: State) -> None:
    """Publish a complete session registry atomically under its update lock."""
    path = state_path(workspace, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("x", encoding="utf-8") as output:
        output.write(json.dumps(state, indent=2) + "\n")
    temporary.replace(path)


def update_state(workspace: Path, session: str, kinds: list[str], document: Document | None = None) -> State:
    """Serialize registry updates or fail explicitly when another update holds the lock."""
    path = state_path(workspace, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".json.lock")
    handle = lock.open("x", encoding="utf-8")
    try:
        with handle:
            state = load_state(workspace, session)
            state["requested"] = sorted(set(state["requested"] + kinds))
            if document is not None and document not in state["documents"]:
                state["documents"].append(document)
            save_state(workspace, session, state)
            return state
    finally:
        lock.unlink()


def request(workspace: Path, session: str, kinds: list[str]) -> State:
    """Register required types after validating their configured templates."""
    for kind in kinds:
        if kind not in KINDS:
            raise ValueError(f"unknown deliverable type: {kind}")
        resolve(workspace, kind)
    return update_state(workspace, session, kinds)


def initialize(workspace: Path, kind: str, slug: str, session: str) -> Path:
    """Create a document exclusively and register it for session validation."""
    entry, text, digest = resolve(workspace, kind)
    path = output_path(workspace, entry, slug)
    request(workspace, session, [kind])
    metadata = {"kind": kind, "slug": slug, "source": entry["source"], "sha256": digest}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as document:
        document.write(f"<!-- hve-document: {json.dumps(metadata, sort_keys=True)} -->\n" + text)
    update_state(workspace, session, [kind], Document(kind=kind, slug=slug))
    return path


def register(workspace: Path, kind: str, slug: str, session: str) -> Path:
    """Register an existing valid generated document without overwriting it."""
    errors = validate(workspace, kind, slug)
    if errors:
        raise ValueError("; ".join(errors))
    request(workspace, session, [kind])
    update_state(workspace, session, [kind], Document(kind=kind, slug=slug))
    return output_path(workspace, configuration(workspace)["templates"][kind], slug)


def validate(workspace: Path, kind: str, slug: str) -> list[str]:
    """Return structural, provenance and placeholder errors for a document."""
    entry, template, digest = resolve(workspace, kind)
    path = output_path(workspace, entry, slug)
    if not path.is_file():
        return [f"missing document: {path}"]
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    metadata = METADATA.findall(text)
    expected = {"kind": kind, "slug": slug, "source": entry["source"], "sha256": digest}
    if len(metadata) != 1 or json.loads(metadata[0]) != expected:
        errors.append(f"template provenance changed or missing: {path}")
    if IDENTITY.findall(text) != IDENTITY.findall(template):
        errors.append(f"template identity changed: {path}")
    sections = SECTION.findall(template)
    if SECTION.findall(text) != sections:
        errors.append(f"required sections missing, duplicated or reordered: {path}")
    if PLACEHOLDER.search(text):
        errors.append(f"unresolved template placeholders: {path}")
    for match in SECTION.finditer(text):
        end = SECTION.search(text, match.end())
        body = text[match.end():end.start() if end else len(text)]
        content = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        content = "\n".join(line for line in content.splitlines() if not line.lstrip().startswith("#"))
        if not content.strip():
            errors.append(f"empty section {match[1]}: {path}")
    return errors


def check_session(workspace: Path, session: str) -> list[str]:
    """Validate every requested type and initialized document in a session."""
    state = load_state(workspace, session)
    errors = [f"no initialized {kind} document for session {session}"
              for kind in state["requested"] if not any(doc["kind"] == kind for doc in state["documents"])]
    for document in state["documents"]:
        errors.extend(validate(workspace, document["kind"], document["slug"]))
    return errors


def main() -> None:
    """Run the template configuration, initialization or validation command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("configure")
    for command in ("resolve", "init", "register", "validate"):
        sub = commands.add_parser(command)
        sub.add_argument("kind", choices=KINDS)
        if command != "resolve":
            sub.add_argument("--slug", required=True)
        if command in ("init", "register"):
            sub.add_argument("--session", required=True)
    sub = commands.add_parser("request")
    sub.add_argument("kinds", nargs="+", choices=KINDS)
    sub.add_argument("--session", required=True)
    sub = commands.add_parser("check")
    sub.add_argument("--session", required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    errors: list[str] = []
    if args.command == "configure":
        path = safe_path(workspace, CONFIG_NAME)
        with path.open("x", encoding="utf-8") as config:
            config.write((BUNDLED / "catalog.json").read_text(encoding="utf-8"))
        result: object = {"config": str(path)}
    elif args.command == "resolve":
        entry, text, digest = resolve(workspace, args.kind)
        result = {**entry, "sha256": digest, "sections": SECTION.findall(text)}
    elif args.command == "request":
        result = request(workspace, args.session, args.kinds)
    elif args.command == "init":
        result = {"document": str(initialize(workspace, args.kind, args.slug, args.session))}
    elif args.command == "register":
        result = {"document": str(register(workspace, args.kind, args.slug, args.session))}
    else:
        errors = check_session(workspace, args.session) if args.command == "check" else validate(workspace, args.kind, args.slug)
        result = {"valid": not errors, "errors": errors}
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()