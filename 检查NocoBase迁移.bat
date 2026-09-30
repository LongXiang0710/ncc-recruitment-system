@echo off
setlocal
cd /d "%~dp0"
if defined RECRUIT_DATA_DIR (set "MIGRATION_DB=%RECRUIT_DATA_DIR%\recruitment.db") else (set "MIGRATION_DB=%~dp0data\recruitment.db")
python -m features.nocobase_sync.migration_cli check "%MIGRATION_DB%"
if errorlevel 1 echo 检查未通过，禁止执行迁移和启用。
pause
