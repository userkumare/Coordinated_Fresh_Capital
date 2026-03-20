# STEP_15_PROMPT.md

## Step Goal

Implement a notification alert scheduling system that triggers alerts based on a defined schedule.

This step must allow the system to trigger alerts at scheduled times and handle delays in processing, ensuring that all alerts are sent in a timely manner.

## Required scope

Implement a scheduling system that:

1. Allows the user to define a schedule for each alert (e.g., a specific time, interval, or delay).
2. Tracks the time each alert should be sent and triggers the alert accordingly.
3. Handles missed or delayed alerts by automatically rescheduling them for the next available time.

## Required behavior

- Implement a scheduling mechanism that:
  - Receives a defined time or delay for each alert.
  - Triggers alerts at the specified time.
  - Reschedules missed or delayed alerts.
- The system should handle alerts at different intervals, such as hourly, daily, or based on a specific date/time.
- Implement logging to track alert scheduling, triggering, and rescheduling.

## Constraints

- The scheduling system should not interfere with the existing retry and notification systems.
- Use the existing database for storing scheduled times and alert statuses.
- Keep the system lightweight and focused on scheduling.

## Files

Create only what is needed for this step.
Expected additions are:
- scheduling module for alerts
- integration with existing notification and retry systems
- logging for alert scheduling and status

## Tests

Add deterministic tests for:

- correctly scheduling and triggering alerts at the specified times.
- handling missed or delayed alerts and rescheduling them.
- correct logging of alert scheduling and triggering.

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
