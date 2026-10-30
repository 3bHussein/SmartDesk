@echo off
setlocal
cd /d "%~dp0"
title SmartDesk 1.0.9.5 - Windows Build
echo ==========================================
echo       SMARTDESK 1.0.9.5 - QR FIX
echo ==========================================
echo.
python --version
if errorlevel 1 (
  echo Python was not found. Install Python 3.11+ and enable Add Python to PATH.
  pause
  exit /b 1
)
if not exist "assets\smartdesk.ico" (
  echo ERROR: assets\smartdesk.ico is missing.
  pause
  exit /b 1
)
echo.
echo Installing dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Cleaning only the 1.0.9.5 build output...
if exist "dist\SmartDesk_1.0.9.5" rmdir /s /q "dist\SmartDesk_1.0.9.5"
if exist "build\SmartDesk_1.0.9.5" rmdir /s /q "build\SmartDesk_1.0.9.5"
mkdir "build\SmartDesk_1.0.9.5"
echo.
echo Building SmartDesk 1.0.9.5...
python -m PyInstaller --noconfirm --clean --onefile --windowed --icon "%~dp0assets\smartdesk.ico" --add-data "%~dp0assets\smartdesk.ico;assets" --collect-all tzdata --collect-all pycountry --collect-all qrcode --name SmartDesk --distpath "dist\SmartDesk_1.0.9.5" --workpath "build\SmartDesk_1.0.9.5" --specpath "build\SmartDesk_1.0.9.5" worldclock.pyw
if errorlevel 1 goto failed
if not exist "dist\SmartDesk_1.0.9.5\SmartDesk.exe" (
  echo ERROR: SmartDesk.exe was not created.
  goto failed
)
echo.
echo ==========================================
echo BUILD SUCCESSFUL
echo ==========================================
echo Executable:
echo %CD%\dist\SmartDesk_1.0.9.5\SmartDesk.exe
echo Version: 1.0.9.5
echo App icon: assets\smartdesk.ico
echo Existing user database and settings are preserved.
echo.
start "" "%CD%\dist\SmartDesk_1.0.9.5\SmartDesk.exe"
pause
exit /b 0
:failed
echo.
echo BUILD FAILED. Read the error above and do not run an older executable.
pause
exit /b 1
