# Requirements Quality: Vague vs Concrete

> **Modified** by Frontier HVE on 2026-10-12 from AgentX `fc39b29` (Apache-2.0): section-number references replaced with requirement IDs; links to files outside this skill removed; the AI product contract and consumer checklist moved here from SKILL.md.

> **Parent skill**: [PRD](../SKILL.md)
> **Purpose**: Catalogue of vague-requirement anti-patterns and the concrete rewrites that replace them.
> **Rule**: Every functional and non-functional requirement must be rewritable as a test. If you cannot write a test for it, it is not a requirement.

---

## The Test

Ask of every requirement: *"What would I assert in a test to prove this is satisfied?"*

If the answer is a number, a named standard, a reference dataset, or a schema -- the requirement is concrete.
If the answer is "well, it should feel right" -- the requirement is vague and MUST be rewritten before the PRD ships.

---

## Anti-Pattern Catalogue

### Performance

| Vague | Concrete |
|-------|---------|
| "The app should be fast." | "API p95 latency <= 200ms at 500 RPS for the endpoints in FR-4 to FR-6." |
| "The UI should feel snappy." | "First Contentful Paint <= 1.5s on a 4G Slow connection measured by Lighthouse CI." |
| "Queries should return quickly." | "SELECT queries on the `orders` table return within 100ms p99 for datasets up to 10M rows." |

### Usability

| Vague | Concrete |
|-------|---------|
| "The UI must be easy to use." | "80% of test participants in the 10-person usability study complete the checkout task in <=60s without assistance." |
| "It should look modern." | "UI conforms to the team's design system. Visual regression tests pass with <=1% pixel delta." |
| "Must be accessible." | "WCAG 2.1 AA compliance verified by axe-core in CI; manual screen-reader smoke test passes on NVDA and VoiceOver." |

### Security

| Vague | Concrete |
|-------|---------|
| "The system should be secure." | "Endpoints require OAuth 2.1 bearer tokens. Secrets stored in Azure Key Vault. OWASP Top 10 ZAP scan passes in CI with zero High/Critical findings." |
| "Data must be protected." | "PII encrypted at rest with AES-256 and in transit with TLS 1.3. Field-level encryption for SSN and DOB columns." |
| "Handle sensitive data carefully." | "All PII access is logged to the audit table with actor, resource, action, and timestamp. Logs retained 7 years per SOC 2 control X.Y." |

### Reliability

| Vague | Concrete |
|-------|---------|
| "The service should be reliable." | "99.9% monthly uptime measured against the public status page. Error budget of 43 minutes per month." |
| "Errors should be handled gracefully." | "Transient failures retry with exponential backoff (base 200ms, max 3 attempts). Permanent failures surface a documented user-facing error code." |

### AI / ML

| Vague | Concrete |
|-------|---------|
| "The AI should give good answers." | "Responses achieve >=4.2/5 on the team's correctness rubric over 50 held-out queries in the regression dataset." |
| "Minimize hallucinations." | "Faithfulness score (RAGAS) >= 0.85 on the eval set. Any answer with retrieval confidence < 0.6 falls back to 'I don't know, here are related docs'." |
| "The agent should be safe." | "Input and output pass the Azure AI Content Safety filter at the `medium` threshold. Off-topic queries are refused with the fallback message defined in FR-9." |
| "The model should be fast." | "p95 end-to-end latency <= 4s for responses up to 500 tokens on the pinned model version." |

### Scope / Completeness

| Vague | Concrete |
|-------|---------|
| "Support common file formats." | "Support CSV (RFC 4180), JSON (RFC 8259), and Parquet (v2.9+). Other formats are out of scope." |
| "Integrate with major providers." | "Integrate with Microsoft Foundry, OpenAI, and Anthropic. Additional providers are out of scope for this PRD." |

### Business Metrics

| Vague | Concrete |
|-------|---------|
| "Improve conversion." | "Checkout conversion rate increases from 2.1% to 2.5% (measured over a 14-day A/B test with >=5000 visitors per arm, p < 0.05)." |
| "Reduce support load." | "Tickets tagged `billing-question` decrease by 30% within 60 days of launch vs. the 60-day baseline." |

---

## Red Flags -- Reject Before Review

If any PRD requirement contains one of these words *without* an attached numeric or named-standard qualifier, it is vague:

`fast`, `slow`, `easy`, `hard`, `intuitive`, `modern`, `clean`, `nice`, `good`, `bad`, `better`, `smart`, `simple`, `complex`, `robust`, `scalable`, `flexible`, `seamless`, `smooth`, `powerful`, `user-friendly`, `high-quality`.

Also reject:
- "as needed", "when appropriate", "if possible", "where reasonable"
- "industry-standard" with no named standard cited
- "best practices" with no specific practice referenced

---

## The Rewrite Protocol

When a vague requirement is found:

1. Identify the **observable outcome** the user actually wants.
2. Attach a **metric**: number, range, named standard, rubric, or eval dataset.
3. Attach a **measurement method**: which test, which tool, which environment, which dataset.
4. Attach a **boundary**: at what p-value, at what load, over what window, on what percentile.
5. If you cannot fill steps 2-4, the requirement is not a requirement -- it is an open question. List it with an owner.

---

## AI-Bearing PRDs: Product-Facing Contract

If any requirement involves AI (LLM, agent, RAG, classification, generation), specify it at the product-facing contract layer, not implementation:

| Field | What to capture |
|-------|----------------|
| Primary AI Job | The user-visible reasoning, generation, classification or decision task |
| Grounding Sources | Docs, knowledge bases, APIs, databases, or "none / model prior only" |
| Tool / Action Boundaries | What the AI may read, write or trigger; what it MUST NOT do autonomously |
| Response Contract | Free-form text, structured JSON, citations or an action plan |
| Fallback Behavior | What happens when confidence is low, retrieval fails or the model is unavailable |
| Human Review Trigger | When a human must approve, edit or confirm before completion |
| Quality Threshold | A numeric metric and the evaluation dataset it is measured on |

Design and engineering turn this into the implementation spec; the PRD must not leave them guessing.

---

## Consumer Checklist

Before building, designing or testing from a PRD:

- [ ] The problem is specific and has evidence
- [ ] At least one success metric is numeric with a window
- [ ] Every P0 requirement has an ID and testable acceptance criteria
- [ ] Non-goals are explicit
- [ ] If AI-bearing, the AI product contract is complete
- [ ] No constraint contradicts the user's intent
- [ ] Open questions are listed rather than silently assumed

If any check fails, push back to the PRD owner rather than inventing the missing requirement.

---

## See Also

- [PRD SKILL.md](../SKILL.md)
