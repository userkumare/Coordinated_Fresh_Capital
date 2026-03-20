# STEP_13_PROMPT.md

## Step Goal

Implement alert notification persistence with the Coordinated Fresh Capital Flow Strategy MVP.

This step must store the status and details of all alerts, including retry attempts, and allow the system to recover from failures by re-sending undelivered alerts.

## Required scope

Implement a notification persistence system that:

1. Saves each alert’s status, including retries and delivery success/failure.
2. Allows querying of past alert statuses (successful, failed, etc.).
3. Implements a mechanism to re-send undelivered alerts based on their status.
4. Supports periodic re-attempts for undelivered alerts.

## Required behavior

- Implement a persistence mechanism for:
  - Saving the alert’s current status (e.g., pending, sent, failed).
  - Storing delivery attempts (e.g., retry count, delay, status).
  - Logging delivery errors and success states.
- Implement a query system to:
  - Retrieve past alert statuses.
  - Identify undelivered alerts for re-sending.
- Ensure that undelivered alerts can be re-sent, with a maximum retry limit.

## Constraints

- Store the data in a **local database** (e.g., SQLite) or **flat files** (e.g., JSONL).
- Keep the implementation minimal.
- Use existing alert notification modules and retry mechanisms.

## Files

Create only what is needed for this step.
Expected additions are:
- database integration module
- persistence layer for alert notifications
- query interface for alert statuses

## Tests

Add deterministic tests for:

- persistence of alert statuses (pending, sent, failed).
- re-sending undelivered alerts after a set period.
- correct logging of delivery attempts and statuses.

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
