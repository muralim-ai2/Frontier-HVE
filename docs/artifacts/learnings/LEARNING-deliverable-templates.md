# Deliverable Template Packaging

- Frontier-HVE's `extension/build.py` copies selected runtime tools and all
  `plugins/harness-assist/skills`; `extension/render.js` publishes those skills.
- The adapter exporter copies runtime and packaged skills. Keeping template
  resolution workspace-relative avoids embedding a VS Code installation path
  into company configuration or exported prompts.
- Template structure enforcement belongs in a shared executable manager, not
  duplicated agent prose. Provenance uses raw-byte SHA-256; marker matching
  normalizes CRLF independently.
- A packaged agent change requires an extension version bump: activation only
  re-renders a previously configured plugin when the version changes.
- Session registration, bounded lifecycle hooks and structural validation do not
  replace semantic review, user approval or live client qualification.