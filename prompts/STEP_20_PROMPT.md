# STEP_20_PROMPT.md

## Step Goal

Build an operator-facing shell command for finalizing the Coordinated Fresh Capital Flow Strategy MVP.

This step will expose a single shell command to allow the operator to run the full MVP pipeline from the CLI, from loading the input fixtures to generating final reports. This command must incorporate all the steps and be fully deterministic.

## Required scope

Implement a shell command or entrypoint that:

1. Loads the existing input fixtures or uses a default fixture.
2. Runs the full pipeline (including data processing, token features extraction, fresh capital detection, alert building, notification handling, etc.).
3. Generates and writes output artifacts (reports, notification state, summaries).
4. Handles errors gracefully and logs them in a deterministic manner.
5. Provides a summary output (e.g., number of alerts triggered, number of processed notifications).
6. Allows the operator to run the process from the shell with no manual intervention (as a one-command solution).

## Required behavior

- The shell command should:
  - Accept fixture input paths as arguments (or use a default fixture if none are provided).
  - Execute the entire pipeline without requiring manual steps between phases.
  - Log progress and errors deterministically.
  - Generate compact JSON reports that can be reviewed after execution.
  - Support scheduled processing if applicable, along with retries and expiration.
  - If the user provides incorrect arguments, handle the error and provide a meaningful message.

## Constraints

- No UI, no background services.
- No new external dependencies beyond what already exists.
- Minimal user interaction (run a single command).
- Reuse all existing pipeline components, avoid duplicating business logic.

## Files

Create only what is needed for this step.

Expected additions are likely:
- a final shell command / script for running the full pipeline
- a report generation helper if needed
- validation tests for argument parsing, error handling, and logging

## Tests

Add deterministic tests for:

- command-line argument parsing (with valid and invalid arguments).
- end-to-end execution of the pipeline using the default or provided fixture.
- output artifact generation (including report and summary).
- error handling for invalid arguments or processing failures.

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
