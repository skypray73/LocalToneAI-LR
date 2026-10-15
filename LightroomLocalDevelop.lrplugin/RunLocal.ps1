param([Parameter(Mandatory=$true)][string]$Job)
$ErrorActionPreference = 'Stop'
$pythonExe = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe = (Get-Command python -ErrorAction Stop).Source }
$runner = Join-Path $PSScriptRoot '..\scripts\run_lightroom_job.py'
if (-not (Test-Path -LiteralPath $runner)) { $runner = Join-Path $PSScriptRoot '..\..\scripts\run_lightroom_job.py' }
& $pythonExe $runner --job $Job
exit $LASTEXITCODE
