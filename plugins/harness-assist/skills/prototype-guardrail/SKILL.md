---
name: prototype-guardrail
description: Stop a vibe-coded prototype from growing into an unmanageable or non-enterprise system - flags code over 5,000 lines, open-source components where licensed enterprise services are expected (for example FalkorDB, Tesseract, SQLite, local vector stores), and self-built infrastructure, then recommends a solution architect and a complexity report.
---

# Prototype guardrail

1. Run `python <plugin root>/scripts/guardrail.py <project folder>` (the plugin root is two folders above this file). It returns JSON: `code_lines`, `largest_files`, `flagged` components with their enterprise alternative, `infrastructure_files`, `verdict`, `reasons`, `experts`. The HVE agents also run it after each tool call in harness projects and warn once per new finding.
2. If `verdict` is `ok`, continue.
3. If `verdict` is `review`:
   - Stop adding features, components or infrastructure.
   - Tell the user, at their technical level: what was found, why it matters (licensing, support, security, scale, data residency), and the enterprise alternative for each flagged component (for example Azure AI Search instead of a local vector store, Azure AI Document Intelligence instead of Tesseract).
   - Recommend the listed experts, always including a solution architect when components or infrastructure are flagged.
   - Offer a complexity report. With the user's yes, write `complexity_report.json` in the project root: current architecture (components and how they connect), each flagged item with risk and enterprise alternative, size hot spots, open questions for the architect, and a suggested next step. For deeper comparison of options, use a stronger research model or the researcher skill if it is admitted.
4. Continue only with the user's decision. Do not swap components yourself without it.

Thresholds and the component catalogue live in `scripts/enterprise_catalog.json`; change them there, not in code.
