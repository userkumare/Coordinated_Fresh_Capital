# STEP_11_PROMPT.md

## Step Goal

Build the minimal live alert notification system for the Coordinated Fresh Capital Flow Strategy MVP.

This step must consume the existing alert records and deliver them through a **real-time system** such as email, webhooks, or a messaging platform.

Do not implement full orchestration or external services beyond alert notification.

## Required scope

Implement a live alert notification system that:

1. consumes the alert records built in Step 7–8
2. delivers them through a **real-time messaging platform** (e.g., email, webhook, or similar)
3. tracks the status of delivery (successful, failed, etc.)

## Required behavior

- Implement an alert delivery system that uses:
  - **Email notifications**, **webhooks**, or any other notification service that fits the system.
  - Logs delivery status and retries in case of failure.
  - Exposes an API endpoint or message queue if integrating with real-time systems.
- Use the existing alert object from Step 8 to send content like:
  - alert type
  - triggered rules
  - reject reasons
  - severity
  - additional fields from the cohort/context
  - status of delivery
  
## Constraints

- Keep the implementation minimal
- Use an existing email API or messaging platform library (like **SMTP**, **Twilio**, **Slack** webhooks)
- No real-time orchestration is required; focus on **sending notifications** after the alert is built
- Delivery status tracking must be **deterministic** with simple logging

## Files

Create only what is needed for this step.
Expected additions are:
- alert notification module
- API/webhook integration code
- test notifications

## Tests

Add deterministic tests for:

- successful alert delivery
- failed delivery with retry mechanism
- testing real-time API/webhook calls
- logging delivery status and tracking errors

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
