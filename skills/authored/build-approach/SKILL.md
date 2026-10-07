---
name: build-approach
description: Choose no-code, low-code or pro-code per component, with trade-offs on fit, scale, governance, licensing and skills, then recommend the platform and the experts to involve.
---

# Build approach: no-code, low-code or pro-code

Decide per component (form, workflow, data store, API, AI feature), not for the whole product.

| Signal | Leans no-code / low-code (for example Power Apps, Power Automate, Copilot Studio) | Leans pro-code |
|---|---|---|
| Users | Internal, tens to hundreds | External or thousands+ |
| Logic | Forms, approvals, CRUD over business data | Custom algorithms, real-time, heavy compute |
| Integration | Standard connectors exist | Custom protocols, high throughput |
| Change | Business owners change it often | Engineers own a release process |
| Governance | Tenant policies and DLP already in place | Needs custom security, audit or residency controls |
| Cost | Per-user licensing acceptable | Usage-based hosting cheaper at scale |
| Skills | Makers and analysts | Developers available to maintain it |

Steps:
1. Score each component against the table; record the leaning and the one deciding factor.
2. Hybrid is normal: low-code front end over a pro-code API, or pro-code app calling a low-code approval flow.
3. Name hidden costs: licensing per user, connector limits, export and lock-in, testing and source control for low-code assets, maintenance ownership.
4. Prototype in the fastest approach, but state plainly which components must move to pro-code (or a managed service) before production.
5. Recommend experts: a Power Platform or low-code architect for governance and licensing; a solution architect when components span both worlds; security for anything holding customer data.
