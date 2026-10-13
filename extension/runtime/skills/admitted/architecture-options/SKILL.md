---
name: architecture-options
description: Compare 2-3 architecture options with trade-offs on cost, risk, scale, team skills and licensing, then record the chosen design as an ADR before building.
---

# Architecture options

Use when a request involves a new service, datastore, integration, hosting choice or anything hard to reverse.

1. **Drivers**: list the 3-5 forces that matter for this decision (expected users and data volume, latency, compliance and data residency, budget, team skills, time to first release).
2. **Options**: describe 2-3 genuinely different options in two sentences each. Always include the simplest one that could work and, where relevant, a managed enterprise service (for example Azure-hosted) instead of a self-built component.
3. **Trade-off table**: one row per option, columns = drivers plus monthly run cost at expected and 10x load, operational burden, lock-in, licensing. Mark unknowns as unknown; do not invent numbers.
4. **Decide**: pick one, say why in one paragraph, and name what would make you revisit the choice (a trigger, not a date).
5. **Record an ADR** in `docs/adr/NNNN-<slug>.md`: context, decision, options considered, consequences (good and bad), status.
6. **Boundaries**: name the modules and their single responsibility, the data each owns, and the interfaces between them. No module reads another's storage directly.
7. **Turn into features**: the first feature proves the riskiest assumption (an integration or the data model), not the easiest screen.

If the decision needs real users, real data or production scale, recommend a solution architect review before building further.
