# Phase 9: skill selection and source coverage audit (2026-10-07)

## Conclusion

**No: the evidence does not establish that all relevant AgentX skills were brought in or evaluated.** The completed experiment evaluated **13 locally authored skills**, not all 134 upstream skills. Ten passed the final admission gate; three were rejected. All six requested areas have at least one admitted skill, but category coverage is not exhaustive capability coverage.

The earlier [micro-evaluation findings](phase-9-skill-micro-eval.md) describe the experiment and its results, not a complete source-selection audit. [D-037 and D-038](../decisions/decision_log.md) explain the authored approach and admission method, but do not contain a source-by-source inclusion/exclusion ledger. This note makes that limitation explicit; it does not retrospectively claim that missing selection work happened.

## 1. What was counted

Local evidence was inspected on 2026-10-07:

| Population | Count | Evidence and meaning |
|---|---:|---|
| AgentX source skill bodies | 134 | Verified against the recursive GitHub tree at commit `fc39b297b6af31630f3ec6cfac94930f7827097a`, counting `.github/skills/**/SKILL.md`; tree response was not truncated |
| Locally authored candidates | 13 | One skill body per directory in [skills/authored](../../skills/authored) |
| Evaluated local skills | 13 | Matching reports in [skills/evals](../../skills/evals) and task suites in [tests/skill_tasks](../../tests/skill_tasks) |
| Admitted library skills | 10 | Top-level `admitted` array in [registry.json](../../skills/registry.json), with matching bodies in [skills/admitted](../../skills/admitted) |
| Rejected local skills | 3 | Top-level `rejected` array in the registry; bodies remain in the authored directory |
| Separate harness plugin skills | 10 | Current working-tree bodies in [plugins/harness-assist/skills](../../plugins/harness-assist/skills); includes untracked `check-context-load` at inspection time |
| Additional workspace registry | Not present | No `.hve/skills-registry.json` in this workspace at inspection time |
| Persisted upstream triage report | Not present | No `skills/triage.json` or source-by-source selection ledger found |

The 10 admitted bodies are copies of authored candidates, not 10 additional distinct skills. Likewise, generated copies under [extension](../../extension) are packaging surfaces, not evidence of additional evaluated candidates. Plugin skills are a separate population: check-context-load, code-review, delivery-coach, explain-walkthrough, feature-checklist, parallel-options, pr-push, prototype-guardrail, recommend-skills and run-tests. They are not additional AgentX imports demonstrated by the 13-skill experiment. Editor-installed skills outside this repository are outside this count.

**Registry visibility caveat:** the three entries inside the `rejected` array still contain an inner `status: "admitted"` field. The current [recommender](../../tools/skills/recommend.py) reads only the top-level `admitted` array, so those three are not library-loadable through that path. This audit uses array membership and on-disk admitted bodies, not that misleading inner field. No registry or runtime code was changed for this documentation audit.

### Upstream count cross-check

Source: [pinned AgentX tree](https://github.com/jnPiyush/AgentX/tree/fc39b297b6af31630f3ec6cfac94930f7827097a/.github/skills), [recursive tree API](https://api.github.com/repos/jnPiyush/AgentX/git/trees/fc39b297b6af31630f3ec6cfac94930f7827097a?recursive=1), and [source index](https://github.com/jnPiyush/AgentX/blob/fc39b297b6af31630f3ec6cfac94930f7827097a/Skills.md). The retrieved index blob SHA was `ce4c24ef65dca7733429fd79d7797fd81c8f7d35`.

| Upstream directory | Skill bodies |
|---|---:|
| ai-systems | 30 |
| architecture | 8 |
| data | 7 |
| design | 13 |
| development | 26 |
| diagrams | 1 |
| document | 3 |
| domain | 7 |
| infrastructure | 4 |
| languages | 10 |
| low-code | 13 |
| operations | 5 |
| product | 1 |
| testing | 6 |
| **Total** | **134** |

The source index advertises 134 skills, but its pipe-delimited directory contains **121 unique paths**. The tree contains 13 additional low-code skills omitted from that directory: canvas-app-yaml, copilot-studio-agents, dataverse-plugins, dataverse-schema, environment-variables, model-driven-app, pac-cli, pcf-controls, power-automate-desktop, power-automate-flow-json, power-pages, security-roles and solution-anatomy. All 121 indexed paths exist in the tree. A future exhaustive inventory must therefore enumerate actual skill bodies, not rely on the index alone.

This commit pins the source checked for this audit. The original selection notes did not pin an upstream commit, so it is not proof of precisely which source revision was considered during authoring.

## 2. What selection method was actually documented

There were three distinct decisions, which must not be conflated:

1. **Authoring/curation.** D-037 records the request for UX, architecture, de-slop, scrub, dreams/self-learning and research skills, permission to rewrite, and the decision to author 13 short, focused skills informed by AgentX topics. The [NOTICE](../../skills/authored/NOTICE) says the text is original, with topic/idea attribution; these are not 13 verbatim imports. The notes record token cost and focused loading as motivations. They do not explain an exhaustive ranking of 134 source skills or why every other relevant source capability was excluded.
2. **Admission of those authored candidates.** The [onboarding gate](../../tools/skills/onboard.py) supports a provisional static check: scan passes, at least one matching category, at most 800 skill tokens, description at most 200 characters, and no listed non-Python script types. D-037 records provisional admission of the authored set. D-038 then records paired micro-evaluation of all 13 authored candidates.
3. **Per-task loading after admission.** The [recommender](../../tools/skills/recommend.py) selects from the admitted library, filters by task categories, ranks by status/relevance/lift/size, and fills a budget of at most 10 skills and 2,000 tokens. This is a per-task context budget, **not a 13-skill library ceiling** and not a reason to skip evaluating other relevant skills. Library skills are intentionally separate from discoverable plugin skills, which also explains why editor-visible lists do not show the same population.

### Available triage tooling is not evidence that an exhaustive triage ran

[triage.py](../../tools/skills/triage.py) can scan every skill body under a supplied source directory. It matches category regexes against the skill's **name and description**, orders candidates by scan pass/fail and increasing estimated size, and shortlists up to the configured `max_skills` per category. It would persist the result to `skills/triage.json`.

No saved output of that full-source operation was found. Its existence does not establish a completed 134-skill review, nor does its size-first shortlist measure usefulness. [categories.json](../../skills/categories.json) supplies category patterns, thresholds and load budgets; it is **not an inventory** and cannot show which source skills were considered or omitted. Its seventh category, graph-workflow-agents, also does not add a skill to the evaluated set.

Metadata regex matching alone can miss related capabilities whose names/descriptions use different terms. The future review needs semantic inspection as well as automated triage, especially for memory, feedback and learning skills.

### Why exactly 13?

Thirteen is the size of the authored batch chosen for the first experiment. There are 13 corresponding task suites and evaluation reports. There is no evidence of 134 skills being evaluated and reduced to 13, no demonstrated one-to-one mapping from 13 source skills to the authored set, and no recorded comprehensive exclusion rationale for the rest. It would therefore be incorrect to describe the remaining 121 upstream skills as "rejected."

## 3. Coverage of the six requested areas

Results below come from the local registry and evaluation reports. A skill can belong to more than one area; `ui-anti-slop` appears twice.

| Requested area | Authored and evaluated | Admitted | Rejected |
|---|---|---|---|
| UX | ux-flows, accessibility, ui-content, ui-anti-slop | ux-flows, ui-anti-slop | accessibility, ui-content |
| Architecture | architecture-options, api-design, build-approach | All three | None |
| De-slop | code-hygiene, prose-anti-slop, ui-anti-slop | prose-anti-slop, ui-anti-slop | code-hygiene |
| Scrub | scrub | scrub | None |
| Dreams / self-learning | dreams | dreams | None |
| Research / analyst | web-research, analyst | Both | None |

Admission used five tasks per skill, paired with/without answers from the same generator, and blind scoring by a separate judge. The final gate required quality lift of at least 10 percentage points, token overhead below 20% against the configured 50,000-token reference call, at least three wins or ties, and no loss worse than one point. The tie rule changed after results were seen. See the [experiment report](phase-9-skill-micro-eval.md) for scores, models, costs and limitations.

These results measure the authored text, not the upstream originals. Rejection also does not mean a capability is unimportant: accessibility, UI content and code hygiene still matter; their tested instructions did not clear this particular gate.

## 4. Relevant source candidates not accounted for by that experiment

The following is an **index/tree-level follow-up shortlist**, not a completed skill-body evaluation or a claim of functional equivalence. Names refer to source directory names at the pinned commit. Thematic overlap with an authored skill is not proof that its detailed procedures, references, scripts or acceptance checks were retained.

| Area | Source capabilities requiring an explicit disposition | Current evidence gap |
|---|---|---|
| UX | design-system-reasoning, impeccable-integration, brand-spec-extraction, prototype-craft, frontend-ui, working-prototype-app, prototype-audit, usability-heuristics, visual-regression | No separate local candidate/eval for these. ux-flows and ui-anti-slop cover some themes, but no capability-level mapping proves coverage of these nine additional design skills. Source ux-ui-design, accessibility, content-design and anti-slop have clearer thematic counterparts in the authored batch, not verified equivalence. |
| Architecture | core-principles, security, performance, database, cost-analysis, infra-governance; diagram-as-code; relevant low-code platform skills | Local API design, option comparison and build-approach advice do not establish coverage of these specialist capabilities. Source api-design and low-code-vs-pro-code have thematic counterparts. Platform-specific relevance still needs a scope decision, not automatic inclusion. |
| De-slop | code-optimization, karpathy-guidelines, impeccable-integration, prototype-audit | No separate local evaluation of these approaches. Source code-hygiene, no-ai-slop and anti-slop align thematically with the three authored de-slop candidates; the local code-hygiene candidate was rejected. |
| Scrub | scrub; potentially complementary security-testing, configuration and security capabilities | An authored scrub skill exists and passed. No source-to-local checklist proves preservation of all source scrub behavior, and adjacent secret/configuration checks have not been evaluated as part of this batch. |
| Dreams / self-learning | agent-memory-systems, feedback-loops, cognitive-architecture, context-management, experimentation-loop, iterative-loop | No source skill named dreams appears in the checked inventory, but several related capabilities do. The bespoke dreams skill does not demonstrate that memory consolidation, feedback or experimentation alternatives were evaluated. |
| Research / analyst | browser-automation, iterative-retrieval, data-analysis, computer-use-and-browser-agents; domain-specific skills where relevant | web-research and analyst passed as authored, tool-less answer instructions. That does not test browser-based retrieval, iterative evidence gathering or actual data-analysis execution. No separate evaluation of these upstream candidates is recorded. |

**Correction to the earlier source characterization:** D-037's statement about no dreams counterpart and only a browser-automation research skill must not be read as "no related learning or research capabilities exist." The current source includes the adjacent capabilities above. This audit does not establish which were available in the unpinned original review or that all should be admitted.

## 5. Work required before claiming exhaustive relevant coverage

1. Persist a source manifest from the pinned repository tree, with all 134 paths, source revision and review status. Do not use the incomplete pipe index as the sole inventory.
2. Review every source skill for the six requested areas, including cross-category capabilities. Record one explicit disposition per skill: candidate, covered with a linked capability mapping, out of scope with a reason, blocked by a dependency/license/runtime constraint, or pending review. "Not reviewed" is not "rejected."
3. Preserve the static scan/triage output and manually check regex misses. Distinguish source originals from authored adaptations and document what is retained, omitted or replaced.
4. Evaluate additional in-scope candidates with independent tasks; use tool-enabled checks where browser operation, file changes, data execution or persistent learning are part of the capability. Keep source review, evaluation and admission as separate statuses.
5. Publish the resulting coverage matrix and link each admission/rejection to its report. Continue loading only a relevant budgeted subset per task; a larger evaluated library does not require loading all of it.

These are outstanding actions, not completed work. This audit added documentation only: no new skill bodies were imported or authored, no model evaluations were run, and no admission decisions or load budgets were changed.

## 6. Update: positioning, full static screen and next step (later on 2026-10-07)

### 6.1 Positioning: why a small first batch

- **Scope was chosen by the user, not filtered by quality.** The first batch covered the six areas the user asked for (UX, architecture, de-slop, scrub, dreams/self-learning, research). The other source skills were not reviewed then; they were not rejected. "Not reviewed" is a scope decision, not a judgement.
- **Two designs, two loading models.** The source library is built for a role-based fleet: a router (`Skills.md`) points each role at the few skills it needs, and each skill is a complete knowledge package (median 1,840 tokens, up to 4,700; rich descriptions for routing). Frontier HVE runs inside a single Copilot chat, where every discoverable skill costs every request. The harness therefore treats skills as a library that must earn its place with measured lift and is loaded per task within a budget. The source skills' depth is a strength in their design; it only needs a different loading path here.
- **Build from scratch, keep the best.** Frontier HVE was built small on purpose, by a co-contributor of the source project, to keep the harness lean and evidence-driven. The first batch tested the approach (author short, measure lift, load per task); it worked: 10 of 13 passed. The next step brings the source skills over as they are and lets the same evidence decide.

### 6.2 Full static screen of all 134 source skills

Every `SKILL.md` at the pinned commit was screened with `tools/skills/scan.py` and the category matcher, with no model calls. One disposition per skill is persisted in [phase-9-source-skill-manifest.json](phase-9-source-skill-manifest.json) (path, size, scan result, scripts, source-runtime references, categories, authored counterpart, disposition, evaluation status).

| Disposition | Skills | Meaning |
|---|---:|---|
| Tier 1: requested area | 33 | Scan passes, matches one of the requested areas, self-contained |
| Tier 1, with scripts or source-runtime steps | 5 | As above, but PowerShell scripts or `.frontier` runtime steps that this harness does not ship; the instructions can still be evaluated |
| Tier 2: outside requested areas | 62 | Scan passes; AI systems, data, languages, infrastructure, low-code, domains and similar: a scope decision is needed, not a quality one |
| Tier 2, with scripts or source-runtime steps | 10 | As above, with scripts or runtime steps |
| Review: scanner flag | 24 | The conservative scanner flagged strings such as destructive commands, secret patterns, URLs or fetch calls. Most are expected in security, DevOps and language skills that teach those topics; each needs a human look, not a rejection |

Other facts from the screen: 110 of 134 pass the scan; 17 ship PowerShell scripts; 24 reference the source runtime; no skill is under the 800-token limit set for short authored skills, and 53 are over 2,000 tokens; 128 have descriptions over 200 characters. Ten source skills have an authored counterpart in the first batch (for example `accessibility`, `scrub`, `api-design`).

The registry caveat in section 1 is fixed: rejected entries now carry `status: "rejected"`.

### 6.3 Next step (agreed with the user): copy, do not rewrite, and evaluate

1. Copy source skills verbatim into an imported library (`skills/imported/agentx/`), with the source `LICENSE` and `NOTICE` kept beside them (Apache-2.0 attribution; files unmodified).
2. Imported skills are never discoverable and never always-on. They are ranked per task like the rest of the library. A skill larger than the loadout budget (2,000 tokens) cannot auto-load; it is offered, ranked, and loads only when the user ticks it.
3. Evaluate with the same micro paired method and gate, in tiers by token budget: tier 1 first (38 skills), then tier 2 by user priority; scanner-flagged skills after a human look. The ten with authored counterparts are compared on the same tasks, so the better version wins on evidence.
4. Record each result in the manifest (`evaluation`) and the registry, so coverage is always visible: reviewed, evaluated, admitted, rejected, or not in scope.

### 6.4 Imported untested (later on 2026-10-07): 27 skills admitted with evaluation pending

- **What was imported.** 27 skills, copied verbatim to `skills/imported/agentx/<group>/<name>/` with the source `LICENSE` and `NOTICE`: the 26 tier-1 skills without an authored counterpart or scripts, plus `karpathy-guidelines` (tier 2, added by the user). Sizes 947-4,552 tokens, 51,908 in total. Tool: `python tools/skills/import_eval.py untested <clone> karpathy-guidelines`.
- **Gate that was defined but not run (strict import gate).** 3 tasks per skill drafted by `gpt-5.2-chat` from the name and description only; paired with/without answers from `gpt-5.4-mini`; blind judge `gpt-5.2-chat`. Admission requires the micro gate (lift >= 10 pp, overhead < 20%) **and** a win on every task **and** a one-sided exact sign test on check-level gains vs losses with p < 0.05 (at least 5 net check gains with no losses). Estimated cost about 0.4-0.5M tokens for the 27.
- **Why it did not run.** The Foundry endpoint failed intermittently from this machine: local DNS (75.75.75.75) often did not resolve `*.cognitiveservices.azure.com` (`getaddrinfo` 11001/11002), and connections that did resolve were reset (`WinError 10054`, SSL EOF). Ten attempts and a pinned-IP run failed before the first task was drafted; no tokens were spent on the evaluation. Per the user, attempts stopped and the skills were admitted untested.
- **What "admitted untested" means.** `onboard.py <dir> <source> untested`: scan and category checks only; registry status `provisional` with `evaluation: "pending"`; the manifest's `evaluation` field says so for each of the 27. They load like other provisional skills: ranked per task by `recommend.py` for HVE agents (`HARNESS_SKILLS_MIN_STATUS=provisional`), never for research agents (`admitted`). They are never discoverable and never always-on, so they add no tokens to requests that do not need them. Every one is above the 800-token provisional limit and most are near or above the 2,000-token loadout, so in practice they are offered for the user to tick rather than loaded automatically.
- **Example.** Prompt "think before coding and make surgical changes to simplify this function": loaded `prose-anti-slop`, `ui-anti-slop` (777 tokens, both admitted); offered `karpathy-guidelines`, `code-optimization`, `prototype-audit`.
- **Upstream defect found.** The only Python script among the 27, `development/documentation/scripts/generate-readme.py`, does not compile at the pinned commit (indentation flattened to one space). It is kept verbatim; the extension build now compiles harness code only, not skill scripts. Worth reporting upstream.
- **Risk.** Provisional skills can be loaded without measured lift. Until the strict gate runs, they rank below admitted skills and above nothing else; the user decides when to tick the large ones.
- **Open issue.** Tracker `N26`: run `python tools/skills/import_eval.py eval "%TEMP%\agentx-src" karpathy-guidelines` when the endpoint is reachable; skills that fail are moved to `rejected` by the same command.
