#!/usr/bin/env python3
"""Run the getcheapapi CLI from this skill.

Uses the installed package when there is one (pip install getcheapapi); otherwise the src/ folder of the
getcheapapi repository this skill was linked from. Standard library only.
"""
import sys
from pathlib import Path

try:
    import getcheapapi  # noqa: F401
except ImportError:
    src = Path(__file__).resolve().parents[3] / "src"  # scripts -> skill -> skills -> repo root
    if not (src / "getcheapapi").is_dir():
        sys.exit("getcheapapi is not installed. Install it with `pip install getcheapapi`, "
                 "or link this skill from a clone of the getcheapapi repository.")
    sys.path.insert(0, str(src))

from getcheapapi.cli import main  # noqa: E402

main()
