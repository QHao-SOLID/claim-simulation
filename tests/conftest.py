import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FROZEN_TEMPLATE = Path(__file__).resolve().parent / 'data' / 'template_frozen.json'
