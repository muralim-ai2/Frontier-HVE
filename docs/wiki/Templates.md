# Configured Deliverable Templates

Frontier HVE includes versioned Markdown templates for Product Requirements
Documents (`prd`), Technical Design Specifications (`technicalDesign`) and Test
Strategies (`testStrategy`). They are bundled in the extension runtime, not read
from any other installed extension. Only the requested document types are loaded.

## End-User Workflow

After installing the updated VSIX and running **Frontier HVE: Set up**, ask
`HVE creator`, `HVE creator-flow`, `HVE creator-github` or `HVE single` to create
the documents. For example: "Create a PRD, technical design specification and
test strategy for the employee leave portal."

Defaults work without configuration. Output locations are:

| Type | Default output |
| --- | --- |
| PRD | `docs/product/PRD-{slug}.md` |
| Technical Design | `docs/design/TDS-{slug}.md` |
| Test Strategy | `docs/testing/TEST-STRATEGY-{slug}.md` |

The agent registers all requested types, initializes each document, fills its
sections and validates it before handoff. `creator-flow` handles document-only
requests directly; its app-flow `design.json` contract is unchanged. Constrained
minimal, evaluation and specialist agents are not document-authoring entry points.

## Company Templates

Run the following from the project root; `<tools>` is `tools` when developing
this repository, or `<installed-extension>/runtime/tools` for end users:

```text
python <tools>/templates/manage.py configure
```

This exclusively creates `frontier-hve.templates.json`; it never overwrites an
existing file. Commit that file and your custom templates to share them with the
team. They belong outside `.hve/`, which is runtime state, often git-ignored.

```json
{
  "version": 1,
  "enforce": true,
  "templates": {
    "prd": {
      "source": "docs/templates/company-prd.md",
      "output": "docs/product/PRD-{slug}.md"
    },
    "technicalDesign": {
      "source": "builtin:technical-design@1",
      "output": "docs/design/TDS-{slug}.md"
    },
    "testStrategy": {
      "source": "builtin:test-strategy@1",
      "output": "docs/testing/TEST-STRATEGY-{slug}.md"
    }
  }
}
```

Start a custom template by copying the corresponding bundled Markdown template
from `templates/deliverables/` (or the installed runtime's same directory).
Preserve one identity such as `<!-- hve-template: prd@2 -->` and give each required
section a unique `<!-- hve-section: purpose -->` marker before its heading.
The identity's type must match the config key; the version is a positive integer.
Use `{{FILL: ...}}` placeholders. Do not put `hve-document` metadata in a template;
the manager creates it. Every marked section is required and must contain content
other than headings/comments. For non-applicable sections, record a reason.

Save templates as UTF-8 without a byte-order mark. Preserve their exact bytes
across checkouts because provenance includes line endings. Bundled templates have
Git text conversion disabled. Add the same rule for your custom template directory
to the repository's `.gitattributes` before sharing documents:

```gitattributes
docs/templates/*.md -text
```

Commit the templates without changing their line endings. An intentional encoding
or line-ending conversion is a source change and requires document migration.

The bundled `config.schema.json` describes the configuration shape. The Python
manager also checks path safety and source identities. Paths must be relative,
use `/`, stay inside the workspace and not traverse `.git`, `.hve` or `.harness`.
Linked paths, absolute paths, case aliases of protected names and components
ending in dots/spaces are rejected. Output patterns require exactly
one `{slug}` and a `.md` extension. Missing or malformed configured sources fail;
they never silently fall back to bundled templates.

## Commands and Validation

The hook provides the session ID. Manual users may select an explicit ID for a
standalone document workflow; use the hook's ID to participate in its Stop gate.

```text
python <tools>/templates/manage.py request prd technicalDesign testStrategy --session <id>
python <tools>/templates/manage.py resolve prd
python <tools>/templates/manage.py init prd --slug leave-portal --session <id>
python <tools>/templates/manage.py validate prd --slug leave-portal
python <tools>/templates/manage.py check --session <id>
```

Fill the initialized document before validating. `validate` and `check` exit 1
for missing documents, altered provenance, missing/duplicated/reordered sections,
empty sections or unfilled `{{FILL: ...}}` placeholders. Other brace expressions,
including GitHub Actions and Helm syntax, are permitted. Preserve the generated comments. Existing
documents are never overwritten. To reuse a valid generated document in a new
session, use `register prd --slug leave-portal --session <id>`.

Provenance includes the exact-byte SHA-256 of the resolved template. If a template
changes, validation flags older generated documents. Obtain approval to migrate
content into a newly initialized document with a new slug. Do not hand-edit the
hash to claim migration. Config and template changes should be version-controlled.

The Stop hook checks the current session's registered documents. It asks once per
turn for correction; on hook reentry it reports remaining failures rather than starting
an unbounded repair loop. `enforce: false` explicitly disables this Stop gate,
not the validation commands. An invalid result is not a successful handoff.
The parent serializes manager commands; delegated workers edit only assigned
documents. Registry updates use an exclusive lock and atomic publication. A busy
or interrupted update fails explicitly; no competing snapshot silently wins.
After an interrupted operation, inspect documents and registry state before
manually removing a leftover `.json.lock` or `.json.tmp`; then register any valid
unregistered documents. Do not delete the registry to bypass validation.

Structural conformance does not prove requirement quality, cross-document
traceability, approval or executed test results. Those require content review.
The request detector recognizes explicit authoring language, not arbitrary intent;
agent instructions require explicit registration for wording it misses. This is
not a security boundary against an agent or user modifying local state.

## Other Clients

Re-export the updated harness for Claude Code, Cursor or Codex. The exporter copies
the manager, templates and skill and translates the authoring hooks. No template
configuration is embedded into an exported prompt; resolution occurs in the
destination workspace. Cursor does not deliver prompt-submit context, but it has
SessionStart context, agent instructions and the Stop follow-up. Live client
qualification remains separate from protocol tests; see [Adapters](Adapters.md).
Cursor's Stop reentry has no diagnostic channel: the initial follow-up explicitly
requires reporting unresolved failures, and reentry does not schedule another
repair loop. Claude/VS Code retain a reentry system message.