# STEP_06_PROMPT.md

Implement Step 6 only.

## Step Goal

Build the minimal alert record builder for the Coordinated Fresh Capital Flow Strategy MVP.

This step must consume the existing detection decision output and assemble a deterministic alert record object for positive detections.

Do not implement persistence, delivery, dashboards, orchestration, external integrations, or later pipeline stages.

## Required scope

Implement a small alert builder module that:

1. accepts the existing detection decision result
2. accepts the cohort and token feature context needed for alert fields
3. builds a deterministic alert record for valid detections
4. returns explicit reject reasons when an alert should not be built

## Required behavior

Use only existing Step 1–5 primitives and thresholds.

At minimum, the alert builder must:

- build an alert only when detection is positive
- map detector severity into alert severity consistently
- include explicit alert type
- include token identifier / token address fields available from current inputs
- include key supporting metrics used by the detector
- include triggered rules
- include timestamp/context fields available from current inputs
- return deterministic ordered reject reasons when no alert is built

Return a deterministic result structure that clearly indicates:

- is_alert_built
- reject_reasons
- alert_record when built
- supporting summary fields used to construct the alert

If some optional context fields are unavailable, handle that explicitly and deterministically rather than inventing values.

## Constraints

- Keep implementation minimal and local
- Preserve existing architecture and naming
- Reuse existing domain models where appropriate
- Use frozen dataclasses where appropriate
- No network calls
- No file/database writes
- No async code
- No CLI/UI
- No alert sending/delivery yet
- No persistence yet

## Files

Create only what is needed for this step.
Expected likely additions are an alerts builder module and focused tests.

## Tests

Add deterministic unit tests for:

- positive detection builds an alert
- negative detection does not build an alert
- severity mapping behavior
- triggered rules are preserved
- supporting metrics are carried into the alert record
- deterministic reject reason ordering
- invalid input handling where applicable

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
