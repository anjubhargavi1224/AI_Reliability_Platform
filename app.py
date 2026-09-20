"""Verity AI - Root Streamlit Entrypoint for Cloud Deployment."""

import os
import sys
from pathlib import Path

# Ensure root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Execute frontend dashboard
import frontend.dashboard  # noqa: F401
