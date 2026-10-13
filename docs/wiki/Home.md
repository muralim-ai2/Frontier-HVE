# Frontier HVE wiki

How-to pages for people and agents. Each page names the files it describes; the source of truth stays in the code, `tracker.json` and `research/decisions/decision_log.md`. The topic list and status live in `tracker.json` under `wiki_topics`.

| Page | Covers | Tracker topic |
|---|---|---|
| [Install](Install.md) | Requirements, one-step install, what happens without Python, checking it works with the provenance report, updating, building the VSIX | W01 |
| [Agents](Agents.md) | The agents available, their guardrails, and how to onboard a new agent | W02, W21 |
| [Skills](Skills.md) | Where skills live, onboarding a skill with `HVE skill-evaluator` (blind with/without evaluation), checking it loads | W09 |
| [Adapters](Adapters.md) | Use the harness in Claude Code, Cursor and Codex CLI; connect Azure DevOps; guards per client; troubleshooting | W19 |
| [Templates](Templates.md) | Configure PRD, technical design and test strategy templates; provenance, validation and company overrides | New capability |
| [Product Manager](Product-Manager.md) | Use `HVE product-manager`: research, model council, PRD in the configured template, backlog in local JSON, Azure DevOps or GitHub | W20 |
| [Evaluation](Evaluation.md) | Output evaluation after the creator's feature loop or on request: JSON contract, grounded rubrics, hooks by output kind, model council, decision, human verdict | New capability |

Other topics in `tracker.json` are not written yet.
