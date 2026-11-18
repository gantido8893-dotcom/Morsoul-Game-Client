@echo off
cd /d "%~dp0"
echo ========================================================
echo   Building MorsoulLauncher.exe with PyInstaller
echo ========================================================
echo.

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo PyInstaller not found in .venv. Installing...
    uv pip install pyinstaller
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

