param([string]$Python = 'python', [string]$Destination = '')
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
if (-not $Destination) { $Destination = Join-Path $project 'dist' }
$Destination = [IO.Path]::GetFullPath($Destination)
[IO.Directory]::CreateDirectory($Destination) | Out-Null
if (Get-ChildItem -LiteralPath $Destination -Filter 'window_pilot-*.whl') {
    throw 'A Window Pilot wheel already exists here; use a new destination after reviewing it.'
}
& $Python -m pip wheel --no-deps --wheel-dir $Destination $project
if ($LASTEXITCODE -ne 0) { throw 'Wheel build failed' }
Get-ChildItem -LiteralPath $Destination -Filter 'window_pilot-*.whl' | Get-FileHash -Algorithm SHA256
