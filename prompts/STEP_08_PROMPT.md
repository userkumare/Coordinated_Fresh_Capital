# STEP_08_PROMPT.md

## Step Goal

Implement the alert delivery and notification system for the Coordinated Fresh Capital Flow Strategy MVP.

This step must consume the locally logged alert records and deliver them to an external notification system or database.

Do not implement full orchestration or external services other than a simple **local API call or database insert** for delivery.

## Required scope

Implement a simple external delivery mechanism that:

1. consumes the alert log entries (from Step 7)
2. sends the alert to a mock external API or stores it in a local database (e.g., SQLite or mock API)
3. updates the alert status from "created" to "delivered"

## Required behavior

- Implement delivery by calling a simple mock API or performing a database insert.
- The API/database should be configured to accept alert records in a standard format (e.g., JSON).
- Track the delivery status and store it (e.g., "delivered", "failed", etc.).
- Implement an **API mock or database mock**, ensuring alerts are "delivered" or stored without needing a real API.

## Constraints

- Keep the implementation minimal and local.
- Use a simple mock API or SQLite database.
- Ensure deterministic logging of the alert status.
- **Do not implement real-time notifications or complex external integrations** (keep it mock for now).
- **Do not implement persistent storage beyond the delivery mechanism**.

## Files

Create only what is needed for this step.
Expected likely additions are a mock API or database integration module and focused tests.

## Tests

Add tests for:

- successful alert delivery
- unsuccessful delivery (mock failures)
- correct API/database insertion behavior
- alert status updates (from "created" to "delivered")
- invalid inputs handling

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
