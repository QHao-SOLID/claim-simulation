"""Competition constants and the scenario-round list.

Python generates data once; every price and every score lives in Excel.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'base_template.json'
ROUNDS_JSON = Path(__file__).resolve().parent / 'rounds.json'
ROUNDS_DIR = Path(__file__).resolve().parent / 'rounds'

# Public train data comes from this round only; test data covers all rounds.
BASE_ROUND = 'base'

# Data split and seeds (hidden from teams).
TRAIN_YEARS = 3
TEST_YEARS = 2
PANEL_SEED = 20260916
OBSERVED_SEED = 42
SCORING_SEEDS = [67, 69, 7, 13, 21]

# Submission bounds enforced in Excel data validation.
PREMIUM_MIN = 100
PREMIUM_MAX = 100000

# Team columns/sheets in the master workbook. Edit teams.txt to change names
# or count; regenerate the master (`make_master`) and re-import submissions.
N_TEAMS = 20
TEAMS_FILE = Path(__file__).resolve().parent / 'teams.txt'

# Generated artifacts.
PUBLIC_WORKBOOK = ROUNDS_DIR / 'competition_dataset.xlsx'
TRUTH_WORKBOOK = ROUNDS_DIR / 'truth' / 'test_truth.xlsx'
MASTER_WORKBOOK = ROUNDS_DIR / 'competition_master.xlsx'
