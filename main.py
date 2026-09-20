"""Verify the local Python environment and installed dependencies."""

import importlib
import sys
from importlib.metadata import version


DEPENDENCIES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pydantic": "pydantic",
    "streamlit": "streamlit",
    "pandas": "pandas",
    "numpy": "numpy",
    "python-dotenv": "dotenv",
    "pytest": "pytest",
    "httpx": "httpx",
    "pypdf": "pypdf",
    "defusedxml": "defusedxml",
}


def main() -> int:
    print("AI Reliability & Evaluation Platform")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Interpreter: {sys.executable}")

    failures = []

    if sys.version_info < (3, 12):
        failures.append("Python 3.12 or newer is required.")

    if sys.prefix == sys.base_prefix:
        failures.append("Run this script using the project virtual environment.")

    for distribution, module_name in DEPENDENCIES.items():
        try:
            importlib.import_module(module_name)
            print(f"PASS {distribution}: {version(distribution)}")
        except Exception as exc:
            failures.append(f"{distribution}: {type(exc).__name__}: {exc}")

    try:
        importlib.import_module("ai_reliability")
        print("PASS ai_reliability package import")
    except Exception as exc:
        failures.append(f"ai_reliability: {type(exc).__name__}: {exc}")

    if failures:
        print("\nPHASE 1 CHECKPOINT: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nPHASE 1 CHECKPOINT: PASS")
    print("Environment imports passed. See README.md for API, dashboard and batch commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
