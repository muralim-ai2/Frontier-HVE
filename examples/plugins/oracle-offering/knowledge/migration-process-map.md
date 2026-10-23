# Oracle migration process map

| Phase | Owner | Input | Output | Hand-off to |
|---|---|---|---|---|
| 1. Discover | DB architect | Access to the source estate | Object inventory, AWR baseline, application list | Assess |
| 2. Assess | DB architect | Inventory, AWR baseline | Assessment: risks, dependencies, recommendation | Design |
| 3. Design | DB architect, application lead | Accepted assessment | Target schema, sizing, migration method (export/import, GoldenGate, Data Guard) | Build |
| 4. Build | Engineer | Accepted design | DDL in dependency order, PL/SQL, load scripts, each with a check | Validate |
| 5. Validate | Engineer, data owner | Built target | Row counts, checksums, compiled PL/SQL, rehearsed rollback | Cutover |
| 6. Cutover | Engineer, service owner | Runbook, go/no-go | Switched applications, monitoring | Hypercare |

Rules of thumb:

1. Choose the migration method by downtime budget: export/import for hours, GoldenGate or Data Guard for minutes.
2. Order DDL as sequences and tables, then constraints, then indexes, then packages; rollback runs in reverse.
3. Never cut over without a rehearsed rollback and a named point of no return.
