@echo off
cd /d "%~dp0"
echo 只读检查NocoBase接口和字段，不迁移数据。
python -m features.nocobase_sync.configure check
pause
