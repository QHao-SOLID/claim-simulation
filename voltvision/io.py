"""Shared result store: one CSV per (scenario, seed) + one claims CSV + manifest.

Files (all generated — never hand-edit):
  results/<scenario>_s<seed>.csv         policy-year rows, columns = schema.COLS
  results/<scenario>_s<seed>_claims.csv  one row per claim, columns = schema.CLAIM_COLS
  results/manifest.json                  provenance per run: files, run facts,
                                         cfg SHA-256 and the resolved cfg

All simulation data only — never premium columns.
"""

import datetime as dt
import json
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


def save_claims_csv(scenario, seed, claims, out=None):
    """Write the claim-level CSV for one run; returns the path written."""
    out = Path(out) if out else RESULTS
    out.mkdir(parents=True, exist_ok=True)
    p = out / f'{result_stem(scenario, seed)}_claims.csv'
    claims.to_csv(p, index=False)
    return p


def load_manifest(out=None):
    """Run index {stem: entry}; empty dict when no run has happened yet."""
    p = (Path(out) if out else RESULTS) / 'manifest.json'
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {}


def update_manifest(stem, entry, out=None):
    """Record one run (files, run facts, cfg snapshot + hash) in the manifest."""
    out = Path(out) if out else RESULTS
    out.mkdir(parents=True, exist_ok=True)
    p = out / 'manifest.json'
    manifest = load_manifest(out)
    manifest[stem] = {'saved_at': dt.datetime.now().isoformat(timespec='seconds'), **entry}
    p.write_text(json.dumps(manifest, indent=1, default=str), encoding='utf-8')
    return manifest
