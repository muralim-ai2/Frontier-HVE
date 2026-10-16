# Design stage

1. Create the technical design with the template manager (kind `technicalDesign`) from the assessment, following the
   `oracle-schema-design` skill. Fill every section and validate it.
2. Write `design.json` with a non-empty `acceptance` list and a real `validation_check` command that exits 0 only when the migrated
   data matches the source (row counts and checksums). The flow locks this command once the design is approved.
3. Run `flow.py transition . design-approved`.
