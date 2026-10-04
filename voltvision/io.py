"""Shared result store: one CSV per (scenario, seed) — simulation data only.

Files (all generated — never hand-edit):
  results/<scenario>_s<seed>.csv   one row per policy-year, columns = schema.COLS
                                   (attributes + claims; never premium columns)
"""

from pathlib import Path

from .schema import COLS

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / 'results'


def result_stem(scenario, seed):
    """File stem for one run — always seed-suffixed, e.g. 'base_s42'."""
    return f'{scenario}_s{int(seed)}'


def sim_book(df):
    """The simulated book: exactly schema.COLS, no premium columns."""
    return df[COLS].copy()


def save_csv(scenario, seed, book, out=None):
    """Write one simulated book to CSV; returns the path written."""
    out = Path(out) if out else RESULTS
    out.mkdir(parents=True, exist_ok=True)
    p = out / f'{result_stem(scenario, seed)}.csv'
    sim_book(book).to_csv(p, index=False)
    return p
