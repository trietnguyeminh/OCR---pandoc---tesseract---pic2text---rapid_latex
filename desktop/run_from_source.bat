@echo off
REM Run FormuDoc in a native window WITHOUT building an exe.
REM Recommended: Python 3.11/3.12. Node.js OPTIONAL (prebuilt UI ships in dist).
setlocal
cd /d "%~dp0"

set "PY=python"
py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if "%PY%"=="python" ( py -3.11 --version >nul 2>nul && set "PY=py -3.11" )

echo Using interpreter:
%PY% --version

echo Installing dependencies (first run only, prefer prebuilt wheels)...
%PY% -m pip install --upgrade pip
%PY% -m pip install --prefer-binary -r ..\backend\requirements.txt || goto :err
%PY% -m pip install --prefer-binary pywebview || goto :err

if not exist "..\frontend\dist\index.html" (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo No prebuilt UI and no Node.js. Install Node.js LTS from https://nodejs.org
    goto :err
  )
  pushd ..\frontend
  call npm install || goto :err
  call npm run build || goto :err
  popd
)

echo Launching FormuDoc...
%PY% ..\run_formudoc.py
exit /b 0

:err
echo.
echo Setup failed. See the first error above.
pause
exit /b 1
