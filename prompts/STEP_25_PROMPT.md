# STEP_25_PROMPT.md

## Step Goal

Finalize the report generation and validation for successful and unsuccessful pipeline runs, ensuring accurate summary of notifications and artifacts.

This step will provide detailed reporting on both successful and failed runs, including any pending or failed notifications, and will allow the operator to inspect the status of any run via CLI.

## Required scope

1. Ensure that final reports are generated for both successful and failed pipeline runs.
2. Include comprehensive status summaries for notifications (processed, pending, failed) and artifacts.
3. Add CLI command to retrieve the final report for any run, whether successful or failed.
4. Allow for comprehensive reporting on failures in the pipeline, including failed notifications or missing artifacts.

### Files to be created:
- CLI integration for accessing final status reports for both successful and failed runs.
- Final status report for incomplete or failed runs.

### Tests:
1. Validate the generation of final reports for both successful and failed runs.
2. Test CLI integration for retrieving failed run reports.
3. Ensure that all failed notification statuses and missing artifacts are included in the final report.

## Delivery requirements

1. Files created/changed.
2. What was implemented.
3. Exact commands to run tests.
4. Assumptions or blockers.

Do not add unrelated features.
