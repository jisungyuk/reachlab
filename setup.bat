@echo off
:: Run once after cloning to set up desktop launchers.

set REPO_DIR=%~dp0
set DESKTOP=%USERPROFILE%\Desktop

:: Create Build launcher on Desktop
echo @echo off > "%DESKTOP%\BuildReachLab.bat"
echo cd /d "%REPO_DIR%" >> "%DESKTOP%\BuildReachLab.bat"
echo call "%REPO_DIR%build.bat" >> "%DESKTOP%\BuildReachLab.bat"

echo Setup complete! Double-click 'BuildReachLab.bat' on your Desktop to build.
pause
