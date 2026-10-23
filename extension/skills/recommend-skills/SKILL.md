---
name: recommend-skills
description: Rank the Frontier HVE skill library for the current task, show every skill that loads and why, and flag a load over the loadout guideline.
---

# Recommend skills

The library skills are not loaded into every chat (that would add their descriptions to every request). The HVE agents' skill loader picks them per task: every skill whose category or keywords match, ranked by relevance, whatever its status. Nothing is dropped silently: over 10 skills or 32,000 tokens the agent scores the shortlist for the ask and asks the user to keep the suggested top 10, all, or named skills.

1. Run `python <tools>/skills/recommend.py provisional "<the task in one or two sentences>"` (`<tools>` is the harness tools folder named in your agent instructions).
2. Show a ranked table: rank, skill, reason (required, category or keyword), status, tokens, measured lift.
   - `provisional`: passed the static gate (security scan, size, category); quality lift not yet measured.
   - `admitted`: paired with/without-skill evaluation showed at least 10 points quality lift with under 20% token overhead.
3. If `over_budget` is true, say in one line that the load exceeds the guideline and costs context on every turn of this task, and offer `suggested` (the required skills plus the most relevant per token that fit the guideline, `suggested_tokens` tokens). Ask once: suggested, all, or named skills; inside an ask run `lifecycle.py skills suggested|all|<a,b>`, which records the choice, the tokens over the guideline, and later how much of the prompt was cached.
4. Cite the evidence once: SkillsBench (https://www.skillsbench.ai, arXiv 2602.12670) found curated skills raise agent pass rates by 16.6 points on average and that focused skills beat large bundles; this harness measures its own skills with the same paired method.
