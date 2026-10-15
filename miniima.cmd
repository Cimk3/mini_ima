@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Project Python environment is missing. See README.md for installation.
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m miniima %*
exit /b %errorlevel%
