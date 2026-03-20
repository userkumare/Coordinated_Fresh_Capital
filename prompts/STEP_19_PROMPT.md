# STEP_19_PROMPT.md

## Step Goal

Build a minimal deterministic end-to-end demo command for the Coordinated Fresh Capital Flow Strategy MVP.

This step must make the MVP easy to run manually from the VPS by exposing one operator-facing flow that loads fixture input, runs the existing pipeline, persists notification state, processes due notifications, and writes compact output artifacts.

Do not add live blockchain ingestion, background workers, dashboards, or unrelated orchestration.

## Required scope

Implement a minimal demo execution flow that:

1. loads existing fixture-driven input
2. runs the current fresh capital pipeline end-to-end
3. persists alerts / notification state through the existing system
4. processes due notifications through the existing ops / scheduling / retry / expiration / prioritization layers
5. writes compact deterministic artifacts for operator inspection

## Required behavior

Implement one small demo entrypoint or command that:

- accepts fixture input paths or uses a default demo fixture set
- runs the current deterministic pipeline
- writes the main pipeline result to a JSON artifact
- writes notification state / summary artifacts
- optionally triggers due notification processing in the same run
- prints a compact shell-friendly summary at the end

The demo flow must reuse existing modules and must not duplicate business logic.

Expected behavior of the demo run:

- build cohort
- extract token features
- run detector
- build alert if triggered
- persist / queue notification state if alert exists
- process due notifications using the current notification system
- emit deterministic artifacts that can be inspected later from shell

## Constraints

- Keep implementation minimal
- No background daemon
- No new external dependencies
- No dashboard
- No unrelated refactors
- Preserve current architecture and naming
- Use existing fixture-driven style and existing modules whenever possible

## Files

Create only what is needed for this step.

Expected additions are likely:
- a demo command / runner module
- artifact writing helpers if needed
- deterministic end-to-end demo tests

## Tests

Add deterministic tests for:

- successful end-to-end demo execution from fixtures
- artifact generation
- no-alert path behavior
- alert-triggered path behavior
- invalid input handling

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
