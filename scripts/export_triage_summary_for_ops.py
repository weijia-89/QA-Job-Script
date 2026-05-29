#!/usr/bin/env python3
"""Summarize JobSpy triage for ops rollup / n8n webhooks.

Regenerates ``jobspy/results/triage_latest_ops.csv`` via
``triage_jobspy_csv.py --latest``, emits JSON with verdict counts plus an
apply-row sample suitable for dashboards.

See ``docs/ops-morning-rollup.md`` for rollup + JSON export examples."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--append-rollup",
        metavar="PATH",
        help="Append summary section to rollup markdown.",
    )
    parser.add_argument(
        "--rollup-dir",
        default=None,
        help="Directory for dated rollup (--append-rollup-auto); default from profile or jobspy/results/ops_rollups",
    )
    parser.add_argument(
        "--append-rollup-auto",
        action="store_true",
        help="Append into <rollup-dir>/YYYY-MM-DD.md",
    )
    parser.add_argument(
        "--dump-json",
        metavar="FILE",
        help="Write summary JSON to FILE (then curl it to n8n).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print JSON to stdout.",
    )
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "jobspy"))
    from profile_loader import ops_rollup_dir  # noqa: E402

    rollup_dir = args.rollup_dir
    if rollup_dir is None:
        rollup_dir = str(ops_rollup_dir())
    triage_runner = os.path.join(root, "scripts", "triage_jobspy_csv.py")
    out_csv = os.path.join(
        root, "jobspy", "results", "triage_latest_ops.csv"
    )

    cmd = [
        sys.executable,
        triage_runner,
        "--latest",
        "--no-post-gates",
        "--out",
        out_csv,
    ]
    subprocess.run(cmd, check=True, cwd=root)

    import pandas as pd

    df = pd.read_csv(out_csv)
    if "triage_verdict" not in df.columns:
        raise SystemExit("triage_latest_ops.csv missing triage_verdict")

    counts = df["triage_verdict"].value_counts(dropna=False).to_dict()
    applies = df[df["triage_verdict"] == "apply"]

    samples: list[dict[str, str]] = []
    for _, row in applies.head(25).iterrows():
        samples.append(
            {
                "company": str(row.get("company", ""))[:160],
                "title": str(row.get("title", ""))[:200],
                "job_url": str(row.get("job_url", ""))[:2048],
            }
        )

    payload = {
        "date_iso": date.today().isoformat(),
        "source_triage_csv": out_csv,
        "counts": {str(k): int(v) for k, v in counts.items()},
        "apply_sample": samples,
    }
    if args.dump_json:
        dump_path = os.path.abspath(os.path.expanduser(args.dump_json))
        os.makedirs(os.path.dirname(dump_path) or ".", exist_ok=True)
        with open(dump_path, "w", encoding="utf-8") as dj:
            json.dump(payload, dj, indent=2)
    if not args.quiet:
        print(json.dumps(payload, indent=2))

    rollup_path: str | None = None
    if args.append_rollup:
        rollup_path = os.path.abspath(os.path.expanduser(args.append_rollup))
    elif args.append_rollup_auto:
        rollup_path = os.path.join(
            rollup_dir, f"{date.today().isoformat()}.md"
        )

    if rollup_path:
        c_apply = payload["counts"].get("apply", 0)
        c_rev = payload["counts"].get("review", 0)
        c_skip = payload["counts"].get("skip", 0)
        block = "\n".join(
            [
                "",
                f"<!-- triage-bot {payload['date_iso']} -->",
                "## Morning triage (auto)",
                f"- apply={c_apply}, review={c_rev}, skip={c_skip}",
                f"- CSV: `{out_csv}`",
                "",
            ]
        )
        os.makedirs(os.path.dirname(rollup_path) or ".", exist_ok=True)
        with open(rollup_path, "a", encoding="utf-8") as fh:
            fh.write(block)


if __name__ == "__main__":
    main()
