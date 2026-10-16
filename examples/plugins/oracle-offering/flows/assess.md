# Assess stage

1. Read the Oracle evidence in the workspace (DDL, PL/SQL, AWR extracts, configuration). If there is none, ask the user for it.
2. Create the assessment with the template manager (kind `oracle-offering:assessment`), fill every section from the evidence, and
   run `manage.py validate oracle-offering:assessment --slug <slug>` until it is valid.
3. Run `flow.py transition . assessed`.
