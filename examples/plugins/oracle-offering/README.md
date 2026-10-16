# Oracle Offering (sample Frontier HVE plugin)

Sample plugin that shows the Frontier HVE plugin contract end to end: two agents, two skills, three templates (one replacing the
core technical design, two new kinds), an Oracle migration flow and its own rubrics.

- Owner: Contoso Oracle practice (sample)
- Support: open an issue in the plugin's own repository
- Install: `python <tools>/plugins/plugin.py inspect examples/plugins/oracle-offering`, then
  `plugin.py install examples/plugins/oracle-offering --confirm <sha256>`, or run **Frontier HVE: Install plugin**.
- Package for release: `plugin.py pack examples/plugins/oracle-offering --out dist`

The skills and templates are illustrative; an organization replaces them with its vetted content.
