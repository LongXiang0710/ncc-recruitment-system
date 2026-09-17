@echo off
cd /d "%~dp0"
for /f "tokens=2,*" %%A in ('reg query HKCU\Environment /v DIFY_API_KEY 2^>nul') do set "DIFY_API_KEY=%%B"
python server.py --host 0.0.0.0 --port 8116
pause
