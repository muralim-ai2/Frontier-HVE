---
name: oracle-performance-tuning
description: Oracle performance tuning from AWR and execution plans - top SQL, wait events, index and statistics fixes, verified before and after.
---

# Oracle performance tuning

1. Start from evidence: an AWR or ASH extract, or execution plans in the workspace. No tuning without a measured baseline.
2. Rank by impact: top SQL by elapsed time, then the dominant wait events.
3. Change one thing at a time (index, statistics, rewrite, hint as a last resort) and re-measure with the same workload.
4. Save before and after measurements to `.harness/evidence/<feature>/` and keep the change only if it improves the baseline.
