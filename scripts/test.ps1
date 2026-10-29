param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $project 'src'
& $Python -m unittest discover -s (Join-Path $project 'tests') -v
exit $LASTEXITCODE
