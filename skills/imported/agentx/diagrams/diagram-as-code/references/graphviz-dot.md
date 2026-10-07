# Graphviz DOT Patterns

> **Parent skill**: [diagrams/diagram-as-code](../SKILL.md)
> **Use when**: rendering dependency graphs, call graphs, network topologies, or any diagram driven from machine-generated data.

---

## Dependency Graph

```dot
digraph deps {
  rankdir=LR;
  node [shape=box, style=rounded];
  "web" -> "api";
  "api" -> "db";
  "api" -> "esign" [label="REST"];
  "esign" [shape=box, style="rounded,dashed"];  // external
}
```

## Network Topology

```dot
digraph net {
  rankdir=TB;
  subgraph cluster_vnet {
    label="Azure VNet";
    "App Gateway" -> "App Service";
    "App Service" -> "Azure SQL";
    "App Service" -> "Key Vault";
  }
  "Internet" -> "App Gateway";
}
```

## Call Graph

```dot
digraph calls {
  rankdir=LR;
  "Controller" -> "Service";
  "Service" -> "Repository";
  "Repository" -> "DB";
}
```

## Rendering

- `dot -Tsvg file.dot -o file.svg`
- VS Code "Graphviz (dot) language support" extension renders inline
- Import SVG to draw.io for Visio export

## Tips

- Prefer DOT over Mermaid when the graph is generated from code (easy to emit)
- Use `rankdir=LR` for left-to-right dependency flow, `TB` for trees
- Apply `cluster_*` subgraphs for grouping (VPCs, namespaces, layers)
- Keep nodes <= 50; beyond that, pre-filter or break into sub-graphs
