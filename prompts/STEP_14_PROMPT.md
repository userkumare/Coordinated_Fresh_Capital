# STEP_14_PROMPT.md

## Step Goal

Implement the final alert status verification system and ensure that all undelivered alerts are retried and successfully processed.

This step must ensure that alerts are fully processed and tracked, with accurate logs for each retry attempt, and undelivered alerts should eventually succeed.

## Required scope

Implement a final alert status verification system that:

1. Verifies the status of all alerts in the system.
2. Ensures that undelivered alerts are retried until successful or the retry limit is reached.
3. Provides a final confirmation that each alert has been processed (sent or failed) with accurate logging.

## Required behavior

- Implement a verification mechanism that:
  - Tracks the final status of each alert (pending, sent, failed).
  - Ensures that alerts that are not successfully delivered are retried based on the retry configuration.
  - Confirms that all alerts have been processed before completion.
- The verification system should:
  - Read the database of stored alert statuses.
  - Trigger retries for undelivered alerts.
  - Track the total number of retries for each alert and log the status.
  - Provide a final report on the processing results.

## Constraints

- The system must work with the existing notification persistence and retry mechanisms.
- The verification system must be simple and should only focus on ensuring that all alerts are processed correctly.
- The implementation should not add any new services or external dependencies beyond those already used.

## Files

Create only what is needed for this step.
Expected additions are:
- alert verification module
- status check interface
- final report generation logic

## Tests

Add deterministic tests for:

- verification of alert status after all retries.
- correct handling of undelivered alerts.
- final processing confirmation (success or failure).

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
