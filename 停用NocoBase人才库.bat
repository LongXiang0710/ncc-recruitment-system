@echo off
cd /d "%~dp0"
echo 此入口将同时停用简历收集和招聘人才库的NocoBase数据源。
python -m features.nocobase_sync.configure disable
pause
