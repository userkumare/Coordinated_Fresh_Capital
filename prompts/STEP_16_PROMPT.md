# STEP_16_PROMPT.md

## Step Goal

Implement a notification system for alert expiration and automatic cancellation for undelivered alerts.

This step must ensure that alerts are canceled after a specific expiration time if they remain undelivered, preventing unnecessary retries or further processing.

## Required scope

Implement an expiration and cancellation mechanism that:

1. Checks the expiration time for each alert.
2. Cancels undelivered alerts after their expiration time has passed.
3. Logs the expiration and cancellation events for each alert.
4. Prevents further retry attempts for canceled alerts.

## Required behavior

- Implement an expiration system that:
  - Each alert has a defined expiration time.
  - Alerts that are not successfully delivered within this time are automatically canceled.
  - Canceled alerts are not retried.
  - Expiration and cancellation events are logged.
- The system should support configurable expiration times, for example:
  - One hour after the first attempt.
  - A specific time window (e.g., until the end of the day).

## Constraints

- The expiration system must integrate with the existing retry and notification systems.
- Use the existing database to track alert expiration and cancellation statuses.
- Keep the implementation minimal and focused only on expiration and cancellation.

## Files

Create only what is needed for this step.
Expected additions are:
- expiration and cancellation module
- integration with the existing notification/retry system
- logging for expiration and cancellation events

## Tests

Add deterministic tests for:

- correct handling of alert expiration.
- cancellation of undelivered alerts after the expiration time.
- logging of expiration and cancellation events.

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
