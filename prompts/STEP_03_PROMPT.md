# STEP_03_PROMPT.md

Implement Step 3 only.

## Step Goal

Build the minimal cohort construction layer for the Coordinated Fresh Capital Flow Strategy MVP.

This step must take already-normalized domain inputs and produce deterministic cohort objects from fresh-address-qualified participants around a token.

Do not implement scoring, alerts, persistence, dashboards, orchestration, external integrations, or later pipeline stages.

## Required scope

Implement a small cohort builder module that:

1. accepts token-level participant inputs based on existing domain models
2. filters to only fresh-qualified addresses
3. groups valid fresh participants for a token into a cohort
4. computes simple cohort-level derived metrics
5. returns deterministic reject reasons when cohort requirements are not met

## Required behavior

Use only the existing Step 1/2 primitives and thresholds.

At minimum, the cohort builder must evaluate:

- unique fresh participant count
- total fresh capital contribution
- whether minimum cohort size is reached
- whether minimum aggregate capital threshold is reached

Return a deterministic result structure that clearly indicates:

- is_valid_cohort
- reject_reasons
- derived metrics
- resulting cohort object when valid

Reject reasons must be explicit, stable, and ordered.

## Constraints

- Keep implementation minimal and local
- Preserve existing architecture and naming
- Use frozen dataclasses where appropriate
- Reuse existing thresholds/config
- Reuse existing validation/domain models where appropriate
- No network calls
- No file/database writes
- No async code
- No CLI/UI
- No later-stage strategy logic

## Files

Create only what is needed for this step.
Expected likely additions are a cohort builder module and focused tests.

## Tests

Add deterministic unit tests for:

- valid cohort creation
- insufficient member count
- insufficient aggregate capital
- mixed valid/invalid participants
- deterministic reject reason ordering
- threshold edge equality behavior
- invalid input handling where applicable

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
