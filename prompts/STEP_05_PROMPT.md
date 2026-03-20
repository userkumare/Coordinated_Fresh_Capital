# STEP_05_PROMPT.md

Implement Step 5 only.

## Step Goal

Build the minimal detection decision engine for the Coordinated Fresh Capital Flow Strategy MVP.

This step must consume the existing deterministic token-level feature output and produce a deterministic detection decision result.

Do not implement alerts, persistence, dashboards, orchestration, external integrations, or later pipeline stages.

## Required scope

Implement a small decision engine module that:

1. accepts the existing token feature extraction result
2. evaluates the core MVP coordinated fresh capital flow rules
3. returns a deterministic decision result
4. exposes explicit ordered triggered_rules and reject_reasons

## Required behavior

Use only existing Step 1–4 primitives and thresholds.

At minimum, evaluate rules for:

- minimum valid cohort presence
- minimum aggregate fresh capital contribution
- maximum concentration guardrail if current thresholds support it
- minimum market-cap-relative funding ratio if available
- minimum liquidity-relative funding ratio if available
- minimum participant count / cohort strength
- optional timing/cohort-span gate if supported by current inputs and thresholds

Return a deterministic result structure that clearly indicates:

- is_detected
- reject_reasons
- triggered_rules
- severity or strength band
- derived decision metrics actually used

Rules must be explicit, stable, and ordered.

If some optional metrics are unavailable, handle that explicitly and deterministically rather than inventing values.

## Constraints

- Keep implementation minimal and local
- Preserve existing architecture and naming
- Reuse existing domain models, thresholds, and extracted features where appropriate
- Use frozen dataclasses where appropriate
- No network calls
- No file/database writes
- No async code
- No CLI/UI
- No alert emission yet
- No persistence yet

## Files

Create only what is needed for this step.
Expected likely additions are a detector/decision module and focused tests.

## Tests

Add deterministic unit tests for:

- positive detection path
- rejection due to insufficient funding
- rejection due to insufficient cohort strength
- rejection due to excessive concentration if implemented
- behavior when optional market/liquidity metrics are unavailable
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
