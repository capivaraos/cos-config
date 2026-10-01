#!/usr/bin/env python3
"""Developer launcher: run straight from the source tree without installing.

    python3 run.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from cos_config.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
