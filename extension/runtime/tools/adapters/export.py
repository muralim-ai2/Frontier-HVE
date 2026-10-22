"""Export the Frontier HVE agents, skills and guard hooks to Copilot (CLI, VS Code Copilot harness, cloud agent), Claude Code, Cursor or
Codex at user or project scope, and an Azure DevOps MCP server to any client."""

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
CLOUD_RUNTIME_PATH = ".github/hve/runtime"
HOOK_SOURCE = "hve-creator.agent.md"
SKIP_SKILLS = {"pr-push", "export-harness"}
UNVERIFIED_EVENTS = {"SubagentStop"}  # not confirmed for Codex and Copilot hook files; an unknown event could void the whole file
LAYOUT = {"claude": {"skills": ".claude/skills", "agents": ".claude/agents"},
          "cursor": {"skills": ".cursor/skills", "hooks": ".cursor/hooks.json"},
          "codex": {"skills": ".agents/skills", "hooks": ".codex/hooks.json"},
          "copilot": {"skills": ".copilot/skills", "agents": ".copilot/agents", "hooks": ".copilot/hooks/hve.json"},
          "cloud": {"skills": ".github/skills", "agents": ".github/agents", "hooks": ".github/hooks/hve.json"}}
USER_CLIENTS = {"claude", "cursor", "codex", "copilot"}
PROJECT_CLIENTS = {"claude", "cursor", "codex", "cloud"}
CURSOR_EVENTS = {"SessionStart": "sessionStart", "UserPromptSubmit": "beforeSubmitPrompt", "PreToolUse": "preToolUse",
                 "PostToolUse": "postToolUse", "Stop": "stop"}
LOCAL_ONLY_FIELDS = re.compile(r"^(?:(?:hooks|handoffs):\n(?:[ \t]+.*\n)*|(?:model|reasoning-effort):.*\n)", re.M)
TOOLS_LINE = re.compile(r"^tools: \[(.*)\]$", re.M)
ADO_DOMAINS = ["core", "work", "work-items", "repositories", "pipelines"]
ORGANIZATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,49}$")
HOOK_COMMAND = re.compile(r"""^ {6}command: 'python "\{\{RUNTIME\}\}/([\w./-]+\.py)"((?: [\w-]+)*)'$""")
EMPTY_PROFILE = {"prompt_style": None, "wants_evidence": None, "verbosity": None, "output_format": None, "build_preference": None,
                 "depth_evidence": 0, "explanation_depth": None, "bloat_triggers": []}
INVOKE = {
    "claude": "claude --agent hve-creator (or any hve-* agent); accept the workspace trust prompt so the agent's hooks run",
    "cursor": "type /hve-creator in Agent chat, or Alt+Enter on it to keep it as a Custom Mode for the session",
    "codex": "type $hve-creator; start codex from the project root and trust the hooks once with /hooks",
    "copilot": "pick an HVE agent with /agent in Copilot CLI, or in VS Code with Session Target Copilot",
    "cloud": "commit .github/agents, .github/skills, .github/hooks/hve.json and .github/hve/runtime to the default branch, then assign an "
             "issue to Copilot with an HVE agent",
    "vscode": "start the ado server in the MCP view, sign in, then pick HVE azure-devops in the Chat view",
}
GAPS = {
    "claude": ["pr-push is not exported (it needs the VS Code GitHub Pull Requests extension)",
               "AskUserQuestion answers are mapped from question text to header; labels containing commas split wrongly"],
    "cursor": ["hooks in .cursor/hooks.json apply to every agent, not only hve-creator (at user scope only while an ask is open)",
               "Cursor has no context channel on prompt submit or before a tool: the skill loadout notice and harness challenges do not "
               "reach the model; guards (deny), module-size feedback, victory check and session profile do",
               "the sub-agent context hook (SubagentStart) is not exported: Cursor's subagentStart only allows or denies",
               "pr-push is not exported"],
    "codex": ["hooks in .codex/hooks.json apply to every session, not only $hve-creator (at user scope only while an ask is open)",
              "Codex runs project hooks only after /hooks trust, and with the session directory as working directory",
              "Codex cannot stop the agent from PreToolUse: escalation stops are sent as denies", "pr-push is not exported"],
    "copilot": ["hooks in ~/.copilot/hooks/hve.json run for every Copilot session but act only while an ask is open",
                "Copilot drops prompt-submit hook output and has no context before a tool: agents load skills from `lifecycle.py contract` "
                "output, and the loadout notice arrives after the first tool call",
                "escalation stops are sent as denies; handoff buttons and agent-scoped hooks are VS Code Local only",
                "pr-push is not exported"],
    "cloud": ["the cloud agent is non-interactive: ask-questions gates and guard waivers cannot be answered, so asks run without them",
              "hooks run in a Linux sandbox from the default branch; files they write are discarded after the job",
              "pr-push is not exported"],
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


class Target(TypedDict):
    """One client export: base folder, runtime folder, the runtime path as agent bodies and hook commands name it, and hook options."""

    client: str
    user: bool
    base: Path
    runtime: Path
    body_ref: str
    hook_ref: str
    python: str
    ask_only: bool


def target(client: str, workspace: Path | None, user: bool, python: str) -> Target:
    """Return where and how to export one client at user scope (home folder) or project scope (workspace)."""
    base = Path.home() if user else workspace
    if base is None:
        raise ValueError("project scope needs a workspace folder; pass one or use --user")
    relative = CLOUD_RUNTIME_PATH if client == "cloud" else RUNTIME_PATH
    runtime = base / relative
    body_ref = runtime.as_posix() if user else relative
    return Target(client=client, user=user, base=base, runtime=runtime, body_ref=body_ref,
                  hook_ref=f"${{CLAUDE_PROJECT_DIR}}/{relative}" if client == "claude" and not user else body_ref,
                  python="python3" if client == "cloud" else python, ask_only=user or client == "cloud")


def parse_agent(path: Path, body_ref: str) -> Agent:
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
    return Agent(description=description[1], hooks=hooks, body=body.replace("{{RUNTIME}}", body_ref))


def portable_agent(path: Path, body_ref: str) -> str:
    """Return a VS Code agent template as a Copilot custom agent: Local-only fields removed, tool names mapped to Copilot's aliases."""
    _, front, body = path.read_text(encoding="utf-8").split("---\n", 2)
    front = TOOLS_LINE.sub(lambda m: "tools: " + json.dumps(list(dict.fromkeys(t.strip().split("/")[0] for t in m[1].split(",") if t.strip()))),
                           LOCAL_ONLY_FIELDS.sub("", front))
    return f"---\n{front}---\n{body.replace('{{RUNTIME}}', body_ref)}"


def compat_args(client: str, hook: Hook, ask_only: bool) -> list[str]:
    """Return the agent_compat.py arguments that run one hook for a client."""
    pairs = [f"{key}={value}" for key, value in hook["env"].items()]
    return [*(["--ask-only"] if ask_only else []), "copilot" if client == "cloud" else client, hook["script"], *pairs,
            *(["--", *hook["args"]] if hook["args"] else [])]


def frontmatter(fields: Json) -> str:
    """Return YAML frontmatter with JSON-quoted values (JSON is valid YAML)."""
    return "---\n" + "".join(f"{key}: {json.dumps(value)}\n" for key, value in fields.items()) + "---\n"


def claude_agent(name: str, agent: Agent, hook_ref: str) -> str:
    """Return a Claude Code subagent file whose frontmatter hooks run the harness hooks through agent_compat.py."""
    lines = ["---", f"name: {name}", f"description: {json.dumps(agent['description'])}"]
    if agent["hooks"]:
        lines.append("hooks:")
    for event, hooks in agent["hooks"].items():
        lines += [f"  {event}:", "    - hooks:"]
        for hook in hooks:
            args = [f"{hook_ref}/hooks/agent_compat.py", *compat_args("claude", hook, False)]
            lines += ["        - type: command", "          command: python", f"          args: {json.dumps(args)}"]
            lines += [f"          timeout: {hook['timeout']}"] if hook["timeout"] else []
    return "\n".join([*lines, "---", ""]) + agent["body"]


def shell_command(t: Target, hook: Hook) -> str:
    """Return the shell command that runs one hook through agent_compat.py."""
    return " ".join([t["python"], f'"{t["hook_ref"]}/hooks/agent_compat.py"', *compat_args(t["client"], hook, t["ask_only"])])


def handler(t: Target, hook: Hook) -> Json:
    """Return one command handler with its timeout, if the template sets one."""
    return {"command": shell_command(t, hook)} | ({"timeout": hook["timeout"]} if hook["timeout"] else {})


def hooks_file(t: Target, agent: Agent) -> Json:
    """Return the hooks file for Cursor (native format), Copilot (version 1, VS Code-compatible events) or Codex (Claude-style format)."""
    if t["client"] == "cursor":
        return {"version": 1, "hooks": {CURSOR_EVENTS[event]: [handler(t, h) for h in hooks]
                                        for event, hooks in agent["hooks"].items() if event in CURSOR_EVENTS}}
    if t["client"] in ("copilot", "cloud"):
        return {"version": 1, "hooks": {event: [{"type": "command", "command": shell_command(t, h), "timeoutSec": h["timeout"] or 30}
                                                for h in hooks] for event, hooks in agent["hooks"].items() if event not in UNVERIFIED_EVENTS}}
    return {"hooks": {event: [{"hooks": [{"type": "command"} | handler(t, h) for h in hooks]}] for event, hooks in agent["hooks"].items()
                      if event not in UNVERIFIED_EVENTS}}


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


def copy_runtime(t: Target) -> None:
    """Copy the harness runtime to the target's runtime folder and, at project scope, create the state the hooks read."""
    if t["runtime"].resolve() != ROOT:
        if t["runtime"].exists():
            shutil.rmtree(t["runtime"])
        shutil.copytree(ROOT, t["runtime"], ignore=shutil.ignore_patterns("__pycache__"))
    if t["user"]:
        return
    (t["base"] / ".hve" / "runs").mkdir(parents=True, exist_ok=True)
    profile = t["base"] / ".hve" / "user_profile.json"
    if not profile.exists():
        profile.write_text(json.dumps(EMPTY_PROFILE, indent=2) + "\n", encoding="utf-8")


def export_client(t: Target) -> list[Path]:
    """Write the runtime, skills, every HVE agent and the hooks for one client; return the files and folders written."""
    copy_runtime(t)
    layout = LAYOUT[t["client"]]
    skills = t["base"] / layout["skills"]
    written = [t["runtime"]]
    for source in sorted((EXTENSION / "skills").iterdir()):
        if source.name not in SKIP_SKILLS:
            shutil.copytree(source, skills / source.name, dirs_exist_ok=True)
            written.append(skills / source.name)
    for template in sorted((EXTENSION / "agents").glob("hve-*.agent.md")):
        name = template.name.removesuffix(".agent.md")
        if t["client"] == "claude":
            path = t["base"] / layout["agents"] / f"{name}.md"
            text = claude_agent(name, parse_agent(template, t["body_ref"]), t["hook_ref"])
        elif t["client"] in ("copilot", "cloud"):
            path = t["base"] / layout["agents"] / template.name
            text = portable_agent(template, t["body_ref"])
        else:
            agent = parse_agent(template, t["body_ref"])
            path = skills / name / "SKILL.md"
            fields = {"name": name, "description": agent["description"]} | ({"disable-model-invocation": True} if t["client"] == "cursor" else {})
            text = frontmatter(fields) + agent["body"]
            if t["client"] == "codex":
                (skills / name / "agents").mkdir(parents=True, exist_ok=True)
                (skills / name / "agents" / "openai.yaml").write_text("policy:\n  allow_implicit_invocation: false\n", encoding="utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    if "hooks" in layout:
        path = t["base"] / layout["hooks"]
        write_owned(path, json.dumps(hooks_file(t, parse_agent(EXTENSION / "agents" / HOOK_SOURCE, t["body_ref"])), indent=2) + "\n")
        written.append(path)
    return written


def export(client: str, workspace: Path | None, organization: str | None, user: bool, python: str) -> Json:
    """Export to one client at user or project scope and return the written paths, how to invoke the agents, and the known gaps."""
    if not (EXTENSION / "agents").is_dir() or not (EXTENSION / "skills").is_dir():
        raise FileNotFoundError(f"{EXTENSION} is not a Frontier HVE extension folder (agents/, skills/, runtime/): run the copy shipped in it")
    if client == "vscode" and not organization:
        raise ValueError("the vscode target only connects Azure DevOps: pass --ado <organization>")
    if user and client not in USER_CLIENTS:
        raise ValueError(f"{client} has no user scope; user scope supports {sorted(USER_CLIENTS)}")
    if not user and client not in PROJECT_CLIENTS | {"vscode"}:
        raise ValueError(f"{client} installs at user scope only: pass --user (use `cloud` for a repository's Copilot cloud agent)")
    if organization and (user or client == "cloud"):
        raise ValueError("--ado writes a workspace MCP file for vscode, claude, cursor or codex: run it at project scope")
    t = target(client, workspace, user, python)
    written = [] if client == "vscode" else export_client(t)
    if organization:
        written.append(add_ado(t["base"], client, organization))
    guide = str(ROOT / "docs" / "wiki" / "Adapters.md") if client == "vscode" else f"{t['body_ref']}/docs/wiki/Adapters.md"
    return {"client": client, "scope": "user" if user else "project", "written": [p.relative_to(t["base"]).as_posix() for p in written],
            "invoke": INVOKE[client], "gaps": GAPS[client], "guide": guide}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", choices=["copilot", "cloud", "claude", "cursor", "codex", "vscode"])
    parser.add_argument("workspace", type=Path, nargs="?", help="project folder (project scope)")
    parser.add_argument("--user", action="store_true", help="install under the home folder for every workspace")
    parser.add_argument("--python", default="python", help="Python launcher the hooks run with (for example py -3)")
    parser.add_argument("--ado", metavar="ORGANIZATION", help="Azure DevOps organization to connect through @azure-devops/mcp")
    options = parser.parse_args()
    print(json.dumps(export(options.client, options.workspace.resolve() if options.workspace else None, options.ado, options.user,
                            options.python), indent=2))
