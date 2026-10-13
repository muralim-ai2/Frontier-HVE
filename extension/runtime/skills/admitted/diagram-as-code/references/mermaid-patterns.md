# Mermaid Patterns

> **Parent skill**: [diagrams/diagram-as-code](../SKILL.md)
> **Use when**: diagram must render natively in GitHub markdown, VS Code preview, or issue/PR comments.

---

## Flowchart

```mermaid
flowchart TD
  A[Client request] --> B{Valid?}
  B -- Yes --> C[Process]
  B -- No --> D[Reject with reason]
  C --> E[(Persist)]
  E --> F[Return 200]
```

## Sequence

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant API
  participant DB
  U->>API: POST /contracts (payload)
  API->>DB: INSERT contract
  DB-->>API: id=123
  API-->>U: 201 Created {id: 123}
```

## State

```mermaid
stateDiagram-v2
  [*] --> Drafting
  Drafting --> Review: submit
  Review --> Drafting: request changes
  Review --> Approved: approve
  Approved --> Executed: sign
  Executed --> [*]
```

## ER

```mermaid
erDiagram
  CONTRACT ||--o{ CLAUSE : contains
  CONTRACT }o--|| CLIENT : "belongs to"
  CONTRACT {
    uuid id
    string title
    date effective_date
  }
```

## C4 Context (Mermaid C4 plugin)

```mermaid
C4Context
  title System Context: Contract Platform
  Person(client, "Client")
  System(clm, "CLM Platform", "Authors, approves, executes contracts")
  System_Ext(esign, "E-Sign Provider")
  Rel(client, clm, "Submits and signs")
  Rel(clm, esign, "Requests signature")
```

## Journey

```mermaid
journey
  title New Contract Journey
  section Request
    Submit form: 5: Client
    Intake: 3: Agent
  section Draft
    Draft terms: 4: Attorney
    Review: 3: Associates, SME
  section Sign
    Sign: 5: Client
```

## Tips

- Prefer `flowchart LR` for journey-style left-to-right stories; `TD` for decision trees
- Use `%%{init: {'theme':'neutral'}}%%` directive for consistent rendering in light + dark themes
- Keep node labels under ~30 characters; put detail in a linked artifact
- For sequence diagrams, `autonumber` helps reviewers cite specific steps
