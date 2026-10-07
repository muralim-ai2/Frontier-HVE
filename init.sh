#!/usr/bin/env bash
# Bootstrap health check: tooling, pinned model across modes, OTel export wiring, metrics hook.
set -euo pipefail
cd "$(dirname "$0")"

declare -A MODEL=([minimal]="GPT-6 Astra (copilot)" [single]="Claude Opus 5.5 (copilot)" [creator]="GPT-5.6 Sol (copilot)")

fail() { echo "init: FAIL $*" >&2; exit 1; }

command -v git >/dev/null || fail "git not on PATH"
command -v python >/dev/null || fail "python not on PATH"
python -c 'import sys; sys.exit(sys.version_info < (3, 11))' || fail "python >= 3.11 required"

for mode in minimal single creator; do
  f=".github/agents/$mode.agent.md"
  [ -f "$f" ] || fail "$f missing"
  grep -qxF "model: ${MODEL[$mode]}" "$f" || fail "$f does not pin 'model: ${MODEL[$mode]}'"
done

python - <<'EOF' || fail "point the Copilot OTel file export at .hve/runs/copilot-otel.jsonl (run 'Frontier HVE: Set up' with research metrics on, or see D-005), then reload"
import json, os, pathlib, re, sys
text = (pathlib.Path(os.environ["APPDATA"]) / "Code" / "User" / "settings.json").read_text(encoding="utf-8")
value = lambda key: re.search(rf'"{re.escape(key)}"\s*:\s*("(?:[^"\\]|\\.)*"|true|false)', text)
m = {k: value(f"github.copilot.chat.otel.{k}") for k in ("enabled", "exporterType", "outfile")}
ok = (all(m.values()) and m["enabled"][1] == "true" and json.loads(m["exporterType"][1]) == "file"
      and pathlib.Path(json.loads(m["outfile"][1])).resolve() == pathlib.Path(".hve/runs/copilot-otel.jsonl").resolve())
sys.exit(0 if ok else 1)
EOF

python -c 'import ast, pathlib; ast.parse(pathlib.Path("hooks/metrics.py").read_text())' || fail "hooks/metrics.py does not parse"

[ -d .git ] || git init -q

# Model access is proven by the first run: .hve/runs/<session>.jsonl records the model actually served.
echo "init: OK (minimal: ${MODEL[minimal]}, single: ${MODEL[single]}, creator: ${MODEL[creator]}). Use Session Target 'Local' so agent hooks run."
