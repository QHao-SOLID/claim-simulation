"""VoltVision motor simulation: premium-independent engine + scenario runner.

This is the CORE library. It must never import `competition` — the competition
application is a consumer built on top (see competition/).

Layout (assumptions in JSON, nothing else — no pricing code exists here):
  schema.py       COLS / CLAIM_COLS — canonical column order
  assumptions.py  base_template.json + scenario patches + seeds.json
  simulate.py     gen / claim_lambda / simulate / simulate_book,
                  build_panel / replay_claims (public panel API)
  io.py           results CSV write (simulation data only)
  runner.py       the scenario x seed loop (used by run_scenarios.py)
"""

from .schema import CLAIM_COLS, COLS
from .assumptions import (
    load_template, load_seeds, build_cfg, validate, describe_patch, deep_merge,
)
from .simulate import (
    gen, claim_lambda, simulate, simulate_book,
    build_panel, replay_claims, PANEL_COLS,
)
from .runner import run_scenarios
from . import io

__version__ = "0.3.0"

__all__ = [
    "COLS", "CLAIM_COLS",
    "load_template", "load_seeds", "build_cfg", "validate", "describe_patch",
    "deep_merge",
    "gen", "claim_lambda", "simulate", "simulate_book",
    "build_panel", "replay_claims", "PANEL_COLS",
    "run_scenarios", "io",
]
