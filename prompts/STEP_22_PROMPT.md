# STEP_22_PROMPT.md

## Step Goal

Build an alert completion check and notification status reporting mechanism for the Coordinated Fresh Capital Flow Strategy MVP.

This step will ensure that all alerts are properly checked for completion and will generate a status report of notifications after the full pipeline execution.

## Required scope

Implement a mechanism that:

1. Verifies the completion of alert processing after the pipeline run.
2. Generates a status report summarizing the alerts’ final state (processed, pending, failed).
3. Allows an operator to retrieve the status report for any completed run.

## Required behavior

- The system should check the alert status after processing and provide a final report.
- The report should include:
  - Number of alerts processed successfully
  - Number of alerts pending
  - Number of failed alerts
  - Final notification outcome summary
- The operator should be able to inspect the result using a CLI command after the run is complete.

### CLI Commands:
- A new command should be added to check the status of alerts after the pipeline run.
- The status report should be output in JSON format, ready for inspection.

### Tests:
1. Validate the alert completion status after processing.
2. Add tests for generating and retrieving the status report.
3. Ensure correct error handling when invalid status is requested.

### Files:
- A new command for fetching the alert completion status.
- A report generation helper.
- Tests for validation and correct report generation.

## Delivery requirements

1. Files created/changed
2. What was implemented
3. Exact commands to run tests
4. Assumptions or blockers

Do not add unrelated features.
