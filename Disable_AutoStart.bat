@echo off
setlocal
title Disable SmartDesk Auto Start
powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'WorldClock' -ErrorAction SilentlyContinue; $l=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\WorldClock.lnk'; Remove-Item -LiteralPath $l -Force -ErrorAction SilentlyContinue"
echo SmartDesk / WorldClock will no longer start automatically when you sign in.
echo You can enable it again from Settings inside the app.
pause
