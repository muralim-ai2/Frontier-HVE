"""Command-line interface for the Frontier HVE output reflection loop."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow  # noqa: E402


def parser() -> argparse.ArgumentParser:
    """Return the reflection-loop command parser."""
    root = argparse.ArgumentParser(description="Contract -> rubrics -> validation -> council -> reflection decision.")
    commands = root.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="snapshot the contract and request, write the rubric-scoring prompt")
    prepare.add_argument("project", type=Path)
    prepare.add_argument("--contract", type=Path, required=True)
    prepare.add_argument("--request", type=Path, required=True, help="file holding the user's original request verbatim")
    prepare.add_argument("--output-kind", required=True, choices=workflow.OUTPUT_KINDS)
    prepare.add_argument("--revision-pass", type=int, default=0)
    for name, extra in (("record-scores", ["input"]), ("validate", []), ("council-prompts", []), ("complete", []),
                        ("record-human", ["input"])):
        command = commands.add_parser(name)
        command.add_argument("project", type=Path)
        command.add_argument("run")
        for arg in extra:
            command.add_argument(arg, type=Path)
    council = commands.add_parser("record-council", help="record one council member's JSON verdict")
    council.add_argument("project", type=Path)
    council.add_argument("run")
    council.add_argument("role")
    council.add_argument("input", type=Path)
    council.add_argument("--requested-model", required=True)
    commands.add_parser("check", help="print the latest decision; exit 1 when missing or a revision is due").add_argument("project", type=Path)
    return root


def main() -> None:
    """Run one reflection-loop command and print its JSON result."""
    args = parser().parse_args()
    if args.command == "prepare":
        result = workflow.prepare(args.project, args.contract, args.request, args.output_kind, args.revision_pass)
    elif args.command == "record-scores":
        result = workflow.record_scores(args.project, args.run, args.input)
    elif args.command == "validate":
        result = workflow.validate_run(args.project, args.run)
    elif args.command == "council-prompts":
        result = workflow.council_prompts(args.project, args.run)
    elif args.command == "record-council":
        result = workflow.record_council(args.project, args.run, args.role, args.input, args.requested_model)
    elif args.command == "complete":
        result = workflow.finalize(args.project, args.run)
    elif args.command == "record-human":
        result = workflow.record_human(args.project, args.run, args.input)
    else:
        result = workflow.check(args.project)
    print(json.dumps(result, indent=2))
    if args.command == "check" and (result["status"] in ("missing", "revise") or result.get("human") == "revise"):
        sys.exit(1)


if __name__ == "__main__":
    main()
