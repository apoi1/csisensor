@echo off
rem Double-click launcher: broker + CSI simulator + desktop GUI + LAN web viewer.
rem Each component opens in its own PowerShell window; the web viewer
rem auto-opens the default browser at http://<host>:8080.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_all.ps1" %*
