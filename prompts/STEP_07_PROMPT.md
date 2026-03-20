# STEP_07_PROMPT.md

## Step Goal

Implement the alert delivery and logging system for the Coordinated Fresh Capital Flow Strategy MVP.

This step must consume the alert record produced in Step 6 and either send the alert or store it deterministically. The alert delivery logic should be simple, log-based, and trackable.

**Do not implement external notification systems or complex workflows** at this stage; this step focuses solely on delivering the alert internally, logging it, or storing it for later integration.

## Required scope

Implement a simple alert handling system that:

1. accepts an alert record from the Step 6 builder
2. stores the alert record internally or sends it to a **local log or storage system**
3. tracks alert statuses deterministically (such as "created", "processed", "rejected")
4. maintains audit logs with timestamps and triggered rule context

## Required behavior

- Store or log the alert record in a structured format (e.g., JSON) for future retrieval.
- The alert record should include the following fields:
  - alert type (from Step 6)
  - reject reasons (if applicable)
  - triggered rules (for reference)
  - severity (as determined in Step 6)
  - timestamp (from the cohort context)
  - a status field (such as "created", "processed", "rejected")
- Implement **no external integrations** (like emailing, pushing to external APIs, etc.) in this step.
- Ensure the storage mechanism can handle future expansions and integration (i.e., store in a structured format that could be expanded into a database or log management system later).

## Constraints

- Keep the implementation minimal and local
- Use simple logging or in-memory storage (e.g., a file or in-memory data structure)
- Ensure **no external notifications** or delivery beyond the local system at this stage
- Ensure that no **real-time or asynchronous** components are involved
- Do not modify previous steps' behavior or outputs unless required

## Files

Create only what is needed for this step. 
Expected likely additions are a `logs` or `alerts` module and focused tests.

## Tests

Add deterministic unit tests for:

- positive alert storage (with valid data)
- alert creation and status change (e.g., from "created" to "processed")
- rejection of invalid alerts (based on Step 6's criteria)
- structured logging or storage behavior
- invalid input handling (such as missing alert data or malformed input)

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
