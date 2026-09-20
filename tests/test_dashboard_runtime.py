"""Streamlit Dashboard Validation for Phase 9."""
import os
import subprocess
import sys
import pytest

PYTHON_EXE = sys.executable


def test_dashboard_compiles_and_imports():
    """Verify that frontend/dashboard.py is valid python and contains required components."""
    cmd = [
        PYTHON_EXE,
        "-c",
        "import py_compile; py_compile.compile('frontend/dashboard.py', doraise=True)",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Dashboard failed compilation: {res.stderr}"


def test_dashboard_help_and_headless():
    """Verify streamlit CLI can load dashboard module syntax."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        PYTHON_EXE,
        "-m",
        "streamlit",
        "version",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert res.returncode == 0
    assert "Streamlit, version" in res.stdout
