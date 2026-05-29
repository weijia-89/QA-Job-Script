# Morning ops rollup (optional)

`scripts/export_triage_summary_for_ops.py` regenerates `jobspy/results/triage_latest_ops.csv` and can append a short markdown block for daily review.

## Basic usage

```bash
python3 scripts/export_triage_summary_for_ops.py
```

## Append to dated rollup

Uses `paths.ops_rollup_dir` from your profile (default: `jobspy/results/ops_rollups`):

```bash
python3 scripts/export_triage_summary_for_ops.py --append-rollup-auto
```

## JSON for dashboards / webhooks

```bash
python3 scripts/export_triage_summary_for_ops.py \
  --dump-json /tmp/triage_summary.json \
  --quiet
```

Pipe the JSON to your own curl/n8n automation — no hosted service is required by this repo.
