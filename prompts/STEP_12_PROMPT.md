# STEP_12_PROMPT.md

## Step Goal

Implement the alert retry mechanism for the Coordinated Fresh Capital Flow Strategy MVP.

This step must ensure that failed alert deliveries will be retried a specific number of times before being marked as failed.

## Required scope

Implement a retry mechanism for alert deliveries that:

1. Tracks the number of attempts for each delivery.
2. Retries the delivery a fixed number of times (e.g., 3 attempts).
3. Marks the delivery as failed after the maximum number of attempts is reached.
4. Logs each retry attempt along with success or failure status.

## Required behavior

- Implement a retry mechanism that:
  - Logs each retry attempt.
  - Attempts to deliver the alert up to 3 times (or configurable).
  - Marks the alert as "failed" after the maximum retries are reached.
  - Provides clear logging on the status of each attempt.
- Retry attempts should be spaced out by a configurable delay (e.g., 5 minutes between attempts).
- If the alert is successfully delivered, mark the status as "delivered" and stop further attempts.

## Constraints

- Keep the implementation minimal and avoid external dependencies.
- Use the existing alert notification module.
- Retry logic should be deterministic and based on the number of attempts and delay.

## Files

Create only what is needed for this step.
Expected additions are:
- retry mechanism module
- integration with the alert notification system
- retry status logging

## Tests

Add deterministic tests for:

- successful alert delivery after retries.
- failed alert delivery after maximum retries.
- correct logging of retry attempts and status changes.

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
