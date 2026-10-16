"""Run the evidence-backed output evaluation stages and the deterministic reflection decision."""

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compose import combine, plugin_contract, selection
from contract import OUTPUT_KINDS, EvaluationContract, ValidationHook, items, load_contract, mapping, text, validate_contract

Json = dict[str, Any]
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
LINE_SUFFIX = re.compile(r":\d+(?::\d+)?$")
CHECKS = re.compile(r"HARNESS_CHECKS (\d+)/(\d+)")
EXCLUDED_PARTS = {".git", ".hve", "node_modules", ".next", "dist", "build", "out", "coverage", "__pycache__", ".venv", ".turbo"}
KINDS = ("risk", "miss", "questionable-design")
SEVERITIES = ("critical", "high", "medium", "low")
RECOMMENDATIONS = ("pass", "revise", "human-review")
HUMAN_DECISIONS = ("accept", "revise", "reject")
TAIL = 1500


def _write_json(path: Path, value: object) -> None:
    """Write JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Any:
    """Return parsed JSON from a required file."""
    if not path.is_file():
        raise FileNotFoundError(f"required evaluation file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _project(project: Path) -> Path:
    """Return the resolved project folder or raise."""
    resolved = project.resolve()
    if not resolved.is_dir():
        raise NotADirectoryError(f"evaluation project not found: {project}")
    return resolved


def _run_folder(project: Path, run_id: str) -> Path:
    """Return the folder of one evaluation run."""
    if not RUN_ID.fullmatch(run_id):
        raise ValueError(f"invalid evaluation run id: {run_id!r}")
    return project / ".hve" / "evaluations" / run_id


def _open_run(project: Path, run_id: str, status: str) -> tuple[Path, Path, EvaluationContract, Json]:
    """Return project, run folder, contract snapshot and manifest of a run that is at the expected stage."""
    project = _project(project)
    folder = _run_folder(project, run_id)
    manifest = mapping(_read_json(folder / "manifest.json"), "manifest")
    if manifest["status"] != status:
        raise ValueError(f"evaluation run {run_id} is at stage {manifest['status']!r}, expected {status!r}")
    return project, folder, validate_contract(_read_json(folder / "contract.json")), manifest


def _advance(folder: Path, manifest: Json, status: str) -> None:
    """Move the run manifest to its next stage."""
    _write_json(folder / "manifest.json", manifest | {"status": status})


def _inventory(project: Path) -> list[str]:
    """Return project-relative files a scorer may cite, without dependencies or harness state."""
    files = []
    for folder, dirs, names in os.walk(project):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_PARTS]
        files += [(Path(folder) / name).relative_to(project).as_posix() for name in names]
    return sorted(files)


def _fingerprint(project: Path, files: list[str]) -> str:
    """Return a SHA-256 over the paths and contents of the delivered files."""
    digest = hashlib.sha256()
    for name in files:
        digest.update(f"{name}\0{hashlib.sha256((project / name).read_bytes()).hexdigest()}\n".encode())
    return digest.hexdigest()


def latest_report(project: Path) -> Json | None:
    """Return the most recent completed reflection report, or None when there is none."""
    reports = sorted((_project(project) / ".hve" / "evaluations").glob("*/report.json"), key=lambda p: p.parent.name)
    return mapping(_read_json(reports[-1]), "latest evaluation report") if reports else None


def _plugin_run(project: Path, core: EvaluationContract, plugin_path: Path | None, selection_path: Path | None, output_kind: str,
                revision_pass: int, last: Json | None) -> tuple[EvaluationContract, Json | None, str | None]:
    """Return the run contract, the core-rubric selection and the plugin contract hash; revision passes reuse pass 0's choices."""
    previous = _read_json(_run_folder(project, last["runId"]) / "manifest.json") if revision_pass else None
    if plugin_path is None:
        if selection_path is not None:
            raise ValueError("--rubric-selection needs --plugin-contract")
        if previous is not None and previous["pluginContractSha256"] is not None:
            raise ValueError("this evaluation used a plugin contract; revision passes must pass the same --plugin-contract")
        return core, None, None
    digest = hashlib.sha256(plugin_path.read_bytes()).hexdigest()
    plugin = plugin_contract(json.loads(plugin_path.read_text(encoding="utf-8")), core)
    if previous is None:
        if selection_path is None:
            raise ValueError("a plugin contract needs --rubric-selection: list every core rubric in include or exclude")
        chosen = selection(_read_json(selection_path), core, plugin, output_kind)
    else:
        if selection_path is not None:
            raise ValueError("revision passes reuse the pass 0 rubric selection; do not pass --rubric-selection")
        if previous["pluginContractSha256"] != digest:
            raise ValueError("revision passes must use the same plugin contract as pass 0")
        chosen = previous["rubricSelection"]
    return combine(core, plugin, chosen), chosen, digest


def prepare(project: Path, contract_path: Path, request_path: Path, output_kind: str, revision_pass: int,
            plugin_path: Path | None = None, selection_path: Path | None = None) -> Json:
    """Create an immutable contract snapshot (core, or plugin rubrics plus selected core rubrics), the request and the scoring prompt."""
    project = _project(project)
    core = load_contract(contract_path.resolve())
    if output_kind not in OUTPUT_KINDS:
        raise ValueError(f"output kind must be one of {list(OUTPUT_KINDS)}; got {output_kind!r}")
    limit = core["decision"]["maxRevisionPasses"]
    if not 0 <= revision_pass <= limit:
        raise ValueError(f"revision pass must be between 0 and {limit}")
    last = latest_report(project)
    if revision_pass and (not last or last["decision"] != "revise" or last["revisionPass"] != revision_pass - 1):
        raise ValueError(f"revision pass {revision_pass} needs a completed pass {revision_pass - 1} whose decision is revise")
    contract, chosen, plugin_digest = _plugin_run(project, core, plugin_path, selection_path, output_kind, revision_pass, last)
    inventory = _inventory(project)
    fingerprint = _fingerprint(project, inventory)
    if last and last["fingerprint"] == fingerprint:
        raise ValueError(f"nothing changed since evaluation {last['runId']} (decision {last['decision']}); change the output first")
    request = text(request_path.read_text(encoding="utf-8"), f"request file {request_path}")
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-p{revision_pass}"
    folder = _run_folder(project, run_id)
    if folder.exists():
        raise FileExistsError(f"evaluation run already exists: {folder}")
    folder.mkdir(parents=True)
    (folder / "request.md").write_text(request + "\n", encoding="utf-8")
    _write_json(folder / "contract.json", contract)
    _write_json(folder / "rubric-prompt.json", {
        "task": "rubric-scoring",
        "request": (folder / "request.md").relative_to(project).as_posix(),
        "instructions": [
            "Read the request, then score each rubric from 0 to 1 against its criteria using only what the project delivers.",
            "Read every file you cite. Cite at least one existing project-relative file per rubric (optionally with :line).",
            "Score what is delivered, not what was planned; missing evidence lowers the score.",
            "Return JSON only, rubrics in the order given: "
            '{"rubrics": [{"id": "...", "score": 0.0, "rationale": "...", "evidence": ["path[:line]"]}]}'],
        "rubrics": [{k: r[k] for k in ("id", "description", "criteria")} for r in contract["rubrics"]],
        "inventory": inventory})
    _write_json(folder / "manifest.json", {
        "runId": run_id, "revisionPass": revision_pass, "outputKind": output_kind, "fingerprint": fingerprint,
        "status": "awaiting-rubric-scores",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "contractSha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "pluginContractSha256": plugin_digest, "rubricSelection": chosen})
    return {"runId": run_id, "folder": folder.relative_to(project).as_posix(), "status": "awaiting-rubric-scores",
            "next": "score rubric-prompt.json with a fresh sub-agent, then record-scores"}


def _evidence_path(project: Path, reference: str) -> str:
    """Return a project-relative evidence path that exists, or raise."""
    relative = LINE_SUFFIX.sub("", reference.strip())
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"evidence must be a project-relative file: {reference!r}")
    target = (project / relative).resolve()
    if not target.is_relative_to(project):
        raise ValueError(f"evidence escapes the project: {reference!r}")
    if not target.is_file():
        raise ValueError(f"evidence file does not exist: {reference!r}")
    return reference.strip()


def record_scores(project: Path, run_id: str, input_path: Path) -> Json:
    """Validate and record complete rubric scores that cite existing files."""
    project, folder, contract, manifest = _open_run(project, run_id, "awaiting-rubric-scores")
    raw = items(mapping(_read_json(input_path), "rubric scores").get("rubrics"), "rubric scores.rubrics")
    expected = [r["id"] for r in contract["rubrics"]]
    got = [mapping(item, f"rubrics[{i}]").get("id") for i, item in enumerate(raw)]
    if got != expected:
        raise ValueError(f"rubric results must follow contract order {expected}; got {got}")
    results = []
    for spec, item in zip(contract["rubrics"], raw):
        score = item.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError(f"rubric {spec['id']} score must be between 0 and 1")
        evidence = [_evidence_path(project, text(e, f"rubric {spec['id']}.evidence")) for e in items(item.get("evidence"), "evidence")]
        if not evidence:
            raise ValueError(f"rubric {spec['id']}.evidence must cite at least one existing file")
        status = "below-blocking" if score < spec["blocking"] else "below-warning" if score < spec["warning"] else "ok"
        results.append({"id": spec["id"], "score": float(score), "blocking": spec["blocking"], "warning": spec["warning"],
                        "status": status, "rationale": text(item.get("rationale"), f"rubric {spec['id']}.rationale"),
                        "evidence": evidence})
    _write_json(folder / "rubric-results.json", {"rubrics": results})
    _advance(folder, manifest, "awaiting-validation")
    return {"runId": run_id, "status": "awaiting-validation", "rubrics": {r["id"]: r["status"] for r in results}}


def _run(command: str, project: Path, timeout: int, env: dict[str, str] | None = None) -> Json:
    """Run one shell command in the project and return its exit code and output tail; a timeout counts as a failure."""
    try:
        done = subprocess.run(command, shell=True, cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, env=env)
    except subprocess.TimeoutExpired as expired:
        return {"command": command, "exitCode": None, "timedOut": True, "output": f"timed out after {expired.timeout}s"}
    output = (done.stdout + done.stderr)[-TAIL:]
    checks = CHECKS.findall(done.stdout)
    return {"command": command, "exitCode": done.returncode, "timedOut": False, "output": output} | (
        {"checks": f"{checks[-1][0]}/{checks[-1][1]}"} if checks else {})


def _feature_checks(project: Path, hook: ValidationHook) -> Json:
    """Re-run every locked feature check against the delivered output."""
    features = items(_read_json(project / "feature_list.json"), "feature_list.json")
    runs = [{"feature": text(mapping(f, "feature").get("name"), "feature.name")}
            | _run(text(f.get("verify"), "feature.verify"), project, hook["timeoutSeconds"]) for f in features]
    passed = sum(1 for r in runs if r["exitCode"] == 0)
    return {"passed": bool(runs) and passed == len(runs), "detail": f"{passed}/{len(runs)} feature checks passed", "runs": runs}


def _command(project: Path, folder: Path, hook: ValidationHook) -> Json:
    """Run a contract-defined evidence command with the run folder in HVE_EVALUATION_RUN."""
    result = _run(hook["command"], project, hook["timeoutSeconds"], {**os.environ, "HVE_EVALUATION_RUN": str(folder)})
    return {"passed": result["exitCode"] == 0, "detail": f"exit code {result['exitCode']}", "runs": [result]}


def _artifacts(project: Path, hook: ValidationHook) -> Json:
    """Collect evidence files matching the hook's globs with their size and SHA-256."""
    files = sorted({p for pattern in hook["paths"] for p in project.glob(pattern) if p.is_file()})
    artifacts = [{"path": p.relative_to(project).as_posix(), "bytes": p.stat().st_size,
                  "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    return {"passed": bool(artifacts), "detail": f"collected {len(artifacts)} artifact(s)", "artifacts": artifacts}


def validate_run(project: Path, run_id: str) -> Json:
    """Run the hooks that fit the output kind: `always` hooks, hooks of rubrics scored below warning, and every hook on a revision pass."""
    project, folder, contract, manifest = _open_run(project, run_id, "awaiting-validation")
    scores = {r["id"]: r for r in _read_json(folder / "rubric-results.json")["rubrics"]}
    revision = manifest["revisionPass"] > 0
    low = [r["id"] for r in contract["rubrics"] if revision or scores[r["id"]]["status"] != "ok"]
    results, not_applicable = [], []
    for hook in contract["validation"]["hooks"]:
        if manifest["outputKind"] not in hook["outputKinds"]:
            not_applicable.append(hook["id"])
            continue
        linked = [r["id"] for r in contract["rubrics"] if hook["id"] in r["validationHooks"]]
        rubrics = linked if hook["trigger"] == "always" else [r for r in linked if r in low]
        if not rubrics:
            continue
        outcome = (_feature_checks(project, hook) if hook["type"] == "feature-checks"
                   else _command(project, folder, hook) if hook["type"] == "command" else _artifacts(project, hook))
        results.append({"id": hook["id"], "type": hook["type"], "required": hook["required"], "rubrics": rubrics} | outcome)
    passed = all(r["passed"] for r in results if r["required"])
    _write_json(folder / "validation-results.json", {"triggeredBy": low, "notApplicable": not_applicable, "hooks": results,
                                                     "passed": passed})
    _advance(folder, manifest, "awaiting-council")
    return {"runId": run_id, "status": "awaiting-council", "passed": passed,
            "hooks": {r["id"]: r["detail"] + ("" if r["passed"] else " (failed)") for r in results}}


def council_prompts(project: Path, run_id: str) -> Json:
    """Write one evidence-bounded prompt for each high-tier council role."""
    project, folder, contract, manifest = _open_run(project, run_id, "awaiting-council")
    hook_ids = [h["id"] for h in contract["validation"]["hooks"]]
    excluded = ["Core rubrics the agent excluded, with its reasons (judge whether each exclusion is sound; an unsound one is a "
                f"miss on the covering rubric): {json.dumps(manifest['rubricSelection'])}"] if manifest["rubricSelection"] else []
    shared = {
        "request": (folder / "request.md").read_text(encoding="utf-8"),
        "rubrics": contract["rubrics"],
        "rubricResults": _read_json(folder / "rubric-results.json")["rubrics"],
        "validationResults": _read_json(folder / "validation-results.json"),
        "rules": excluded + [
            "Judge the rubric scores and validation evidence above. You may read project files to confirm or refute them; edit nothing.",
            "Mark risks, misses and questionable designs; do not invent proof.",
            f"Each marker's rubric is one of {[r['id'] for r in contract['rubrics']]}.",
            f"Each marker cites evidence as rubric:<id>, validation:<id> (ids {hook_ids}) or file:<project-relative path>.",
            "Severity critical means the output must not ship as is.",
            "Recommend pass only when no critical or high marker remains; revise when a bounded revision can fix the markers; "
            "human-review when a judgment call (design, scope, risk acceptance) needs a person.",
            "Return JSON only: {\"role\": \"<your role>\", \"recommendation\": \"pass|revise|human-review\", \"summary\": \"...\", "
            "\"markers\": [{\"kind\": \"risk|miss|questionable-design\", \"severity\": \"critical|high|medium|low\", "
            "\"rubric\": \"<id>\", \"summary\": \"...\", \"evidence\": [\"...\"]}]}"]}
    prompts = [{"role": r["id"], "mandate": r["mandate"], "modelTier": r["modelTier"]} | shared for r in contract["council"]["roles"]]
    path = folder / "council-prompts.json"
    _write_json(path, {"prompts": prompts})
    return {"runId": run_id, "prompts": path.relative_to(project).as_posix(), "roles": [p["role"] for p in prompts],
            "next": "run one high-tier reviewer per role (a different model vendor each), then record-council per role"}


def _evidence_ref(project: Path, reference: str, rubric_ids: list[str], hook_ids: list[str]) -> str:
    """Return a valid marker evidence reference or raise."""
    kind, _, value = reference.partition(":")
    if (kind == "rubric" and value in rubric_ids) or (kind == "validation" and value in hook_ids):
        return reference
    if kind == "file":
        return "file:" + _evidence_path(project, value)
    raise ValueError(f"marker evidence must be rubric:<id>, validation:<id> or file:<path>; got {reference!r}")


def _marker(project: Path, raw: object, role: str, rubric_ids: list[str], hook_ids: list[str]) -> Json:
    """Return one validated council marker."""
    item = mapping(raw, f"council {role} marker")
    kind, severity, rubric = item.get("kind"), item.get("severity"), item.get("rubric")
    if kind not in KINDS or severity not in SEVERITIES or rubric not in rubric_ids:
        raise ValueError(f"council {role} marker needs kind in {KINDS}, severity in {SEVERITIES} and rubric in {rubric_ids}; "
                         f"got {kind!r}, {severity!r}, {rubric!r}")
    evidence = [_evidence_ref(project, text(e, "marker evidence"), rubric_ids, hook_ids) for e in items(item.get("evidence"), "evidence")]
    if not evidence:
        raise ValueError(f"council {role} marker must cite evidence")
    return {"kind": kind, "severity": severity, "rubric": rubric, "summary": text(item.get("summary"), "marker summary"),
            "evidence": evidence, "source": role}


def record_council(project: Path, run_id: str, role: str, input_path: Path, requested_model: str) -> Json:
    """Validate and record one council member's traceable verdict."""
    project, folder, contract, _ = _open_run(project, run_id, "awaiting-council")
    _read_json(folder / "council-prompts.json")
    roles = [r["id"] for r in contract["council"]["roles"]]
    if role not in roles:
        raise ValueError(f"unknown council role {role!r}; expected one of {roles}")
    target = folder / "council" / f"{role}.json"
    if target.exists():
        raise FileExistsError(f"council verdict for {role} is already recorded: {target}")
    verdict = mapping(_read_json(input_path), f"council verdict {role}")
    if verdict.get("role") != role:
        raise ValueError(f"council verdict role must be {role!r}; got {verdict.get('role')!r}")
    if verdict.get("recommendation") not in RECOMMENDATIONS:
        raise ValueError(f"unsupported council recommendation {verdict.get('recommendation')!r}; expected one of {RECOMMENDATIONS}")
    rubric_ids = [r["id"] for r in contract["rubrics"]]
    hook_ids = [h["id"] for h in contract["validation"]["hooks"]]
    markers = [_marker(project, m, role, rubric_ids, hook_ids) for m in items(verdict.get("markers"), "council markers")]
    _write_json(target, {"role": role, "requestedModel": text(requested_model, "requested model"),
                         "recommendation": verdict["recommendation"], "summary": text(verdict.get("summary"), "council summary"),
                         "markers": markers})
    remaining = [r for r in roles if not (folder / "council" / f"{r}.json").exists()]
    return {"runId": run_id, "role": role, "recorded": len(markers), "remainingRoles": remaining}


def _synthetic_markers(scores: list[Json], validation: Json) -> list[Json]:
    """Return deterministic markers for blocking scores and failed required validation."""
    markers = [{"kind": "miss", "severity": "high", "rubric": r["id"], "source": "rubrics", "evidence": [f"rubric:{r['id']}"],
                "summary": f"{r['id']} scored {r['score']:.2f}, below its blocking threshold {r['blocking']:.2f}"}
               for r in scores if r["status"] == "below-blocking"]
    for hook in validation["hooks"]:
        if hook["required"] and not hook["passed"]:
            markers.append({"kind": "risk", "severity": "high", "rubric": hook["rubrics"][0], "source": "validation",
                            "evidence": [f"validation:{hook['id']}"], "summary": f"required validation {hook['id']} did not pass: {hook['detail']}"})
    return markers


def finalize(project: Path, run_id: str) -> Json:
    """Aggregate scores, validation and all council verdicts into the reflection decision."""
    project, folder, contract, manifest = _open_run(project, run_id, "awaiting-council")
    roles = [r["id"] for r in contract["council"]["roles"]]
    missing = [r for r in roles if not (folder / "council" / f"{r}.json").exists()]
    if missing:
        raise ValueError(f"council verdicts missing for {missing}")
    verdicts = [_read_json(folder / "council" / f"{r}.json") for r in roles]
    scores = _read_json(folder / "rubric-results.json")["rubrics"]
    validation = _read_json(folder / "validation-results.json")
    weights = {r["id"]: r["weight"] for r in contract["rubrics"]}
    specs = {h["id"]: h for h in contract["validation"]["hooks"]}
    score = round(sum(weights[r["id"]] * r["score"] for r in scores), 4)
    synthetic = _synthetic_markers(scores, validation)
    markers = sorted(synthetic + [m for v in verdicts for m in v["markers"]], key=lambda m: SEVERITIES.index(m["severity"]))
    votes = {rec: sum(1 for v in verdicts if v["recommendation"] == rec) for rec in RECOMMENDATIONS}
    rules = contract["decision"]
    blocked = bool(synthetic) or any(m["severity"] == "critical" for m in markers)
    if not blocked and score >= rules["minimumScore"] and votes["pass"] >= rules["councilPasses"]:
        decision, reason = "pass", "Scores, required validation and the council agree the output can go to the human as delivered."
    elif manifest["revisionPass"] < rules["maxRevisionPasses"] and votes["human-review"] < rules["councilPasses"]:
        decision, reason = "revise", "Fix the critical and high markers in one bounded revision pass, then evaluate again."
    else:
        decision, reason = "human-review", ("Revision budget spent or the council asks for a human judgment; "
                                            "present the markers to the human for reflection.")
    report = {"runId": run_id, "revisionPass": manifest["revisionPass"], "outputKind": manifest["outputKind"],
              "fingerprint": manifest["fingerprint"], "decision": decision, "reason": reason, "score": score,
              "minimumScore": rules["minimumScore"], "votes": votes,
              "rubrics": [{k: r[k] for k in ("id", "score", "blocking", "warning", "status")} for r in scores],
              "validation": {"passed": validation["passed"], "hooks": [{k: h[k] for k in ("id", "required", "passed", "detail")}
                                                                       for h in validation["hooks"]]},
              "council": [{k: v[k] for k in ("role", "requestedModel", "recommendation", "summary")} for v in verdicts],
              "markers": markers,
              "excludedCoreRubrics": ([{"id": k, "reason": v, "detail": manifest["rubricSelection"]["reasons"].get(k)}
                                       for k, v in manifest["rubricSelection"]["exclude"].items()]
                                      if manifest["rubricSelection"] else []),
              "recommendations": [f"{h['id']}: {h['detail']}. {specs[h['id']]['recommendation']}"
                                  for h in validation["hooks"] if not h["required"] and not h["passed"]]}
    _write_json(folder / "report.json", report)
    _advance(folder, manifest, "complete")
    return report


def record_human(project: Path, run_id: str, input_path: Path) -> Json:
    """Record the human's verdict on a completed run and the markers they disagree with."""
    project, folder, _, _ = _open_run(project, run_id, "complete")
    target = folder / "human.json"
    if target.exists():
        raise FileExistsError(f"human verdict is already recorded: {target}")
    markers = _read_json(folder / "report.json")["markers"]
    verdict = mapping(_read_json(input_path), "human verdict")
    if verdict.get("decision") not in HUMAN_DECISIONS:
        raise ValueError(f"human decision must be one of {HUMAN_DECISIONS}; got {verdict.get('decision')!r}")
    disagree = items(verdict.get("disagree"), "human verdict.disagree (marker indexes; [] when agreeing with all)")
    if any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(markers) for i in disagree) or len(set(disagree)) != len(disagree):
        raise ValueError(f"human verdict.disagree must hold unique marker indexes from 0 to {len(markers) - 1}")
    record = {"decision": verdict["decision"], "summary": text(verdict.get("summary"), "human verdict.summary"),
              "recorded": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "disagree": [{"index": i} | {k: markers[i][k] for k in ("severity", "kind", "rubric", "source", "summary")} for i in disagree]}
    _write_json(target, record)
    return {"runId": run_id, "decision": record["decision"], "agreed": len(markers) - len(disagree), "disagreed": len(disagree)}


def check(project: Path) -> Json:
    """Return the latest reflection decision, the human verdict if recorded, and whether another pass is due."""
    report = latest_report(project)
    if report is None:
        return {"status": "missing", "message": "No completed output evaluation was found."}
    counts = {s: sum(1 for m in report["markers"] if m["severity"] == s) for s in SEVERITIES}
    messages = {"pass": "Output evaluation passed; report it to the human.",
                "human-review": "Output evaluation is complete and needs human reflection on its markers.",
                "revise": "Output evaluation needs another bounded revision pass."}
    human = _run_folder(_project(project), report["runId"]) / "human.json"
    return {"status": report["decision"], "runId": report["runId"], "score": report["score"], "markers": counts,
            "recommendations": report["recommendations"], "message": messages[report["decision"]]} | (
        {"human": _read_json(human)["decision"]} if human.exists() else {})
