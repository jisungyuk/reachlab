@echo off
:: Build ReachLab as a standalone executable using PyInstaller

set REPO_DIR=%~dp0
set DESKTOP=%USERPROFILE%\Desktop

cd /d "%REPO_DIR%\app"

pyinstaller ^
    --name ReachLab ^
    --windowed ^
    --onedir ^
    --noconfirm ^
    --icon "%REPO_DIR%assets\icon.ico" ^
    --distpath "%DESKTOP%" ^
    --workpath "%REPO_DIR%build" ^
    --specpath "%REPO_DIR%" ^
    main.py

:: Rename output folder (keep executable name unchanged)
if exist "%DESKTOP%\ReachLab_app" rmdir /s /q "%DESKTOP%\ReachLab_app"
rename "%DESKTOP%\ReachLab" "ReachLab_app"

:: Always copy config.json from source
if exist "%REPO_DIR%app\config.json" (
    copy /y "%REPO_DIR%app\config.json" "%DESKTOP%\ReachLab_app\config.json" >nul
)

echo.
echo Build complete!
echo ReachLab is on your Desktop — open ReachLab_app and run ReachLab.exe.
pause
