@echo off
rem DuctZip portable CLI launcher.
rem Uses the Python interpreter from PATH and keeps settings beside this file.
setlocal
set "DZ_ROOT=%~dp0"
set "PYTHONPATH=%DZ_ROOT%src"
set "DUCTZIP_PORTABLE_ROOT=%DZ_ROOT%"
if not defined DUCTZIP_SETTINGS_PATH set "DUCTZIP_SETTINGS_PATH=%DZ_ROOT%settings\settings.json"
python -m ductzip %*
exit /b %ERRORLEVEL%
