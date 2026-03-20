# STEP_21_PROMPT.md

## Step Goal

Build a deterministic run manifest and artifact index system for the Coordinated Fresh Capital Flow Strategy MVP.

This step must make each MVP run easier to inspect from the VPS by writing one compact manifest that describes what happened during the run, which artifacts were produced, and what the final notification outcome was.

Do not add dashboards, background services, or unrelated orchestration.

## Required scope

Implement a minimal run manifest system that:

1. records one deterministic manifest for each end-to-end run
2. indexes the main artifacts produced by the run
3. records final pipeline and notification summary fields
4. makes it easy for an operator to inspect a past run from shell

## Required behavior

Implement manifest generation that:

- writes a compact JSON manifest file for each run
- includes:
  - run identifier
  - input fixture path
  - execution timestamp
  - pipeline outcome summary
  - whether an alert was built
  - whether notification state was queued
  - whether due notifications were processed
  - final notification summary counts
  - paths to key generated artifacts
- keeps the output deterministic and compact
- reuses existing demo / ops / pipeline logic instead of duplicating business logic

Also add a small helper or CLI path that allows an operator to:

- read the latest manifest
- list manifests if needed
- inspect a manifest path directly

## Constraints

- Keep implementation minimal
- No background worker
- No web UI
- No external dependencies
- No unrelated refactors
- Preserve current architecture and naming

## Files

Create only what is needed for this step.

Expected additions are likely:
- run manifest helper or module
- small manifest inspection CLI/helper
- deterministic tests for manifest generation and reading

## Tests

Add deterministic tests for:

- manifest generation after a successful run
- manifest contents and artifact indexing
- no-alert path manifest behavior
- reading latest manifest or inspecting a specific manifest
- invalid manifest input handling

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
