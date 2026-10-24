param([string]$Python = 'python', [string]$Config = '')
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
if (-not $Config) { $Config = Join-Path $project 'config.local.json' }
$env:PYTHONPATH = Join-Path $project 'src'
& $Python -m window_pilot serve --config $Config
exit $LASTEXITCODE
