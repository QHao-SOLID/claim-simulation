"""Simulate every scenario group and write one CSV per (scenario, seed).

Examples:
  python run_scenarios.py                     # all scenarios x seeds.json, full size
  python run_scenarios.py --quick             # smoke: n=1000, 2 years
  python run_scenarios.py --scenarios MIX,base
  python run_scenarios.py --seeds 42,67,69    # override seeds.json
  python run_scenarios.py --grid scenarios/frequency.json
  python run_scenarios.py --out my_results

Output: results/<scenario>_s<seed>.csv — simulation data only (attributes +
claims; never premium columns). The engine is premium-independent: same seed
+ same cfg = identical CSV.
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from voltvision import run_scenarios


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description='Premium-independent motor simulation runner (CSV out)')
    ap.add_argument('--grid', default='scenarios',
                    help='scenario directory or single .json file (default scenarios/)')
    ap.add_argument('--scenarios', default='',
                    help='subset of scenario names (comma-separated; default: all)')
    ap.add_argument('--seeds', default='',
                    help='override seeds.json, e.g. 42,67,69')
    ap.add_argument('--quick', action='store_true', help='smoke: n=1000, 2 years')
    ap.add_argument('--out', default='',
                    help='output directory (default results/)')
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    names = {s.strip() for s in args.scenarios.split(',') if s.strip()} or None
    seeds = [int(s) for s in args.seeds.split(',') if s.strip()] if args.seeds else None
    results = run_scenarios(grid=args.grid, scenario_names=names, seeds=seeds,
                            quick=args.quick, out=args.out or None)
    if results.empty:
        print('no scenarios selected.')
        return 1
    print('\n=== runs (premium-independent simulation data) ===')
    print(results[['scenario', 'seed', 'policies', 'rows', 'claims', 'claim_amount']]
          .to_string(index=False))
    print('\ndone.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
