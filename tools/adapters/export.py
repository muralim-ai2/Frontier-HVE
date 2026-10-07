"""Export the Frontier HVE agents, skills and guard hooks to Claude Code, Cursor or Codex, and an Azure DevOps MCP server to any client."""

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, TypedDict

ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT.parent
RUNTIME_PATH = ".hve/runtime"
COMPAT = f"{RUNTIME_PATH}/hooks/agent_compat.py"
AGENTS = {"hve-creator": "hve-creator.agent.md", "hve-single": "hve-single.agent.md", "hve-azure-devops": "hve-azure-devops.agent.md"}
SKIP_SKILLS = {"pr-push", "export-harness"}
SKILL_DIRS = {"claude": ".claude/skills", "cursor": ".cursor/skills", "codex": ".agents/skills"}
CURSOR_EVENTS = {"SessionStart": "sessionStart", "UserPromptSubmit": "beforeSubmitPrompt", "PreToolUse": "preToolUse",
                 "PostToolUse": "postToolUse", "Stop": "stop"}
ADO_DOMAINS = ["core", "work", "work-items", "repositories", "pipelines"]
ORGANIZATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,49}$")
HOOK_COMMAND = re.compile(r"""^ {6}command: 'python "\{\{RUNTIME\}\}/([\w./-]+\.py)"((?: [\w-]+)*)'$""")
EMPTY_PROFILE = {"prompt_style": None, "wants_evidence": None, "verbosity": None, "output_format": None, "build_preference": None,
                 "depth_evidence": 0, "explanation_depth": None, "bloat_triggers": []}
INVOKE = {
    "claude": "claude --agent hve-creator (or hve-single, hve-azure-devops); accept the workspace trust prompt so the agent's hooks run",
    "cursor": "type /hve-creator in Agent chat, or Alt+Enter on it to keep it as a Custom Mode for the session",
    "codex": "type $hve-creator; start codex from the project root and trust the hooks once with /hooks",
    "vscode": "start the ado server in the MCP view, sign in, then pick HVE azure-devops in the Chat view",
}
GAPS = {
    "claude": ["pr-push is not exported (it needs the VS Code GitHub Pull Requests extension)",
               "AskUserQuestion answers are mapped from question text to header; labels containing commas split wrongly"],
    "cursor": ["hooks in .cursor/hooks.json apply to every agent in this project, not only hve-creator",
               "Cursor has no context channel on prompt submit or before a tool: the skill loadout notice and harness challenges do not "
               "reach the model; guards (deny), module-size feedback, victory check and session profile do",
               "the sub-agent context hook (SubagentStart) is not exported: Cursor's subagentStart only allows or denies",
               "pr-push is not exported"],
    "codex": ["hooks in .codex/hooks.json apply to every session in this project, not only $hve-creator",
              "Codex runs project hooks only after /hooks trust, and with the session directory as working directory",
              "Codex cannot stop the agent from PreToolUse: escalation stops are sent as denies", "pr-push is not exported"],
    "vscode": [],
}

Json = dict[str, Any]


class Hook(TypedDict):
    """One hook command of an agent template: runtime script, script arguments, environment and timeout in seconds."""

    script: str
    args: list[str]
    env: dict[str, str]
    timeout: int | None


class Agent(TypedDict):
    """An agent template split into its description, hooks per event and body with the runtime path filled in."""

    description: str
    hooks: dict[str, list[Hook]]
    body: str


def parse_agent(path: Path) -> Agent:
    """Return the description, hooks and body of a VS Code agent template."""
    _, front, body = path.read_text(encoding="utf-8").split("---\n", 2)
    description = re.search(r"^description: (.+)$", front, re.M)
    if not description:
        raise ValueError(f"{path} has no description")
    hooks: dict[str, list[Hook]] = {}
    event = ""
    for line in front.splitlines():
        if match := re.match(r"^  (\w+):$", line):
            event = match[1]
            hooks[event] = []
        elif match := HOOK_COMMAND.match(line):
            hooks[event].append(Hook(script=match[1], args=match[2].split(), env={}, timeout=None))
        elif match := re.match(r"^ {6}timeout: (\d+)$", line):
            hooks[event][-1]["timeout"] = int(match[1])
        elif match := re.match(r"^ {8}(\w+): (\S+)$", line):
            hooks[event][-1]["env"][match[1]] = match[2]
    return Agent(description=description[1], hooks=hooks, body=body.replace("{{RUNTIME}}", RUNTIME_PATH))


def compat_args(client: str, hook: Hook) -> list[str]:
    """Return the agent_compat.py arguments that run one hook for a client."""
    pairs = [f"{key}={value}" for key, value in hook["env"].items()]
    return [client, hook["script"], *pairs, *(["--", *hook["args"]] if hook["args"] else [])]


def frontmatter(fields: Json) -> str:
    """Return YAML frontmatter with JSON-quoted values (JSON is valid YAML)."""
    return "---\n" + "".join(f"{key}: {json.dumps(value)}\n" for key, value in fields.items()) + "---\n"


def claude_agent(name: str, agent: Agent) -> str:
    """Return a Claude Code subagent file whose frontmatter hooks run the harness hooks through agent_compat.py."""
    lines = ["---", f"name: {name}", f"description: {json.dumps(agent['description'])}"]
    if agent["hooks"]:
        lines.append("hooks:")
    for event, hooks in agent["hooks"].items():
        lines += [f"  {event}:", "    - hooks:"]
        for hook in hooks:
            args = [f"${{CLAUDE_PROJECT_DIR}}/{COMPAT}", *compat_args("claude", hook)]
            lines += ["        - type: command", "          command: python", f"          args: {json.dumps(args)}"]
            lines += [f"          timeout: {hook['timeout']}"] if hook["timeout"] else []
    return "\n".join([*lines, "---", ""]) + agent["body"]


def shell_command(client: str, hook: Hook) -> str:
    """Return the shell command that runs one hook through agent_compat.py from the project root."""
    return " ".join(["python", COMPAT, *compat_args(client, hook)])


def handler(client: str, hook: Hook) -> Json:
    """Return one command handler with its timeout, if the template sets one."""
    return {"command": shell_command(client, hook)} | ({"timeout": hook["timeout"]} if hook["timeout"] else {})


def hooks_file(client: str, agent: Agent) -> Json:
    """Return the project hooks file for Cursor (native format) or Codex (Claude-style format)."""
    if client == "cursor":
        return {"version": 1, "hooks": {CURSOR_EVENTS[event]: [handler(client, h) for h in hooks]
                                        for event, hooks in agent["hooks"].items() if event in CURSOR_EVENTS}}
    return {"hooks": {event: [{"hooks": [{"type": "command"} | handler(client, h) for h in hooks]}] for event, hooks in agent["hooks"].items()}}


def write_owned(path: Path, text: str) -> None:
    """Write a file Frontier HVE owns; refuse to overwrite one it did not write."""
    if path.exists() and "agent_compat.py" not in path.read_text(encoding="utf-8"):
        raise FileExistsError(f"{path} exists and was not written by Frontier HVE; merge its hooks by hand or move it away")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ado_server(organization: str, client: str) -> Json:
    """Return the stdio launch of Microsoft's Azure DevOps MCP server for an organization, limited to the harness domains."""
    args = ["-y", "@azure-devops/mcp", organization, "-d", *ADO_DOMAINS]
    if client == "vscode":
        return {"type": "stdio", "command": "npx", "args": args}
    return {"command": "cmd", "args": ["/c", "npx", *args]} if os.name == "nt" else {"command": "npx", "args": args}


def add_ado(workspace: Path, client: str, organization: str) -> Path:
    """Add the ado server to the client's project MCP configuration and return the file."""
    if not ORGANIZATION.match(organization):
        raise ValueError(f"{organization!r} is not an Azure DevOps organization name (letters, digits and hyphens)")
    if client == "codex":
        path = workspace / ".codex" / "config.toml"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if "[mcp_servers.ado]" not in text:
            server = ado_server(organization, client)
            path.parent.mkdir(exist_ok=True)
            path.write_text(text + f"\n[mcp_servers.ado]\ncommand = {json.dumps(server['command'])}\nargs = {json.dumps(server['args'])}\n",
                            encoding="utf-8")
        return path
    path, key = {"vscode": (workspace / ".vscode" / "mcp.json", "servers"), "claude": (workspace / ".mcp.json", "mcpServers"),
                 "cursor": (workspace / ".cursor" / "mcp.json", "mcpServers")}[client]
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault(key, {})["ado"] = ado_server(organization, client)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def copy_runtime(workspace: Path) -> None:
    """Copy the harness runtime into <workspace>/.hve/runtime and create the state the hooks read."""
    target = workspace / RUNTIME_PATH
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns("__pycache__"))
    (workspace / ".hve" / "runs").mkdir(exist_ok=True)
    profile = workspace / ".hve" / "user_profile.json"
    if not profile.exists():
        profile.write_text(json.dumps(EMPTY_PROFILE, indent=2) + "\n", encoding="utf-8")


def export_client(workspace: Path, client: str) -> list[Path]:
    """Write the runtime, skills, agents and hooks for Claude Code, Cursor or Codex; return the files and folders written."""
    copy_runtime(workspace)
    skills = workspace / SKILL_DIRS[client]
    written = [workspace / RUNTIME_PATH]
    for source in sorted((EXTENSION / "skills").iterdir()):
        if source.name not in SKIP_SKILLS:
            shutil.copytree(source, skills / source.name, dirs_exist_ok=True)
            written.append(skills / source.name)
    agents = {name: parse_agent(EXTENSION / "agents" / file) for name, file in AGENTS.items()}
    for name, agent in agents.items():
        if client == "claude":
            path = workspace / ".claude" / "agents" / f"{name}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(claude_agent(name, agent), encoding="utf-8")
        else:
            path = skills / name / "SKILL.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            fields = {"name": name, "description": agent["description"]} | ({"disable-model-invocation": True} if client == "cursor" else {})
            path.write_text(frontmatter(fields) + agent["body"], encoding="utf-8")
            if client == "codex":
                (skills / name / "agents").mkdir(exist_ok=True)
                (skills / name / "agents" / "openai.yaml").write_text("policy:\n  allow_implicit_invocation: false\n", encoding="utf-8")
        written.append(path)
    if client != "claude":
        path = workspace / (".cursor/hooks.json" if client == "cursor" else ".codex/hooks.json")
        write_owned(path, json.dumps(hooks_file(client, agents["hve-creator"]), indent=2) + "\n")
        written.append(path)
    return written


def export(client: str, workspace: Path, organization: str | None) -> Json:
    """Export to one client and return the written paths, how to invoke the agents, and the known gaps."""
    if not (EXTENSION / "agents").is_dir() or not (EXTENSION / "skills").is_dir():
        raise FileNotFoundError(f"{EXTENSION} is not a Frontier HVE extension folder (agents/, skills/, runtime/): run the copy shipped in it")
    if client == "vscode" and not organization:
        raise ValueError("the vscode target only connects Azure DevOps: pass --ado <organization>")
    written = [] if client == "vscode" else export_client(workspace, client)
    if organization:
        written.append(add_ado(workspace, client, organization))
    guide = str(ROOT / "docs" / "wiki" / "Adapters.md") if client == "vscode" else f"{RUNTIME_PATH}/docs/wiki/Adapters.md"
    return {"client": client, "written": [p.relative_to(workspace).as_posix() for p in written], "invoke": INVOKE[client],
            "gaps": GAPS[client], "guide": guide}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", choices=["claude", "cursor", "codex", "vscode"])
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--ado", metavar="ORGANIZATION", help="Azure DevOps organization to connect through @azure-devops/mcp")
    options = parser.parse_args()
    print(json.dumps(export(options.client, options.workspace.resolve(), options.ado), indent=2))
