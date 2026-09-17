$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtime = Get-Command python -ErrorAction SilentlyContinue
if (-not $runtime) { throw 'Please install Python 3.10+ and add it to PATH.' }
& $runtime.Source server.py --host 0.0.0.0 --port 8116
