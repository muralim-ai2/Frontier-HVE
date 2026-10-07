---
name: recommend-skills
description: Rank the Frontier HVE skill library for the current task, show what is loaded within the loadout budget and what else is relevant, and let the user tick extra skills to load.
---

# Recommend skills

The library skills are not loaded into every chat (that would add their descriptions to every request). The creator agents' skill loader picks them per task: the most relevant first, up to 10 skills and 2,000 tokens. Anything over that budget is offered, not loaded.

1. Run `python <tools>/skills/recommend.py provisional "<the task in one or two sentences>"` (`<tools>` is the harness tools folder named in your agent instructions).
2. Show a ranked table: rank, skill, loaded or offered, status, tokens, measured lift.
   - `provisional`: passed the static gate (security scan, size, category); quality lift not yet measured.
   - `admitted`: paired with/without-skill evaluation showed at least 10 points quality lift with under 20% token overhead.
3. If skills are offered over the budget, ask with the ask-questions tool: `header` `load-skills`, multi-select, `label` = skill name, `description` = why it fits and its token cost. Say that loading more costs context on every turn of this task. Only ticked skills load (a hook adds them); never read an unticked library skill.
4. Cite the evidence once: SkillsBench (https://www.skillsbench.ai, arXiv 2602.12670) found curated skills raise agent pass rates by 16.6 points on average and that focused skills beat large bundles; this harness measures its own skills with the same paired method.
