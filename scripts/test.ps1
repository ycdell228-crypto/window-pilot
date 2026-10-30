param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $project 'src'
& $Python (Join-Path $PSScriptRoot 'test_runner.py')
exit $LASTEXITCODE
