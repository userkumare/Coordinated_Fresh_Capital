# STEP 01 PROMPT

Step 1 — Core domain models, config thresholds, enums, validation helpers

Implement the first foundation step for the MVP project: Coordinated Fresh Capital Flow Strategy.

## Goal

Create the core domain layer and shared primitives only.
Do not implement detectors yet.

## Requirements

1. Add strict domain models for:
   - AddressRecord
   - FundingEvent
   - TokenTrade
   - TokenMarketSnapshot
   - Cohort
   - CohortMember
   - CohortTokenPosition
   - TokenDetectionFeatures
   - AlertRecord
   - TokenStateRecord

2. Add enums for:
   - AlertType
   - TokenLifecycleState
   - TradeSide
   - ServiceType
   - SourceType
   - Severity

3. Add a config/constants module with MVP thresholds:
   - fresh address thresholds
   - cohort thresholds
   - accumulation thresholds
   - confirmation thresholds
   - distribution thresholds
   - short-watch thresholds

4. Add validation helpers for:
   - required numeric non-negative fields
   - percentage range checks
   - timestamp ordering
   - allowed enum/state values

5. Keep implementation deterministic and provider-agnostic.

## Constraints

- pure Python
- type hints
- dataclasses or equivalent typed structures
- small focused functions
- no database
- no network code
- no detector logic yet

## Tests

Add unit tests for:

- model construction
- enum validity
- config loading/import
- validation success/failure cases

## Output Format Required

1. Files Created / Changed
2. Implementation Notes
3. Full code
4. Tests
5. Acceptance Criteria
6. Run / Verify

## Acceptance Criteria

- all models import cleanly
- all tests pass
- no detector logic included
- foundation is ready for next steps
