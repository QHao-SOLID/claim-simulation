"""Build the whole competition dataset ONCE:

  competition_dataset.xlsx   public: base train history + all-scenario test set
  truth/test_truth.xlsx      hidden: claim replications per test policy
  competition_master.xlsx    organizer scoring workbook (free team count)

Usage (from repo root):
  python -m competition.build_dataset
  python -m competition.build_dataset --n 2000 --jobs 6
  python -m competition.build_dataset --teams-file competition/teams.txt
  python -m competition.build_dataset --only base,freq_p10,severity_shock
"""

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from voltvision.assumptions import build_cfg, deep_merge, load_template
from voltvision.simulate import build_panel, replay_claims

from . import config
from .sanitize import (
    TEST_POLICY_COLS, TRAIN_CLAIM_COLS, TRAIN_POLICY_COLS,
    check_public_columns,
)
from .workbooks import (
    write_master_workbook, write_public_dataset, write_truth_workbook,
)


def load_rounds(path=None):
    """Round definitions: [{name, label, patch}, ...]."""
    path = path or config.ROUNDS_JSON
    rounds = json.loads(open(path, encoding='utf-8').read())
    if not isinstance(rounds, list) or not rounds:
        raise ValueError(f'{path}: expected a non-empty JSON list of rounds')
    return rounds


def load_team_names(path):
    """Team names from a .json list / {"teams": [...]} or a text file
    (one per line, commas allowed; blank lines and #-comments ignored)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'teams file not found: {p}')
    text = p.read_text(encoding='utf-8')
    if p.suffix.lower() == '.json':
        data = json.loads(text)
        names = data.get('teams') if isinstance(data, dict) else data
        names = [n for n in names if n]
    else:
        names = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            names.extend(t.strip() for t in line.split(',') if t.strip())
    return names or None


def resolve_team_names(teams, teams_file=None):
    """Names from an explicit file, else the default teams.txt, else count."""
    if teams_file:
        return load_team_names(teams_file)
    if config.TEAMS_FILE.exists():
        names = load_team_names(config.TEAMS_FILE)
        if names:
            return names
    return None


def _round_cfg(template, round_def, total_years, n=None):
    cfg = build_cfg(template, {'name': round_def['name'], **round_def.get('patch', {})})
    if n:
        cfg = deep_merge(cfg, {'n': int(n)})
    return deep_merge(cfg, {'n_years': total_years})


def _split_years(cfg, train_years):
    years = [cfg['cohort_year'] + i for i in range(cfg['n_years'])]
    return set(years[:train_years]), set(years[train_years:])


def _test_truth_frames(cfg, name, test_year_set, panel, observed, scoring_seeds):
    """Test policy frame + hidden truth frame for one round."""
    test = observed[observed['SIM_YEAR'].isin(test_year_set)].copy()
    test['TEST_ID'] = [f'{name}|{p}|{int(y)}'
                       for p, y in zip(test['POLID'], test['SIM_YEAR'])]
    test.insert(0, 'SCENARIO', name)
    test = test[['SCENARIO'] + TEST_POLICY_COLS].reset_index(drop=True)
    check_public_columns(test.columns, f'test_policies[{name}]')

    truth = test[['TEST_ID', 'SCENARIO', 'POLID', 'SIM_YEAR']].reset_index(drop=True)
    index = pd.MultiIndex.from_frame(truth[['POLID', 'SIM_YEAR']])
    for i, seed in enumerate(scoring_seeds, start=1):
        seed_book, _ = replay_claims(panel, cfg, seed)
        amounts = seed_book.set_index(['POLID', 'SIM_YEAR'])['CLAIM_AMOUNT']
        truth[f'CLAIMS_S{i}'] = amounts.reindex(index).to_numpy()
    return test, truth


def _build_round_frames(round_def, template, total_years, train_years, test_years,
                        panel_seed, observed_seed, scoring_seeds, n):
    """Worker: one round's panel + observed replay + truth (picklable args)."""
    cfg = _round_cfg(template, round_def, total_years, n)
    _, test_year_set = _split_years(cfg, train_years)
    panel = build_panel(cfg, panel_seed, total_years)
    observed, _ = replay_claims(panel, cfg, observed_seed)
    return _test_truth_frames(cfg, round_def['name'], test_year_set, panel,
                              observed, scoring_seeds)


def build_dataset(rounds, template, out_dir, train_years=None, test_years=None,
                  observed_seed=None, scoring_seeds=None, panel_seed=None,
                  n=None, n_teams=None, team_names=None, jobs=1, verbose=True):
    """Generate public dataset + hidden truth + master workbook. Returns paths.

    jobs > 1 builds independent scenario rounds in parallel processes; the
    base round is always built once in-process (its panel feeds the train set).
    """
    train_years = config.TRAIN_YEARS if train_years is None else int(train_years)
    test_years = config.TEST_YEARS if test_years is None else int(test_years)
    observed_seed = config.OBSERVED_SEED if observed_seed is None else int(observed_seed)
    scoring_seeds = list(scoring_seeds or config.SCORING_SEEDS)
    panel_seed = config.PANEL_SEED if panel_seed is None else int(panel_seed)
    total_years = train_years + test_years

    base_def = next((r for r in rounds if r['name'] == config.BASE_ROUND), None)
    if base_def is None:
        raise ValueError(f"round list must contain the base round {config.BASE_ROUND!r}")

    # --- base round (train history + its own test rows), built once ---------
    base_cfg = _round_cfg(template, base_def, total_years, n)
    train_year_set, base_test_years = _split_years(base_cfg, train_years)
    base_panel = build_panel(base_cfg, panel_seed, total_years)
    base_observed, base_claims = replay_claims(base_panel, base_cfg, observed_seed)

    train = base_observed[base_observed['SIM_YEAR'].isin(train_year_set)]
    train_policies = train[TRAIN_POLICY_COLS].reset_index(drop=True)
    check_public_columns(train_policies.columns, 'train_policies')

    train_claims = base_claims[base_claims['SIM_YEAR'].isin(train_year_set)]
    train_claims = train_claims[TRAIN_CLAIM_COLS].reset_index(drop=True)
    check_public_columns(train_claims.columns, 'train_claims')

    results = {}
    base_test, base_truth = _test_truth_frames(base_cfg, base_def['name'],
                                               base_test_years, base_panel,
                                               base_observed, scoring_seeds)
    results[base_def['name']] = (base_test, base_truth)
    if verbose:
        print(f"round {base_def['name']}: test rows {len(base_test)}")

    # --- other rounds: sequential or parallel -------------------------------
    others = [r for r in rounds if r['name'] != config.BASE_ROUND]
    if jobs and jobs > 1 and len(others) > 1:
        workers = min(int(jobs), len(others))
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(_build_round_frames, r, template, total_years,
                          train_years, test_years, panel_seed, observed_seed,
                          tuple(scoring_seeds), n): r['name']
                for r in others
            }
            for fut in as_completed(futures):
                name = futures[fut]
                test, truth = fut.result()
                results[name] = (test, truth)
                if verbose:
                    print(f"round {name}: test rows {len(test)}")
    else:
        for round_def in others:
            test, truth = _build_round_frames(
                round_def, template, total_years, train_years, test_years,
                panel_seed, observed_seed, list(scoring_seeds), n)
            results[round_def['name']] = (test, truth)
            if verbose:
                print(f"round {round_def['name']}: test rows {len(test)}")

    # --- assemble in round order --------------------------------------------
    test_policies = pd.concat([results[r['name']][0] for r in rounds],
                              ignore_index=True)
    truth_all = pd.concat([results[r['name']][1] for r in rounds],
                          ignore_index=True)

    # --- write workbooks -----------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    public_path = Path(out_dir) / config.PUBLIC_WORKBOOK.name
    truth_path = Path(out_dir) / 'truth' / config.TRUTH_WORKBOOK.name
    master_path = Path(out_dir) / config.MASTER_WORKBOOK.name
    truth_path.parent.mkdir(parents=True, exist_ok=True)

    names = team_names or resolve_team_names(n_teams)
    write_public_dataset(public_path, train_policies, train_claims, test_policies,
                         train_label=config.BASE_ROUND)
    write_truth_workbook(truth_path, truth_all)
    write_master_workbook(master_path, truth_all, test_policies,
                          train_policies=train_policies,
                          train_claims=train_claims,
                          n_teams=n_teams, team_names=names)

    if verbose:
        print(f"\ntrain rows {len(train_policies)} | train claims {len(train_claims)}")
        print(f"test rows {len(test_policies)} across "
              f"{test_policies['SCENARIO'].nunique()} scenarios")
        print(f"public -> {public_path}")
        print(f"hidden -> {truth_path}")
        print(f"master -> {master_path}")
    return public_path, truth_path, master_path


def main(argv=None):
    ap = argparse.ArgumentParser(description='Competition dataset factory (Excel-out)')
    ap.add_argument('--rounds', default=str(config.ROUNDS_JSON))
    ap.add_argument('--only', default='', help='comma-separated round names (base required)')
    ap.add_argument('--out', default=str(config.ROUNDS_DIR))
    ap.add_argument('--train-years', type=int, default=config.TRAIN_YEARS)
    ap.add_argument('--test-years', type=int, default=config.TEST_YEARS)
    ap.add_argument('--n', type=int, default=None, help='override template book size')
    ap.add_argument('--observed-seed', type=int, default=config.OBSERVED_SEED)
    ap.add_argument('--panel-seed', type=int, default=config.PANEL_SEED)
    ap.add_argument('--seeds', default=','.join(str(s) for s in config.SCORING_SEEDS),
                    help='hidden scoring seeds, comma-separated')
    ap.add_argument('--teams', type=int, default=0,
                    help='default team count when no teams file is used')
    ap.add_argument('--teams-file', default='', help='team names file (default: teams.txt)')
    ap.add_argument('--jobs', type=int, default=0,
                    help='parallel scenario workers (0 = auto)')
    args = ap.parse_args(argv)

    only = {s.strip() for s in args.only.split(',') if s.strip()} or None
    rounds = [r for r in load_rounds(args.rounds) if not only or r['name'] in only]
    if not any(r['name'] == config.BASE_ROUND for r in rounds):
        rounds.insert(0, next(r for r in load_rounds(args.rounds)
                              if r['name'] == config.BASE_ROUND))
    seeds = [int(s) for s in args.seeds.split(',') if s.strip()]
    names = resolve_team_names(None, args.teams_file or None)
    jobs = args.jobs if args.jobs > 0 else min(len(rounds), os.cpu_count() or 1)

    public, truth, master = build_dataset(
        rounds, load_template(), Path(args.out),
        train_years=args.train_years, test_years=args.test_years,
        observed_seed=args.observed_seed, scoring_seeds=seeds,
        panel_seed=args.panel_seed, n=args.n,
        n_teams=args.teams or config.N_TEAMS, team_names=names,
        jobs=jobs)
    print('done.' if public else '')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
