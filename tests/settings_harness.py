"""Test harness: force DuctZip settings onto a throwaway path.

Importing this module sets DUCTZIP_SETTINGS_PATH so CLI/GUI tests never
read (or write) the developer's real per-user settings. unittest discover
does not collect this module (name does not match test*.py).
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

_directory = tempfile.TemporaryDirectory(prefix="dz-test-settings-")
os.environ["DUCTZIP_SETTINGS_PATH"] = str(Path(_directory.name) / "settings.json")
