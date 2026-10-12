@echo off
rem Zombie-proof wrapper: runs the flasher with Bypass without any
rem paste-split risk (batch files are not subject to PS execution policy).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0flash-board.ps1" %*
