---
name: prose-anti-slop
description: Edit prose to remove AI slop - filler openers, hedging, inflated adjectives, reflexive lists of three, false balance - while keeping the author's voice and every fact.
---

# Prose anti-slop

Use on READMEs, docs, release notes, UI help text and replies. Edit, do not rewrite: the author's voice and facts stay.

Remove or fix:
- **Filler openers and closers**: "In today's fast-paced world", "It's worth noting that", "In conclusion", "I hope this helps".
- **Hedging stacks**: "may potentially help to somewhat improve" -> "improves" (or state the real uncertainty once).
- **Inflated words**: seamless, robust, cutting-edge, leverage, delve, unlock, empower, game-changing, comprehensive. Use the plain word or a measured fact.
- **Reflexive lists of three** and parallel slogans that add rhythm but no information.
- **False balance**: "While X has benefits, Y also has merits" when the text should give a recommendation.
- **Restating the question** before answering it; summaries that repeat the paragraph above.
- **Vague claims**: "significantly faster" -> the number and how it was measured, or remove.
- **Formatting noise**: bold on every other phrase, headings for two-line sections, emoji bullets.

Keep: domain terms the reader needs, the author's examples, every number and citation.

Mode: if asked only to detect, list each instance with its line and the rule, and change nothing. If asked to edit, return the edited text plus a short list of the changes by rule.
