@echo off
rem DuctZip portable GUI launcher.
rem Requires PySide6 in the active Python environment (pip install PySide6).
setlocal
set "DZ_ROOT=%~dp0"
set "PYTHONPATH=%DZ_ROOT%src"
set "DUCTZIP_PORTABLE_ROOT=%DZ_ROOT%"
if not defined DUCTZIP_SETTINGS_PATH set "DUCTZIP_SETTINGS_PATH=%DZ_ROOT%settings\settings.json"
start "" pythonw -m ductzip.gui %*
