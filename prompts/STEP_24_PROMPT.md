# STEP_24_PROMPT.md

## Step Goal

Finalize and validate the end-to-end operation of the Coordinated Fresh Capital Flow Strategy MVP pipeline, ensuring all alerts, notifications, and artifacts are processed correctly.

This step will ensure the final validation of the pipeline by checking the completion of all notifications, generating and verifying the final reports, and confirming that no alerts are missed or unprocessed.

## Required scope

1. Validate that the entire pipeline has been executed without errors.
2. Ensure that all notifications have been processed correctly.
3. Generate final status reports for all completed runs, including any failed or pending notifications.
4. Allow the operator to inspect final reports and artifacts via CLI.

### Files to be created:
- Final validation helpers for checking processed notifications.
- Final report generation for completed runs.

### Tests:
1. Validate the correctness of the final status report after a complete run.
2. Verify that all notifications are processed, even those that fail or are pending.
3. Test the CLI command for generating the final status and artifacts report.

## Delivery requirements

1. Files created/changed.
2. What was implemented.
3. Exact commands to run tests.
4. Assumptions or blockers.

Do not add unrelated features.
