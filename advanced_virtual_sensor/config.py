"""Paths, constants, and toggles for the pipeline."""

from pathlib import Path

# Repository root (parent of package): .../virtual_sensor/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
