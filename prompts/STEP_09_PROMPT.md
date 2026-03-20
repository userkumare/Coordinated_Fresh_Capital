# STEP_09_PROMPT.md

Implement Step 9 only.

## Step Goal

Build the minimal end-to-end orchestration function for the Coordinated Fresh Capital Flow Strategy MVP.

This step must connect the existing Step 2–8 modules into one deterministic in-process pipeline that accepts normalized inputs and runs the full detection flow.

Do not implement schedulers, background workers, external APIs, dashboards, Telegram, CLI apps, or live on-chain integrations.

## Required scope

Implement a small orchestration module that:

1. accepts normalized token-level inputs using existing domain models
2. runs fresh address classification for participants
3. builds a cohort
4. extracts token features
5. runs the detection engine
6. builds an alert when appropriate
7. writes alert handling and optional local delivery outputs using the existing Step 7–8 modules
8. returns a deterministic pipeline result object summarizing all stage outcomes

## Required behavior

Use only existing Step 1–8 primitives and modules.

At minimum, the orchestration result must clearly expose:

- participant classification results
- cohort result
- feature extraction result
- detection result
- alert build result
- alert handling result if an alert was handled
- delivery result if delivery was attempted
- explicit stage_status / stage_skipped information for deterministic tracing

The orchestration function must stop cleanly at the correct stage when prior gates fail.
It must not invent downstream results when an upstream stage fails.

## Constraints

- Keep implementation minimal and local
- Preserve existing architecture and naming
- Reuse existing modules instead of rewriting logic
- Use frozen dataclasses where appropriate
- No network calls
- No async code
- No dashboard/UI
- No scheduler/daemon
- No new external dependencies
- No live data fetching

## Files

Create only what is needed for this step.
Expected likely additions are a pipeline/orchestrator module and focused end-to-end tests.

## Tests

Add deterministic unit tests for:

- full positive end-to-end path
- stop at fresh-address/cohort gate failure
- stop at detector failure without building alert
- positive alert path with handler output
- positive alert path with delivery output
- deterministic stage ordering and stage status reporting
- invalid input handling where applicable

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
