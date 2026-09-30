@echo off
cd /d "%~dp0"
echo 此入口已同时启用简历收集和招聘人才库。
python -m features.nocobase_sync.configure enable
pause
