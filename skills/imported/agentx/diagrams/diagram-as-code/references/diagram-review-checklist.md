# Diagram Review Checklist

> **Parent skill**: [diagrams/diagram-as-code](../SKILL.md)
> **Use when**: reviewing a diagram-bearing artifact (PRD, ADR, spec, UX flow) or during the Diagram Specialist self-review.

---

## Universal Checks (all diagrams)

- [ ] **Source is text** -- `.mmd`, `.puml`, `.dsl`, `.dot`, or `.drawio` (not a raw image)
- [ ] **Format matches intent** -- checked against decision matrix in [SKILL.md](../SKILL.md)
- [ ] **Title** present (in header comment or diagram body)
- [ ] **Legend** for any non-default color, shape, or line style
- [ ] **Source-of-truth link** -- header cites the parent artifact (PRD-/ADR-/SPEC- issue)
- [ ] **Renders cleanly** in the target surface (tested, not assumed)
- [ ] **ASCII only** -- no emoji, no Unicode symbols
- [ ] **Consistent naming** -- node labels use the same terminology as the parent artifact

## Swimlane / CFF Specific

- [ ] Format supports native lanes (PlantUML activity beta, draw.io CFF, or BPMN)
- [ ] Every activity is in exactly one lane (no lane-spanning shapes)
- [ ] Phase bands are ordered and named
- [ ] Start and end nodes are explicit (distinct shapes)
- [ ] Handoff arrows carry action labels ("Send draft", not bare arrow)
- [ ] Lane count <= 7
- [ ] Phase count <= 6

## C4 Specific

- [ ] One level per diagram (no mixing context with container or component)
- [ ] Every element has a one-sentence responsibility
- [ ] Every relationship has a verb + protocol ("JSON/HTTPS", "gRPC", "reads")
- [ ] External systems are styled distinctly from internal

## Sequence Specific

- [ ] `autonumber` enabled (reviewers can cite step N)
- [ ] Every arrow carries an action and payload/error
- [ ] Alt/opt/loop blocks used for conditional flows
- [ ] Participants ordered left-to-right in call order

## State Specific

- [ ] Initial state marked (`[*] -->`)
- [ ] Terminal states marked (`--> [*]`)
- [ ] Every transition labeled with the triggering event
- [ ] No orphan states (every state is reachable and exits)

## ER Specific

- [ ] Cardinalities are correct and match the spec (`||--o{`, `}o--||`, etc.)
- [ ] Keys marked (PK / FK)
- [ ] Entity names use domain nouns (not table names if different)

## Network / Topology Specific

- [ ] Boundaries (VPC, subnet, region) drawn as clusters/subgraphs
- [ ] Direction of traffic indicated on edges
- [ ] External entry points (Internet, users) at top or left
- [ ] Security boundaries (firewalls, WAF, IAM) are visible

## Visio Interop (when `needs:visio` is set)

- [ ] `.vsdx` export co-located with source file
- [ ] Conversion path documented ("authored in draw.io, exported to VSDX")
- [ ] Round-trip tested (opened the `.vsdx` in Visio after export)

## Review Verdict

- **APPROVED** if all applicable checks pass
- **REJECTED** if any MUST rule from the parent skill is violated
- **CHANGES REQUESTED** for violations of diagram-type-specific checks above
