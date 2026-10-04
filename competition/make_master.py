"""Rebuild the organizer master workbook from saved artifacts (e.g. after
editing teams.txt to add/remove teams).

Reads the public dataset workbook + hidden truth workbook and writes the
master workbook with the scoreboard layout.

Usage:
  python -m competition.make_master
  python -m competition.make_master --teams-file my_teams.txt
"""

import argparse
from pathlib import Path

import pandas as pd

from . import config
from .build_dataset import resolve_team_names
from .workbooks import write_master_workbook


def main(argv=None):
    ap = argparse.ArgumentParser(description='Organizer master workbook')
    ap.add_argument('--rounds-dir', default=str(config.ROUNDS_DIR))
    ap.add_argument('--teams', type=int, default=0,
                    help='default team count when no teams file is used')
    ap.add_argument('--teams-file', default='', help='team names file (default: teams.txt)')
    ap.add_argument('--out', default='')
    args = ap.parse_args(argv)

    rounds_dir = Path(args.rounds_dir)
    truth_path = rounds_dir / 'truth' / config.TRUTH_WORKBOOK.name
    dataset_path = rounds_dir / config.PUBLIC_WORKBOOK.name
    if not truth_path.exists() or not dataset_path.exists():
        print('missing artifacts — run competition.build_dataset first')
        return 1

    truth = pd.read_excel(truth_path, sheet_name='Truth')
    dataset = pd.read_excel(dataset_path, sheet_name='Test_Policies')
    train_policies = pd.read_excel(dataset_path, sheet_name='Train_Policies')
    train_claims = pd.read_excel(dataset_path, sheet_name='Train_Claims')

    names = resolve_team_names(None, args.teams_file or None)
    out = Path(args.out) if args.out else rounds_dir / config.MASTER_WORKBOOK.name
    write_master_workbook(out, truth, dataset, train_policies=train_policies,
                          train_claims=train_claims,
                          n_teams=args.teams or config.N_TEAMS, team_names=names)
    n = len(names) if names else (args.teams or config.N_TEAMS)
    print(f'master workbook -> {out} ({n} teams)')
    print('Import each team into its staging sheet (column B), then read the Master sheet.')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
