# PlantUML Patterns

> **Parent skill**: [diagrams/diagram-as-code](../SKILL.md)
> **Use when**: need strong UML semantics, swimlane activity flows, or when rendering via PlantUML server / VS Code extension.

---

## Activity (beta) with Swimlanes

See [swimlane-patterns.md](swimlane-patterns.md) for the full swimlane pattern. Quick form:

```plantuml
@startuml
|Client|
start
:Submit request;
|Attorney|
:Draft;
|Client|
:Sign;
stop
@enduml
```

## Sequence

```plantuml
@startuml
autonumber
actor User
participant API
database DB
User -> API : POST /contracts
API -> DB : INSERT
DB --> API : id=123
API --> User : 201 {id:123}
@enduml
```

## Component

```plantuml
@startuml
package "CLM Platform" {
  [Web UI]
  [Contract Service]
  [Approval Engine]
  database "Contracts DB"
}
[Web UI] --> [Contract Service]
[Contract Service] --> [Approval Engine]
[Contract Service] --> "Contracts DB"
@enduml
```

## Deployment

```plantuml
@startuml
node "Azure App Service" {
  [API]
}
node "Azure SQL" {
  database "contracts"
}
[API] --> "contracts"
@enduml
```

## State

```plantuml
@startuml
[*] --> Drafting
Drafting --> Review : submit
Review --> Approved : approve
Review --> Drafting : changes
Approved --> Executed : sign
Executed --> [*]
@enduml
```

## Tips

- Activity beta (`|Role|` swimlanes) is the right choice for CFFs rendered in CI pipelines
- Use `!include` to share skinparam themes across diagrams
- Export SVG for docs, `.vsdx` via draw.io import when Visio is required
- Validate via `plantuml -tsvg file.puml` locally or public PlantUML server
