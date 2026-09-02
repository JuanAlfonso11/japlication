import sys
from pathlib import Path

# Ensure `app` is importable when pytest is run from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
