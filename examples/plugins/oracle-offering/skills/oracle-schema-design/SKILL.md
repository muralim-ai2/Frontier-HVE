---
name: oracle-schema-design
description: Oracle schema design - tablespaces, partitioning, constraints, indexes and PL/SQL package boundaries, with a migration-safe DDL order.
---

# Oracle schema design

1. Inventory the source objects from DDL in the workspace: tables, partitions, indexes, constraints, sequences, packages.
2. Keep every constraint explicit (primary, foreign, check); never rely on application code for integrity.
3. Partition only tables with a measured access pattern that benefits; record the evidence.
4. Order DDL so a migration can run and roll back: sequences and tables, then constraints, then indexes, then packages.
5. Record each decision with its alternative and the evidence in the technical design's `alternatives` section.
