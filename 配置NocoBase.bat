@echo off
cd /d "%~dp0"
python -m features.nocobase_sync.configure
pause
