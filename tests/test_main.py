"""Smoke test for the documented module entry point."""

from pathlib import Path
import subprocess
import sys


def test_module_entry_point_runs_successfully() -> None:
    """The documented launch command must work from the project root."""
    project_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "src.main"],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "J1 Match Predictor" in completed.stdout
