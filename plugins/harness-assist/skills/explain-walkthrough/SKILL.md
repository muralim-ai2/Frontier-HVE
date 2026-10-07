---
name: explain-walkthrough
description: Explain what is being built and the concepts involved (frontend, API, middleware, data, PRs, CI) at the user's technical level, and recommend which experts to involve before moving from prototype to production.
---

# Explain walkthrough

## 1. Know the level
Use `technical_level` from the session context (`executive`, `partial`, `developer`). If it is unknown, ask once with the ask-questions tool:
- `header`: `technical-level`
- `question`: `How technical should explanations be? [profile: .hve/user_profile.json]`
- options (single choice), `label` exactly: `executive` (business view, no code), `partial` (TPM or architect: concepts, some code), `developer` (deeply technical).
A plugin hook saves the answer to the profile.

## 2. Walk through (executive and partial)
Keep it to one screen:
1. **What we are building** in one sentence and who uses it.
2. **How the parts fit**: what the user sees (frontend), what does the work (backend/API), what connects systems (middleware, queues, integrations), where data lives, where it runs (hosting).
3. **Where we are**: prototype, pilot or production, and what is still missing for the next step.
4. **New terms used today**, one line each (for example: "A pull request (PR) is a proposed change that a reviewer approves before it joins the product.").
For `developer`, skip this and give only decisions and trade-offs.

## 3. Recommend experts
When the work moves beyond a prototype (real users or data, integrations, scale, security, compliance, licensed services), recommend involving:

| Need | Expert |
|---|---|
| Screens, usability, accessibility | UI/UX designer, frontend developer |
| APIs, data models, integrations | Backend or full-stack developer |
| Models, evaluation, data quality | Data scientist |
| LLM, retrieval, OCR, agents | AI engineer |
| Choice of platform and licensed services | Solution architect |
| Hosting, pipelines, monitoring | DevOps / platform engineer |
| Authentication, data protection | Security engineer |

Say why each is needed in one line. Never present a prototype as production-ready.
