#!/usr/bin/env python3
"""Phase 0.5: groupby l1_pipeline_fail_rule on latest full jobspy_results CSV.

Usage:
  python3 scripts/audit_l1_pipeline_fail_rules.py
  python3 scripts/audit_l1_pipeline_fail_rules.py /path/to/jobspy_results_YYYYMMDD.csv

Prints rule counts and a small sample per non-empty rule. No scraper changes.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _latest_full_csv(results_dir: str) -> str:
    pattern = os.path.join(results_dir, 'jobspy_results_*.csv')
    candidates = [
        p for p in glob.glob(pattern)
        if '_new' not in os.path.basename(p)
    ]
    if not candidates:
        raise SystemExit(f'no full jobspy_results_*.csv under {results_dir}')
    return max(candidates, key=os.path.getmtime)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'csv_path',
        nargs='?',
        help='full jobspy_results_YYYYMMDD.csv (default: newest in jobspy/results/)',
    )
    parser.add_argument(
        '--sample', type=int, default=3,
        help='sample rows per non-empty fail rule (default: 3)',
    )
    args = parser.parse_args()
    csv_path = args.csv_path or _latest_full_csv(
        os.path.join(_PROJECT, 'jobspy', 'results'),
    )

    try:
        import pandas as pd
    except ImportError:
        print('pandas required: pip install pandas', file=sys.stderr)
        return 1

    df = pd.read_csv(csv_path)
    if 'l1_pipeline_fail_rule' not in df.columns:
        raise SystemExit(f'missing l1_pipeline_fail_rule column in {csv_path}')

    col = df['l1_pipeline_fail_rule'].fillna('').astype(str)
    counts = col.value_counts(dropna=False)
    print(f'CSV: {csv_path}')
    print(f'rows: {len(df)}')
    print()
    print('l1_pipeline_fail_rule counts:')
    for rule, n in counts.items():
        label = '(pass)' if rule == '' else rule
        print(f'  {label!r}: {n}')

    print()
    print('samples (non-empty rules):')
    for rule in counts.index:
        if rule == '':
            continue
        subset = df[col == rule].head(args.sample)
        print(f'--- {rule} ---')
        for _, row in subset.iterrows():
            title = str(row.get('title', ''))[:60]
            company = str(row.get('company', ''))[:40]
            print(f'  {company} | {title}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
