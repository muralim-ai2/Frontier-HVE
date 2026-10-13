# Visio Interop

> **Parent skill**: [diagrams/diagram-as-code](../SKILL.md)
> **Use when**: deliverable must be viewable or editable in Microsoft Visio (`.vsdx`) by stakeholders who do not use diagram-as-code tools.

---

## Round-Trip Matrix

| Source format | Path to `.vsdx` | Path from `.vsdx` | Fidelity |
|---------------|-----------------|-------------------|----------|
| **draw.io / diagrams.net** | File -> Export as -> Advanced -> VSDX | File -> Import -> select `.vsdx` | **High** (native converter) |
| **Mermaid** | Visio for the web -> Insert -> Visualizer -> Mermaid paste | n/a | Medium (flow, sequence, ER only) |
| **PlantUML** | Export SVG -> Import into draw.io -> Export `.vsdx` | n/a | Medium (shapes become generic) |
| **BPMN (bpmn.io)** | Export XML -> Import via draw.io BPMN shapes -> Export `.vsdx` | n/a | Medium |
| **Graphviz DOT** | Export SVG -> Import into draw.io -> Export `.vsdx` | n/a | Low-medium (loses semantic shape types) |

Recommendation: if Visio is a hard requirement, **author in draw.io** and export `.vsdx` as a deliverable. Everything else is a workaround.

---

## Path 1: draw.io -> `.vsdx` (recommended)

1. Author diagram in draw.io (desktop, web, or VS Code extension "Draw.io Integration")
2. Save `.drawio` file in git alongside the artifact
3. Export: `File -> Export as -> Advanced -> VSDX`
4. Commit both `.drawio` (source) and `.vsdx` (export) to the same folder
5. Update handoff: share the `.vsdx` with Visio users; require edits to come back via the `.drawio` source

Caveat: custom shapes from Visio stencils (e.g., network-gear stencil, Azure stencil) may render as generic shapes in draw.io after round-trip. Use draw.io's built-in Azure / AWS / CFF shape libraries instead for best fidelity.

---

## Path 2: Mermaid -> Visio for the web

1. In Visio for the web, open a blank diagram
2. `Insert -> Visualizer -> From Mermaid`
3. Paste Mermaid source; Visio renders native shapes
4. Supported: flowchart, sequence, ER (as of 2025-2026; check Visio release notes)
5. Not supported: C4, gantt, journey, state (v2), mindmap

Use this when stakeholders edit in Visio for the web and the diagram is a flowchart or sequence.

---

## Path 3: PlantUML -> draw.io -> `.vsdx`

1. Render PlantUML to SVG (`plantuml -tsvg`)
2. Open SVG in draw.io (`File -> Import`)
3. Export as `.vsdx`
4. Shapes will be generic rectangles/arrows; no UML semantic preservation

Use only when PlantUML is the existing source of truth and a one-off `.vsdx` is needed.

---

## File Naming and Storage

Co-locate source and export:

```
docs/artifacts/adr/ADR-42/diagrams/
  ADR-42-context.drawio          <- source (committed)
  ADR-42-context.vsdx            <- export (committed when needs:visio)
  ADR-42-context.svg             <- preview (optional)
```

Rule: the `.drawio` (or other text source) is the source of truth. The `.vsdx` is a build artifact -- regenerate rather than edit.

---

## When NOT to Use Visio

- CI-rendered diagrams embedded in markdown docs -> use Mermaid, render inline
- ADR/spec diagrams reviewed in PRs -> use Mermaid or PlantUML, diff-friendly
- Legacy `.vsdx` files from a Visio-first org -> **convert once** (import into draw.io), then maintain as `.drawio` going forward

Only ship `.vsdx` when the consumer explicitly requires it (legal, executive decks, external stakeholders).
