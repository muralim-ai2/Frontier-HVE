# Validate stage

1. Run every feature check and the `validation_check` from `design.json`; save their output to `.harness/evidence/<feature>/*.log`.
2. Create the migration runbook with the template manager (kind `oracle-offering:migrationRunbook`); fill and validate it.
3. If a check fails or the runbook cannot be completed, run `flow.py transition . rework-required <file:problem; ...>`.
4. Otherwise run `flow.py transition . cutover-ready`.
