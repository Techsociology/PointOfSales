@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Home Bar POS -- building installer (Windows)
echo ============================================================
echo.

:: Detect Python
set PY=
py --version >nul 2>&1
if not errorlevel 1 (set PY=py) else (
    python --version >nul 2>&1
    if not errorlevel 1 (set PY=python)
)

if "%PY%"=="" (
    echo ERROR: Python not found.
    echo Get Python from https://www.python.org/downloads/
    echo CHECK "Add Python to PATH" during install.
    pause & exit /b 1
)
echo Python found (%PY%): & %PY% --version & echo.

echo [1/4] Installing dependencies...
%PY% -m pip install --upgrade pip --quiet
%PY% -m pip install flask==3.0.3 werkzeug==3.0.3 flask-wtf==1.2.1 waitress==3.0.0 stripe>=9.0.0 pyinstaller --quiet
if errorlevel 1 (echo. & echo pip install failed. & pause & exit /b 1)
echo Dependencies OK. & echo.

echo [2/4] Building with PyInstaller...
if exist build\HomeBarPOS rmdir /s /q build\HomeBarPOS
if exist dist\HomeBarPOS  rmdir /s /q dist\HomeBarPOS

%PY% -m PyInstaller HomeBarPOS.spec --noconfirm
if errorlevel 1 (
    echo.
    echo BUILD FAILED. Common fixes:
    echo  - Run again (sometimes a retry works)
    echo  - Temporarily disable antivirus
    echo  - Try: %PY% -m pip install --upgrade pyinstaller
    pause & exit /b 1
)
echo PyInstaller done. & echo.

echo [3/4] Checking for NSIS to build installer...
set NSIS=
if exist "C:\Program Files (x86)\NSIS\makensis.exe" set NSIS=C:\Program Files (x86)\NSIS\makensis.exe
if exist "C:\Program Files\NSIS\makensis.exe"       set NSIS=C:\Program Files\NSIS\makensis.exe

if "%NSIS%"=="" (
    echo NSIS not found -- skipping installer creation.
    echo The app folder is ready at:  dist\HomeBarPOS\
    echo.
    echo To also get a single .exe installer:
    echo   1. Download NSIS free from https://nsis.sourceforge.io/Download
    echo   2. Install it, then run this bat again.
    echo.
    goto :done_no_installer
)

echo NSIS found. Building HomeBarPOS_Setup.exe installer...
"%NSIS%" HomeBarPOS_installer.nsi
if errorlevel 1 (
    echo NSIS build failed -- check HomeBarPOS_installer.nsi
    goto :done_no_installer
)

echo.
echo ============================================================
echo  [4/4] Done!
echo  Installer: HomeBarPOS_Setup.exe  (share this single file)
echo  App folder: dist\HomeBarPOS\     (also works standalone)
echo ============================================================
goto :end

:done_no_installer
echo ============================================================
echo  [4/4] Done! (no installer -- NSIS not installed)
echo  App folder:  dist\HomeBarPOS\
echo  Executable:  dist\HomeBarPOS\HomeBarPOS.exe
echo.
echo  To run: double-click HomeBarPOS.exe inside that folder.
echo  The WHOLE folder is needed, not just the .exe.
echo ============================================================

:end
echo.
pause
