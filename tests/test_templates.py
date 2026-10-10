"""Regression cases for configured deliverables, path safety and session guards."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools" / "templates"))
sys.path.insert(0, str(REPO / "hooks"))
import manage  # noqa: E402
import template_guard  # noqa: E402


def fails(error: type[Exception], action: Callable[[], object]) -> None:
    """Require the action to raise the specified error."""
    try:
        action()
    except error:
        return
    raise AssertionError(f"expected {error.__name__}")


def fill(path: Path) -> None:
    """Replace fixture placeholders with explicit fixture-only content."""
    text = path.read_text(encoding="utf-8")
    path.write_text(manage.PLACEHOLDER.sub("Fixture content, not actual approval or test evidence.", text), encoding="utf-8")


def policy(workspace: Path) -> manage.Config:
    """Write and return a mutable copy of the bundled policy."""
    data = manage.configuration(workspace)
    (workspace / manage.CONFIG_NAME).write_text(json.dumps(data), encoding="utf-8")
    return data


def test_bundled_documents_and_no_overwrite() -> None:
    """All defaults initialize, reject empty content, validate and refuse replacement."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        manage.request(workspace, "s1", list(manage.KINDS))
        assert len(manage.check_session(workspace, "s1")) == 3
        for kind in manage.KINDS:
            path = manage.initialize(workspace, kind, "sample", "s1")
            assert any("unresolved" in error for error in manage.validate(workspace, kind, "sample"))
            original = path.read_bytes()
            fails(FileExistsError, lambda: manage.initialize(workspace, kind, "sample", "s1"))
            assert path.read_bytes() == original
            fill(path)
            path.write_text(path.read_text(encoding="utf-8") + "\n```yaml\nref: ${{ github.ref }}\nvalue: {{ .Values.x }}\n```\n", encoding="utf-8")
            assert manage.validate(workspace, kind, "sample") == []
            manage.register(workspace, kind, "sample", "s2")
        assert manage.check_session(workspace, "s1") == []
        assert manage.check_session(workspace, "s2") == []


def test_custom_template_and_provenance() -> None:
    """Custom CRLF templates resolve and drift or broken sources fail explicitly."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        data = policy(workspace)
        source = workspace / "company-prd.md"
        source.write_bytes(b"<!-- hve-template: prd@2 -->\r\n# Company PRD\r\n<!-- hve-section: purpose -->\r\n## Purpose\r\n{{FILL: purpose}}\r\n")
        data["templates"]["prd"] = {"source": "company-prd.md", "output": "specs/{slug}-requirements.md"}
        (workspace / manage.CONFIG_NAME).write_text(json.dumps(data), encoding="utf-8")
        path = manage.initialize(workspace, "prd", "custom", "s1")
        assert path == workspace.resolve() / "specs" / "custom-requirements.md"
        fill(path)
        assert manage.validate(workspace, "prd", "custom") == []
        source.write_text(source.read_text(encoding="utf-8") + "\nChanged instructions.\n", encoding="utf-8")
        assert any("provenance" in error for error in manage.validate(workspace, "prd", "custom"))
        source.unlink()
        fails(FileNotFoundError, lambda: manage.resolve(workspace, "prd"))


def test_structure_and_registration_failures() -> None:
    """Removed, duplicated, reordered or empty sections fail, including registration."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        path = manage.initialize(workspace, "prd", "sample", "s1")
        fill(path)
        valid = path.read_text(encoding="utf-8")
        variants = [
            valid.replace("<!-- hve-section: users -->", ""),
            valid.replace("<!-- hve-section: users -->", "<!-- hve-section: goals -->"),
            valid.replace("<!-- hve-section: users -->", "<!-- hve-section: swap -->")
                 .replace("<!-- hve-section: goals -->", "<!-- hve-section: users -->")
                 .replace("<!-- hve-section: swap -->", "<!-- hve-section: goals -->"),
            valid.replace("## Context and Evidence\nFixture content, not actual approval or test evidence.", "## Context and Evidence"),
            valid.replace('"sha256": "', '"sha256": "changed-'),
        ]
        for text in variants:
            path.write_text(text, encoding="utf-8")
            assert manage.validate(workspace, "prd", "sample")
            fails(ValueError, lambda: manage.register(workspace, "prd", "sample", "s2"))


def test_invalid_policy_and_paths() -> None:
    """Malformed config, unsafe sources/outputs, invalid identities and slugs fail."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        data = manage.configuration(workspace)
        config = workspace / manage.CONFIG_NAME
        for invalid in ([], {}, {**data, "version": True}, {**data, "enforce": "true"}, {**data, "extra": 1}):
            config.write_text(json.dumps(invalid), encoding="utf-8")
            fails(ValueError, lambda: manage.configuration(workspace))
        config.write_text(json.dumps(data), encoding="utf-8")
        for unsafe in ("../outside.md", "/outside.md", "C:/outside.md", "folder\\outside.md", ".git/config", ".hve/config", "./prd.md",
                   ".GIT/config", ".HVE/state", ".git./review.md", "docs /sample.md", "docs./sample.md"):
            fails(ValueError, lambda: manage.safe_path(workspace, unsafe))
        for output in ("../{slug}.md", "out.md", "{slug}-{slug}.md", "{other}.md", "{slug}.json"):
            broken = json.loads(json.dumps(data))
            broken["templates"]["prd"]["output"] = output
            config.write_text(json.dumps(broken), encoding="utf-8")
            fails(ValueError, lambda: manage.configuration(workspace))
        config.write_text(json.dumps(data), encoding="utf-8")
        for slug in ("../bad", "MixedCase", "bad_name", "a" * 81):
            fails(ValueError, lambda: manage.initialize(workspace, "prd", slug, "s1"))
        fails(ValueError, lambda: manage.state_path(workspace, "../session"))
        source = workspace / "bad.md"
        source.write_text("<!-- hve-template: prd@1 -->\n# No section markers\n", encoding="utf-8")
        data["templates"]["prd"]["source"] = "bad.md"
        config.write_text(json.dumps(data), encoding="utf-8")
        fails(ValueError, lambda: manage.resolve(workspace, "prd"))


def test_registry_lock_and_all_documents_checked() -> None:
    """A busy update fails explicitly and every successfully registered output is checked."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        manage.request(workspace, "s1", ["prd"])
        lock = manage.state_path(workspace, "s1").with_suffix(".json.lock")
        lock.write_text("busy", encoding="utf-8")
        fails(FileExistsError, lambda: manage.initialize(workspace, "prd", "blocked", "s1"))
        assert not (workspace / "docs" / "product" / "PRD-blocked.md").exists()
        lock.unlink()
        first = manage.initialize(workspace, "prd", "first", "s1")
        second = manage.initialize(workspace, "prd", "second", "s1")
        fill(first)
        fill(second)
        assert len(manage.load_state(workspace, "s1")["documents"]) == 2
        assert manage.check_session(workspace, "s1") == []
        second.unlink()
        assert any("PRD-second.md" in error for error in manage.check_session(workspace, "s1"))


def test_validation_errors_produce_stop_decisions() -> None:
    """Malformed provenance and missing configured sources cannot escape the Stop gate."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        path = manage.initialize(workspace, "prd", "sample", "s1")
        fill(path)
        text = path.read_text(encoding="utf-8")
        path.write_text(manage.METADATA.sub("<!-- hve-document: invalid-json -->", text), encoding="utf-8")
        stop: template_guard.Payload = {"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": False}
        result = template_guard.handle(stop, workspace)
        assert result and result["hookSpecificOutput"]["decision"] == "block"
        assert "validation error" in json.dumps(result)
        repeated = template_guard.handle({**stop, "stop_hook_active": True}, workspace)
        assert repeated and "validation error" in repeated["systemMessage"]
        data = policy(workspace)
        data["templates"]["prd"]["source"] = "missing.md"
        (workspace / manage.CONFIG_NAME).write_text(json.dumps(data), encoding="utf-8")
        result = template_guard.handle(stop, workspace)
        assert result and "missing.md" in json.dumps(result)
        (workspace / manage.CONFIG_NAME).write_text("{}", encoding="utf-8")
        result = template_guard.handle(stop, workspace)
        assert result and result["hookSpecificOutput"]["decision"] == "block"


def test_prompt_detection_and_stop_guard() -> None:
    """Authoring registers expected outputs; unrelated prompts do not block stopping."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        for prompt in ("Explain what a PRD is", "Do not create a PRD", "Provide a summary of the PRD",
                       "Implement the login feature from the PRD and update the tests", "Do we need a test strategy?",
                       "Write the code, no PRD needed", "don\u2019t write a PRD", "Write code to compute TDS on salaries",
                       "How do I write a PRD?", "Explain how to write a test strategy",
                       "Create a PRD template for our company", "Update the PRD template to add a compliance section",
                       "Generate PRD-based test cases", "Create a TDS calculator for payroll",
                       "Create a test strategy template"):
            assert template_guard.requested_types(prompt) == [], prompt
        assert template_guard.requested_types("Create these:\nPRD\nTechnical Design Specification\nTest Strategy") == list(manage.KINDS)
        assert template_guard.requested_types("Write a PRD; prepare technical design specification; draft a test strategy.") == list(manage.KINDS)
        assert template_guard.requested_types("Could you please write a PRD?") == ["prd"]
        assert template_guard.requested_types("Create a new PRD document for payroll") == ["prd"]
        start = template_guard.handle({"hook_event_name": "SessionStart", "session_id": "s1"}, workspace)
        assert start and "session s1" in json.dumps(start)
        stop: template_guard.Payload = {"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": False}
        assert template_guard.handle(stop, workspace) is None
        template_guard.handle({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "Create a PRD"}, workspace)
        blocked = template_guard.handle(stop, workspace)
        assert blocked and blocked["hookSpecificOutput"]["decision"] == "block"
        repeated = template_guard.handle({**stop, "stop_hook_active": True}, workspace)
        assert repeated and "systemMessage" in repeated
        path = manage.initialize(workspace, "prd", "sample", "s1")
        fill(path)
        assert template_guard.handle(stop, workspace) is None
        path.unlink()
        assert template_guard.handle(stop, workspace)
        data = policy(workspace)
        data["enforce"] = False
        (workspace / manage.CONFIG_NAME).write_text(json.dumps(data), encoding="utf-8")
        assert template_guard.handle(stop, workspace) is None


def test_cli_exit_codes() -> None:
    """CLI initialization and configuration succeed, while an incomplete document fails."""
    with tempfile.TemporaryDirectory() as tmp:
        base = [sys.executable, str(REPO / "tools" / "templates" / "manage.py"), "--workspace", tmp]
        for args in (["configure"], ["init", "prd", "--slug", "sample", "--session", "s1"]):
            result = subprocess.run([*base, *args], capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
        result = subprocess.run([*base, "check", "--session", "s1"], capture_output=True, text=True)
        assert result.returncode == 1 and json.loads(result.stdout)["valid"] is False


if __name__ == "__main__":
    test_bundled_documents_and_no_overwrite()
    test_custom_template_and_provenance()
    test_structure_and_registration_failures()
    test_invalid_policy_and_paths()
    test_registry_lock_and_all_documents_checked()
    test_validation_errors_produce_stop_decisions()
    test_prompt_detection_and_stop_guard()
    test_cli_exit_codes()
    print("test_templates: OK")