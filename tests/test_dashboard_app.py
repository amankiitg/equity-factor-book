"""The app must be launchable the way the Makefile launches it.

`streamlit run dashboard/app.py` puts the dashboard folder, not the repo
root, first on sys.path, so the app has to repair sys.path itself before it
imports the dashboard package.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Same conditions as `streamlit run dashboard/app.py`: the script folder is
# on sys.path and the working directory is not.
RUNNER = (
    "import sys; "
    "sys.path.insert(0, 'dashboard'); "
    "sys.path = [p for p in sys.path if p not in ('', '.')]; "
    "import runpy; "
    "runpy.run_path('dashboard/app.py', run_name='__main__')"
)


def test_app_runs_with_dashboard_folder_first_on_sys_path() -> None:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-c", RUNNER],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr
