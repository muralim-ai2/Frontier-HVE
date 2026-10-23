# Loop guard awareness mode, error-streak guard, telemetry trim, per-ask skill scoring

- **Requests received:** 2026-10-21, after D-055 (two messages)
- **Decision:** D-056 in `research/decisions/decision_log.md`
- **Built in:** extension 0.15.0 (unreleased, same version as D-054 and D-055)

## User requests (verbatim in substance)

1. **Loop guard.** The loop guard needs more investigation and blocks without a proper explanation. Have it stand down temporarily: it should not block, and should instead surface to the user in the chat under a title like "Guard Invoked - For your attention". Example: "during the run the features_list was modified. The modification was ...". For now it becomes an awareness layer for the user.
2. **Telemetry file.** If the Copilot telemetry file is present, prune it whether telemetry is on or off, so it does not silently take up space. Make sure it is in `.gitignore`.
3. **Repeated errors.** During runs where a presentation could not be made, the agent kept erroring out. After three to five continuous errors it should pause and raise it to the user instead of looping. The user thought this guard existed and was disappointed it did not.
4. **Skill selection.** Select skills by relevance to the task, with a score that does not come only from keyword search but from looking at each ask. Admit the top 10 by rank. Raise the 2,000-token check to about 32,000 tokens.
   - **Correction, same day:** the shortlist must not be curtailed. It can shortlist as many skills as it wants (say 40), ranked by relevance for the ask across its stages or steps. Only when over budget does the LLM suggest the top 10 by relevance score, and this must be presented to the user.

## Findings

- **Request 3: the guard really did not exist.**
  - The loop has stuck rules for feature checks: same failure, circular fixes, an attempt cap, then escalation.
  - These only run between `loop.py next` and `loop.py verify`.
  - A deck build, a package install or any command outside the feature loop had no streak limit, so an agent could retry a failing `python build_deck.py` without end.
- **Request 1: what the loop guard blocks.** It blocks:
  - edits to the loop files while features fail;
  - edits to loop state;
  - stopping while features fail (the victory check);
  - escalations, `--no-verify` and other hook bypasses, `resume`, and unticked or force pushes.

  The deny reasons name the rule, but not what the agent tried to change. The user saw blocks without being able to judge them.

## Decisions and what was built

| Request | Built |
|---|---|
| 1 | `hooks/guard_mode.json` with `{"loop_guard": "advise"}`; set it to `enforce` to restore blocking. See the first list below. |
| 2 | `tools/observe/otel_trim.py`; the extension runs it from `extension.js`. See the second list below. |
| 3 | New hook `hooks/error_guard.py`. See the third list below. |
| 4 | Changes to `recommend.rank`, the contract and the agent instructions. See the fourth list below. |

**Request 1: loop guard in awareness mode**
- In advise mode these are not blocked:
  - loop-file edits (`loop_files`);
  - loop-state edits (`anti_gaming`);
  - stopping while features still fail (`victory_check`).
- Instead, each trip is recorded as an intervention and returns a message that starts with `Guard Invoked - For your attention: during the run <what happened>. The modification was: <the command, or the file with the replaced text>. ...`.
- The agent is told to show that message word for word under that heading.
- Escalation, hook bypass, `resume` and push rules still block, because they protect the user, git history and the remote.

**Request 2: telemetry trim**
- `otel_trim.py` keeps the export's records from the last 3 days, plus undated ones, with at most 200 MB of the newest.
- It rewrites the file in place, because the Copilot exporter keeps its file handle open.
- It adds `.hve/runs/copilot-otel.jsonl` to `.gitignore` unless `.hve/` is already ignored.
- It refuses while `bench.lock` exists, because a benchmark run is reading the export.
- The extension runs it in the background on every activation when the file exists, and when research telemetry is turned on. It tells the user what it trimmed or ignored, and shows failures as errors.

**Request 3: error-streak guard**
- After 3 failed terminal commands in a row, the agent stops (`continue: false`) and the user sees `Error guard - paused for your attention` with each command and the end of its output.
- **What counts as a failure:** "exited with code N" for N other than 0, or a tool error.
- **What resets the streak:** a successful command, or the user's next prompt.
- **What is ignored:** the feature loop's own scripts, which have their own retry rules.
- While paused, every tool except reading and asking the user is denied.
- It runs on E2E, BYOW, Prototype Creator and the engineer.

**Request 4: skill selection (after the correction)**
- **Shortlist:** `recommend.rank` shortlists every category or keyword match, with no cap: required skills first, then by relevance (shared categories plus rarity-weighted shared word stems).
- **Within the guideline** (10 skills, 32,000 tokens): all shortlisted skills load.
- **Over it:** every ask-opening agent scores each shortlisted skill 0-10 for the ask across its stages, from its description, writes `.hve/asks/skill-scores.json`, and runs `lifecycle.py skills score`.
  - That re-ranks the shortlist by score and sets the suggested set: the required skills plus the top-scored, up to 10. It drops nothing itself.
  - The agent then shows the user the shortlist size and the suggested skills with their scores, reasons and tokens, and asks once: suggested top 10, all, or named (`lifecycle.py skills suggested|all|<a,b>`).
  - Scores and reasons show in `plan.md`.
- **Budget:** `max_tokens` goes from 2,000 to 32,000.
- **Not kept:** an intermediate version that capped loading at 10 and kept a 20-candidate pool was replaced the same day.

## Decisions to surface (not settled)

1. **The threshold is 3** (the user said three to five). Three failed commands in a row also stops a legitimate fix-and-retry cycle outside the loop. Raise `STREAK_LIMIT` to 5 if that proves too eager.
2. **Failure detection reads the tool's text** ("exited with code"). Clients that report exit codes differently are not counted. Sub-agent sessions reset only on a successful command.
3. **Awareness mode is global.** It also applies to the research arms in `.github/agents/` (same `hooks/`), so benchmark runs no longer block loop-file edits. Benchmarks comparing guard effects should switch back to `enforce`.
4. **Copilot CLI and Cursor drop the awareness message.** They have no context channel before a tool runs, so in those clients awareness mode means the change goes through with no visible notice. Claude Code shows it.
5. **The trim deletes data.** Records older than 3 days, or beyond 200 MB, are gone. This includes OTel spans that ask reports and uncollected benchmark sessions would need. The bench lock prevents trimming during a run, but not between a run and its `collect.py`.
6. **Per-ask skill scoring is an agent judgement.** It is not deterministic. It runs only when the shortlist is over the guideline; below it, everything relevant loads. With 32,000 tokens, a full shortlist may add many tokens per turn.
7. **`lifecycle.py` is at 495 lines**, close to the 500-line limit. The next addition should split it.
