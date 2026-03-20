# STEP_18_PROMPT.md

## Step Goal

Build a minimal operator-facing notification operations CLI for the Coordinated Fresh Capital Flow Strategy MVP.

This step must make the notification system practically usable from the VPS shell by exposing a small deterministic CLI for inspecting notification state and manually running due processing.

Do not build a web UI or background daemon.

## Required scope

Implement a minimal CLI workflow that allows an operator to:

1. inspect notification states from the existing SQLite persistence layer
2. inspect scheduled / pending / sent / failed / canceled alerts
3. run due notification processing manually from shell
4. generate a compact JSON report for current notification state

## Required behavior

Implement a small CLI entrypoint or command module that supports actions such as:

- showing notification summary counts by state
- listing due alerts waiting for processing
- listing failed / canceled / sent alerts
- manually triggering due notification processing using the existing scheduling / retry / expiration / prioritization flow
- writing a deterministic JSON report to a file

The CLI must:

- use the existing SQLite-backed notification system
- reuse existing modules instead of duplicating business logic
- keep outputs deterministic and compact
- be safe for repeated manual runs by an operator on the VPS

## Constraints

- Keep implementation minimal
- No background worker
- No external services beyond what already exists
- No web dashboard
- No unrelated refactors
- Preserve current architecture and naming

## Files

Create only what is needed for this step.

Expected additions are likely:
- a notification ops CLI module
- minimal report builder helpers if needed
- deterministic CLI tests

## Tests

Add deterministic tests for:

- summary output / summary data generation
- listing due alerts from persisted state
- manual processing of due alerts through the CLI path
- JSON report generation
- invalid CLI argument handling

## Delivery requirements

After implementation, report:

1. files created/changed
2. what was implemented
3. exact commands to run tests
4. assumptions or blockers

Do not add unrelated features.
