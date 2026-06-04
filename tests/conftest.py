"""pytest-select test harness."""

import sys
from pathlib import Path

# Ensure plugin is importable when running from repo root
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURE = Path(__file__).parent / "fixtures" / "sample_project"
OPTIONAL_DEPS_FIXTURE = Path(__file__).parent / "fixtures" / "optional_deps_project"
