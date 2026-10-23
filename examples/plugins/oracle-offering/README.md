# Oracle Offering (sample Frontier HVE expertise pack)

Sample pack that shows the pack contract end to end: two agents, two skills, three templates (one replacing the core technical
design, two new kinds), an Oracle migration lifecycle (overlay) with stage evidence and a rework step, two knowledge documents and
its own rubrics.

- Owner: Contoso Oracle practice (sample)
- Support: open an issue in the pack's own repository
- Use in one workspace: copy this folder to `plugins/oracle-offering/` in the workspace.
- Install for every workspace: `python <tools>/plugins/plugin.py inspect examples/plugins/oracle-offering`, then
  `plugin.py install examples/plugins/oracle-offering --confirm <sha256>`, or run **Frontier HVE: Install plugin**.
- Package for release: `plugin.py pack examples/plugins/oracle-offering --out dist`

The skills and templates are illustrative; an organization replaces them with its vetted content.
