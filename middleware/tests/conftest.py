"""Make `app.*` importable whether pytest is run from the repo root or from middleware/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
