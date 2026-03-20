# STEP_10_PROMPT.md

Implement Step 10 only.

## Step Goal

Build a minimal fixture-driven demo runner for the Coordinated Fresh Capital Flow Strategy MVP.

This step must provide a simple file-based entrypoint that reads normalized input data from local JSON fixtures, runs the existing Step 9 pipeline orchestrator, and writes deterministic output artifacts locally for inspection.

Do not implement live ingestion, external APIs, dashboards, Telegram, background workers, schedulers, or on-chain integrations.

## Required scope

Implement a small demo runner module that:

1. reads local JSON input fixtures from disk
2. converts fixture payloads into the existing normalized domain models required by the Step 9 pipeline
3. runs the existing end-to-end orchestration function
4. writes deterministic local output artifacts to disk
5. returns a clear result object describing what was read, what was executed, and what was written

## Required behavior

Use only existing Step 1–9 primitives and modules.

At minimum, the demo runner must support:

- loading one fixture file containing:
  - chain
  - token metadata / token address
  - token market snapshot fields
  - participant records composed from the existing normalized model inputs
- validating that fixture content is sufficient to build the required domain objects
- running the Step 9 pipeline exactly once for the fixture
- writing a deterministic JSON result file containing the pipeline result summary
- optionally writing a second human-inspectable pretty JSON artifact if practical
- failing explicitly on invalid fixture structure instead of silently guessing

The output must be local-only and deterministic.

## Constraints

- Keep implementation minimal and local
- Preserve existing architecture and naming
- Reuse the existing pipeline/orchestrator instead of rewriting logic
- Reuse existing domain models and validation helpers where appropriate
- No network calls
- No async code
- No external dependencies unless clearly necessary
- No CLI framework is required; a simple function-based runner is enough
- Do not add a full application shell

## Files

Create only what is needed for this step.

Expected likely additions are:

- a demo/runner module
- a sample fixture file under a fixtures/ or examples/ directory
- focused tests for fixture loading and end-to-end execution

## Tests

Add deterministic unit tests for:

- valid fixture load and successful pipeline execution
- invalid fixture structure rejection
- deterministic output file creation
- positive path with alert output present
- negative path where pipeline stops before alert build
- stable output shape / key presence

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
