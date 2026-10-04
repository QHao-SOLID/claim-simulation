# Competition — Excel-first pricing game

Python is a **one-time data factory**. Every dataset, price and score lives in
Excel. Teams get the **base-world train history** and a **combined test set
covering all scenarios**; cheapest premium wins each policy; any scenario with
portfolio LR ≥ 100% disqualifies the team overall.

## Rules

- **Public train data**: base scenario only — `Train_Policies` + `Train_Claims`
  (one observed history, sanitized: no `CLAIM_LAMBDA`, no `BEHAVIOR_RISK`, no
  settlement internals).
- **Test set**: `Test_Policies` — all rounds stacked in one sheet with a
  `SCENARIO` column; attributes only, no claims. Teams fill `Submission`
  (`TEST_ID`, `PREMIUM`, bounds RM100–RM100,000).
- **Allocation**: lowest premium wins each policy; ties split equally
  (`1 / number of tied lowest prices`).
- **Scoring**: claims come from hidden replications of the same customers
  (5 seeds, pooled). `LR = shared claims / shared premium`, computed
  **per scenario**.
- **Disqualification**: LR ≥ 100% in any scenario → disqualified overall.
- **Missing entries**: a blank premium = no bid. That policy is not awarded to
  the team, and a test row with no bid from any team is won by nobody. A team
  that wins no business shows `no wins` (not Qualified, not DQ); DQ only
  triggers on LR ≥ 100% in a scenario where it actually won business.
- **Leaderboard**: total fractional policies won across all scenarios, among
  non-disqualified teams (`Master sheet` OVERALL block; `By_Scenario` shows
  the per-scenario breakdown).

## Organizer workflow

```bash
# One command builds everything (parallel scenario workers by default):
#   competition_dataset.xlsx  (ship to teams)
#   truth/test_truth.xlsx     (HIDDEN)
#   competition_master.xlsx   (organizer scoring)
python -m competition.build_dataset
#    options: --only base,freq_p10 --n 2000 --jobs 6 --test-years 2

# Rebuild only the master after changing the team list (fast):
python -m competition.make_master
```

Then:
1. Import each team's `TEST_ID,PREMIUM` into its staging sheet (`Team A`...
   column B, same row order). The merged `Subs` sheet does the rest.
2. `Master sheet`, `Alloc`, `By_Scenario` and `Checks` are formula-driven.
3. `Checks` must read 0 (except its informational rows) before publishing.
4. Winner = highest OVERALL Policies Won among Qualified teams.

## Flexible teams

Team count is **not fixed**:

- Edit [`teams.txt`](teams.txt) — one name per line (comments with `#`,
  blank lines ignored) — then run `python -m competition.make_master`.
- The master creates one staging sheet and one scoreboard column per name,
  and sizes every block automatically; names are sanitized to valid, unique
  Excel sheet names.
- Submission CSVs are the source of truth: after regenerating the master,
  re-import each team's prices.
- Or pass an explicit list: `--teams-file my_teams.txt` (text or JSON).

## Scaling scenarios

- Add/remove/edit entries in [`rounds.json`](rounds.json); the public test
  set, truth, and every master block/row scale with the list.
- Builds run in parallel: `--jobs N` (default: auto = number of rounds capped
  by CPU count); `--only` builds a subset (base is always included, since the
  train history comes from it).
- Cost scales linearly: one panel + one observed replay + one replay per
  scoring seed per scenario. Test rows per scenario are controlled by
  `--test-years` and the template `n`.

## Files

```
competition/
├─ rounds.json          scenario list (patches, labels) — scale freely
├─ teams.txt            team names, one per line — scale freely
├─ config.py            seeds, split sizes, bounds, paths
├─ sanitize.py          public/hidden column whitelists (leak guard)
├─ build_dataset.py     factory: public + hidden truth + master workbooks
├─ workbooks.py         xlsx writers (public, truth, master)
├─ make_master.py       rebuild master from saved artifacts (fast)
└─ rounds/              GENERATED (gitignored)
   ├─ competition_dataset.xlsx   public: base train + all-scenario test + submission
   ├─ competition_master.xlsx    organizer: import all teams, compare
   └─ truth/test_truth.xlsx      HIDDEN — never ship
```

## Anti-leak notes

- The engine is deterministic: hidden scoring seeds and scenario configs must
  never be published. `truth/` stays organizer-side.
- `sanitize.check_public_columns` fails loud if a forbidden column would ever
  reach a public frame; `tests/test_competition.py` enforces it in CI.
- Test claims exist only in the truth workbook; the public test set has
  pricing-time columns only.

## Reproducing the dataset

Same `rounds.json` + same seeds → identical workbooks. `panel.py` builds each
scenario's customer panel once (retention pinned so every customer stays all
years), then replays the engine's claim machinery per seed on that fixed
panel — seeds differ only in claim outcomes, never in customer attributes.
