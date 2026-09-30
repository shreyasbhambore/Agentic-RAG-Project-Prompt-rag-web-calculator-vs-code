"""FastAPI application package."""

# Some Windows-managed Python installations cannot write optional ML packages
# globally. Keep the local vendor directory as a fallback for packages that are
# not installed in the active environment.
from pathlib import Path
import sys

VENDOR_DIRECTORY = Path(__file__).resolve().parents[1] / "vendor"
if VENDOR_DIRECTORY.is_dir() and str(VENDOR_DIRECTORY) not in sys.path:
    sys.path.append(str(VENDOR_DIRECTORY))
