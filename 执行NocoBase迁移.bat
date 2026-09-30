@echo off
setlocal
cd /d "%~dp0"
if defined RECRUIT_DATA_DIR (set "MIGRATION_DB=%RECRUIT_DATA_DIR%\recruitment.db") else (set "MIGRATION_DB=%~dp0data\recruitment.db")
python -m features.nocobase_sync.migration_cli apply "%MIGRATION_DB%"
if errorlevel 1 echo 迁移未完成，数据源没有启用；请查看脱敏报告后重试。
pause
