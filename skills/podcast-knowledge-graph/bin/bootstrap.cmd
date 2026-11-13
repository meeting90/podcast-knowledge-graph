@echo off
rem Thin launcher: bin\bootstrap.cmd == python bin\bootstrap.py
rem Probes the interpreter first: the Windows Store aliases `python`/`python3`
rem exit with code 49 instead of running Python.
setlocal
if not "%PODCAST_KG_PYTHON%"=="" (
  "%PODCAST_KG_PYTHON%" -c "import sys;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    "%PODCAST_KG_PYTHON%" "%~dp0bootstrap.py" %*
    exit /b %ERRORLEVEL%
  )
)
python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if not errorlevel 1 (
  python "%~dp0bootstrap.py" %*
  exit /b %ERRORLEVEL%
)
py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0bootstrap.py" %*
  exit /b %ERRORLEVEL%
)
echo bootstrap: 需要 Python 3.10+，或先装 uv ^(https://docs.astral.sh/uv/^)：
echo   powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
echo 然后： py -3 "%~dp0bootstrap.py"
exit /b 1
