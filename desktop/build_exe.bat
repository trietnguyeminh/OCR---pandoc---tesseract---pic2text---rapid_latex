@echo off
REM ============================================================
REM  Build FormuDoc.exe  (run this on Windows, one time)
REM  Requires: Python 3.11/3.12 recommended. Node.js is OPTIONAL
REM  (a prebuilt UI ships in frontend\dist).
REM  Result:   desktop\dist\FormuDoc.exe  (double-click to run)
REM ============================================================
setlocal
cd /d "%~dp0"

REM Prefer Python 3.12 (widest wheel coverage); else 3.11; else default python.
set "PY=python"
py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if "%PY%"=="python" ( py -3.11 --version >nul 2>nul && set "PY=py -3.11" )

echo Using interpreter:
%PY% --version
echo.

echo [1/4] Installing Python dependencies (prefer prebuilt wheels)...
%PY% -m pip install --upgrade pip
%PY% -m pip install --prefer-binary -r ..\backend\requirements.txt || goto :err
%PY% -m pip install --prefer-binary pywebview pyinstaller || goto :err

echo [2/4] Preparing the web UI...
if exist "..\frontend\dist\index.html" (
  echo   Using prebuilt UI in frontend\dist  ^(Node.js not required^).
) else (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo   Node.js/npm not found and no prebuilt UI present.
    echo   Install Node.js LTS from https://nodejs.org and run again.
    goto :err
  )
  pushd ..\frontend
  call npm install || goto :err
  call npm run build || goto :err
  popd
)

echo [3/4] Packaging FormuDoc.exe with PyInstaller...
REM close any running instance so PyInstaller can overwrite the exe
taskkill /F /IM FormuDoc.exe >nul 2>nul
%PY% -m PyInstaller --noconfirm FormuDoc.spec || goto :err

echo [4/4] Done!
echo.
echo   Your app:  %~dp0dist\FormuDoc.exe
echo   Double-click it to launch FormuDoc in its own window.
echo.
echo   (Optional) For editable Word equations and OCR, install:
echo     - pandoc       https://pandoc.org/installing.html
echo     - tesseract    https://github.com/UB-Mannheim/tesseract/wiki
echo.
pause
exit /b 0

:err
echo.
echo Build failed. See the FIRST error above.
echo  - "build wheel from source"/GCC/meson error  -> install Python 3.12.
echo  - "npm is not recognized"                     -> already handled if
echo    frontend\dist exists; otherwise install Node.js LTS.
pause
exit /b 1
