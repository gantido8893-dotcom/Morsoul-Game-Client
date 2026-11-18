@echo off
cd /d "%~dp0"
echo ========================================================
echo   Building MorsoulLauncher.exe with PyInstaller
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment with Python 3.12...
    uv venv --python 3.12 .venv
)

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo Installing dependencies and PyInstaller in .venv...
    uv pip install -e . pyinstaller
)

.\.venv\Scripts\pyinstaller.exe MorsoulLauncher.spec --clean --noconfirm

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo   BUILD SUCCESSFUL!
    echo   Executable created at: dist\MorsoulLauncher.exe
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo   BUILD FAILED! Check error output above.
    echo ========================================================
)

pause

