---
name: explain-walkthrough
description: Explain what is being built and the concepts involved (frontend, API, middleware, data, PRs, CI) at the depth that suits the user, and recommend which experts to involve before moving from prototype to production.
---

# Explain walkthrough

## 1. Know the depth
Use the explanation depth from the session context (`guided`, `balanced`, `expert`). It is inferred from how the user works; adapt silently and never label, classify or quiz the user about their skills. If no depth is known, ask once with the ask-questions tool:
- `header`: `build-preference`
- `question`: `How do you prefer to build? [profile: .hve/user_profile.json]`
- options (single choice), `label` exactly: `no code` (describe the outcome, the agent writes the code), `low code` (read and adjust code with guidance), `pro code` (write and review code yourself).
A plugin hook saves the answer as the starting point; the depth keeps adjusting to how the user actually works.

## 2. Walk through (guided and balanced)
Keep it to one screen:
1. **What we are building** in one sentence and who uses it.
2. **How the parts fit**: what the user sees (frontend), what does the work (backend/API), what connects systems (middleware, queues, integrations), where data lives, where it runs (hosting).
3. **Where we are**: prototype, pilot or production, and what is still missing for the next step.
4. **New terms used today**, one line each (for example: "A pull request (PR) is a proposed change that a reviewer approves before it joins the product.").
For `expert`, skip this and give only decisions and trade-offs.

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
