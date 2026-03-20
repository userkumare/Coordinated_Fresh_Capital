# STEP_04_PROMPT.md

Implement Step 4 only.

## Step Goal

Build the minimal token detection feature extractor for the Coordinated Fresh Capital Flow Strategy MVP.

This step must consume existing normalized domain inputs plus the valid cohort output from Step 3 and produce deterministic token-level detection features.

Do not implement scoring, alerts, persistence, dashboards, orchestration, external integrations, or later pipeline stages.

## Required scope

Implement a small feature extraction module that:

1. accepts a valid cohort object
2. accepts token market snapshot input
3. computes deterministic token-level detection features
4. returns a clear result object with derived metrics only

## Required behavior

Use only existing Step 1–3 primitives and thresholds.

At minimum, compute and expose:

- fresh participant count
- total fresh capital contribution
- average capital per fresh participant
- top participant share of total fresh capital
- concentration ratio of top N participants if practical with current inputs
- cohort age window / cohort timing span if timestamps are available
- market-cap-relative funding ratio if market cap is available
- liquidity-relative funding ratio if liquidity is available

If an input needed for a metric is unavailable, handle it explicitly and deterministically rather than inventing values.

Return a deterministic result structure that clearly indicates:

- computed feature values
- any omitted/unavailable feature fields in an explicit way

## Constraints

- Keep implementation minimal and local
- Preserve existing architecture and naming
- Reuse existing domain models and thresholds where appropriate
- Use frozen dataclasses where appropriate
- No network calls
- No file/database writes
- No async code
- No CLI/UI
- No scoring or alert decision logic yet

## Files

Create only what is needed for this step.
Expected likely additions are a features/extractor module and focused tests.

## Tests

Add deterministic unit tests for:

- normal valid feature extraction
- missing optional market inputs
- top-share calculation
- average funding calculation
- ratio calculations
- edge cases with empty/invalid input where applicable
- stable ordering / deterministic output where applicable

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
