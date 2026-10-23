# Common Oracle migration fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| PL/SQL package invalid after import | Dependencies compiled out of order | Recompile with `UTL_RECOMP.RECOMP_SERIAL()` for the schema, then list `USER_ERRORS` |
| Duplicate key after load | Sequence not advanced past the loaded maximum | Reset the sequence start to `MAX(id) + 1` before applications reconnect |
| Row counts differ for a table | Load filtered by a trigger or a disabled constraint | Disable triggers during load, reload the table, compare counts and checksums again |
| Character data garbled | Source and target character sets differ | Convert with the target `NLS_CHARACTERSET` declared, and compare samples of multibyte columns |
| Slow queries after cutover | Missing optimizer statistics | Gather schema statistics, then compare the top SQL against the AWR baseline |
