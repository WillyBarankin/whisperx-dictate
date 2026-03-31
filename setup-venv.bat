@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set FOUND=
for %%V in (3.12 3.13 3.11 3.10) do (
  py -%%V -c "import sys" 2>nul
  if not errorlevel 1 (
    set "FOUND=%%V"
    goto :create
  )
)
echo Install Python 3.10-3.13 from https://www.python.org/downloads/
echo WhisperX does not support Python 3.14 yet; pip cannot install torch 2.8 on 3.14.
echo During setup, enable the "py" launcher.
exit /b 1

:create
py -!FOUND! -m venv .venv
if errorlevel 1 exit /b 1

call .venv\Scripts\activate.bat
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo Done ^(Python !FOUND!^).
echo   Git Bash:  source .venv/Scripts/activate
echo   CMD:       .venv\Scripts\activate.bat
exit /b 0
