# STEP 02 PROMPT

Step 2 — Fresh address classifier

Implement the fresh address classifier for the Coordinated Fresh Capital Flow Strategy MVP.

## Goal

Classify addresses as fresh or not fresh using deterministic rule-based logic.

## Rules

Address is fresh if:

- `address_age_days <= 30`
- `previous_tx_count <= 20`
- `distinct_tokens_before_window <= 10`
- not labeled as exchange / bridge / router / treasury / service

## Requirements

1. Create a classifier module that accepts normalized address data.
2. Return:
   - `is_fresh` boolean
   - reject reasons list
   - derived metrics used in the decision
3. Make logic transparent and auditable.
4. Do not add scoring yet.
5. Keep provider-specific labels outside the classifier core; classifier should use normalized service flags/types only.

## Tests

Add tests for:

- positive fresh case
- each individual rejection rule
- multiple rejection reasons at once
- edge threshold equality cases
- missing/invalid values if relevant

## Output Format Required

1. Files Created / Changed
2. Implementation Notes
3. Full code
4. Tests
5. Acceptance Criteria
6. Run / Verify

## Acceptance Criteria

- classifier returns deterministic output
- rejection reasons are explicit
- thresholds exactly match MVP spec
- tests fully cover threshold boundaries
