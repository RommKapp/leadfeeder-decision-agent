# Changelog

This file records meaningful, reviewable project changes. Add new entries at
the top of the History section so the newest state is always first.

## History

### 2026-09-04 — Initial private reviewer release

- Packaged the existing localhost ChatKit, FastAPI, and Codex SDK application
  with its five-skill Leadfeeder workflow, policies, contract, and fictional
  deterministic fixtures.
- Removed project-specific account defaults and all Leadfeeder write authority;
  the reviewer profile exposes exactly eight no-credit reads and four read-only
  OAuth scopes.
- Added a fail-closed local launcher readiness check and reviewer instructions
  for Codex login, project trust, Leadfeeder OAuth, installation, validation,
  launch, and limitations.
- Retained the existing `gpt-5.6-sol` model with `max` reasoning for source
  fidelity. Verified 2026-09-04 against the
  [official model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol),
  which continues to list the model and `max` reasoning support; model access
  remains dependent on the reviewer's Codex account.
- Deliberately did not add Claude or a direct model-API runtime. Either requires
  a separate provider integration and Leadfeeder OAuth implementation.
