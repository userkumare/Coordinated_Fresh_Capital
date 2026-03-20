# Fresh Capital MVP Deployment

This repository ships a deterministic, one-command MVP for the Coordinated Fresh Capital Flow Strategy.

## Architecture Summary

The runtime is intentionally small and layered:

- `fresh_capital.demo.runner` loads the bundled fixture, runs the deterministic pipeline, and writes local artifacts.
- `fresh_capital.manifest` records run metadata, artifact paths, and validation state.
- `fresh_capital.notifications.verification` inspects notification state and builds final status reports.
- `fresh_capital.__main__` is the operator-facing command that orchestrates the full run and exposes the `status` subcommand.

The pipeline writes JSON and SQLite artifacts to the chosen output directory and does not require external services for the MVP path.

## Production-Style Run

Run the full pipeline from the repository root:

```bash
python /root/projects/fresh-capital-mvp/run_fresh_capital.py --output-dir /tmp/fresh-capital-run
```

Inspect the final status for a completed run:

```bash
python /root/projects/fresh-capital-mvp/run_fresh_capital.py status --manifest-path /tmp/fresh-capital-run/manifests/<manifest-file>.json
```

## Produced Artifacts

For a successful run, the operator should expect:

- `pipeline_result.json`
- `pipeline_result.pretty.json`
- `alerts.jsonl`
- `deliveries.sqlite`
- `delivery_status.jsonl`
- `notification_state.sqlite`
- `notification_report.json`
- `notification_status_report.json`
- `artifacts_summary.json`
- `final_validation_report.json`
- `manifests/<timestamp>--<run_id>.json`

## Validation Checklist

Before deployment, verify:

1. The final run completes with exit code `0`.
2. `validation_passed` is `true` in the final summary JSON.
3. `final_validation_report.json` exists and matches the run output.
4. The `status` command returns the same `run_id` as the completed run.
5. A no-alert run still generates deterministic artifacts and reports.

## Cleanup Notes

No Docker image or extra cleanup script is required for the current MVP.
The project does not create persistent deployment-time configuration files outside the chosen output directory.

If temporary output directories are created during testing, remove them with standard shell cleanup for your environment.
