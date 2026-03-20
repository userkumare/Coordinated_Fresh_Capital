# STEP_17_PROMPT.md

## Step Goal

Implement a notification alert prioritization system to ensure high-priority alerts are processed and delivered first.

This step must ensure that alerts are prioritized based on their importance and processed accordingly, regardless of when they were queued.

## Required scope

Implement a prioritization system that:

1. Allows the system to classify alerts by priority (e.g., high, medium, low).
2. Ensures high-priority alerts are processed first, even if they were queued later than low-priority alerts.
3. Adjusts the scheduling and retry mechanism to respect the priority order of alerts.
4. Logs prioritization events to track changes in alert priority.

## Required behavior

- Implement a prioritization mechanism that:
  - Classifies each alert with a priority label (e.g., `high`, `medium`, `low`).
  - Ensures that high-priority alerts are processed before low-priority ones, regardless of their queue order.
  - Allows re-prioritization of alerts if needed (e.g., user-defined priority changes).
  - Logs priority changes and alert processing order.
- The system should integrate with the existing retry and scheduling mechanisms, ensuring that priority is respected when determining the order of retries.

## Constraints

- The prioritization system should be minimal and integrate seamlessly with the existing notification system.
- Use the existing database to store the priority status of each alert.
- Keep the implementation lightweight and focused on prioritization.

## Files

Create only what is needed for this step.
Expected additions are:
- prioritization module for alerts
- integration with existing scheduling and retry systems
- logging for priority changes and processing order

## Tests

Add deterministic tests for:

- correct prioritization of alerts.
- ensuring high-priority alerts are processed first.
- logging of priority changes and order of processing.

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
