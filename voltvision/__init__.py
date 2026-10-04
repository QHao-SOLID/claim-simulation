"""VoltVision motor simulation: premium-independent engine + scenario runner.

Layout (assumptions in JSON, nothing else — no pricing code exists here):
  schema.py       COLS — canonical simulated-book column order
  assumptions.py  base_template.json + scenario patches + seeds.json
  simulate.py     gen / claim_lambda / simulate / simulate_book
  io.py           results CSV write (simulation data only)
  runner.py       the scenario x seed loop (used by run_scenarios.py)
"""

from .schema import COLS
from .assumptions import (
    load_template, load_seeds, build_cfg, validate, describe_patch, deep_merge,
)
from .simulate import gen, claim_lambda, simulate, simulate_book
from .runner import run_scenarios
from . import io

__version__ = "0.3.0"

__all__ = [
    "COLS",
    "load_template", "load_seeds", "build_cfg", "validate", "describe_patch",
    "deep_merge",
    "gen", "claim_lambda", "simulate", "simulate_book",
    "run_scenarios", "io",
]
