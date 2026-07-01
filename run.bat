@echo off
REM Double-click to run FormuDoc from the LATEST source (no exe rebuild needed).
setlocal
cd /d "%~dp0"

set "PY="
if not defined PY ( py -3.12 --version >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( py -3    --version >nul 2>nul && set "PY=py -3" )
if not defined PY ( python   --version >nul 2>nul && set "PY=python" )
if not defined PY ( for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-*") do @if exist "%%D\python.exe" set PY="%%D\python.exe" )
if not defined PY (
  echo Khong tim thay Python. Cai Python 3.12 tu python.org roi chay lai.
  pause & exit /b 1
)

echo Dang chay FormuDoc (source moi nhat) bang: %PY%
%PY% run_formudoc.py
pause
