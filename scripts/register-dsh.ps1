param(
    [Parameter(Mandatory=$true)][string]$Python,
    [string]$Profile = (Join-Path $env:USERPROFILE '.dsh\profiles\desktop'),
    [string]$Config = ''
)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
if (-not $Config) { $Config = Join-Path $project 'config.local.json' }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python executable not found' }
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'Create config.local.json first; keep daily_authorized=false' }
$patch = Join-Path $Profile 'cordis.patch.yml'
if (-not (Test-Path -LiteralPath $patch -PathType Leaf)) { throw 'Expected existing desktop profile patch' }
$bytes = [IO.File]::ReadAllBytes($patch)
$text = [Text.Encoding]::UTF8.GetString($bytes)
if ($text -match '(?m)^\s*- id: window-pilot-mcp\s*$') { Write-Output 'Already registered; no changes'; exit 0 }
if ($text -match 'serverName:\s*window_pilot') { throw 'Namespace already in use; inspect existing configuration' }
$backupDir = Join-Path $project '.local\backups'
[IO.Directory]::CreateDirectory($backupDir) | Out-Null
$backup = Join-Path $backupDir ('cordis.patch.pre-window-pilot-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.yml')
[IO.File]::WriteAllBytes($backup, $bytes)
if ((Get-FileHash -LiteralPath $patch).Hash -ne (Get-FileHash -LiteralPath $backup).Hash) { throw 'Backup verification failed' }
# JSON strings are valid YAML scalar/array values. No shell command interpolation.
$command = ConvertTo-Json -Compress $Python
$directory = ConvertTo-Json -Compress $project
$source = ConvertTo-Json -Compress (Join-Path $project 'src')
$arguments = ConvertTo-Json -Compress @('-m', 'window_pilot', 'serve', '--config', $Config)
$addition = @"

- insert:
    - id: window-pilot-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: window_pilot
        transport: stdio
        command: $command
        args: $arguments
        cwd: $directory
        env:
          PYTHONPATH: $source
          PYTHONUTF8: '1'
          PYTHONUNBUFFERED: '1'
        toolCallTimeoutMs: 30000
        failOnStartupError: false
"@
$newBytes = [Text.UTF8Encoding]::new($false).GetBytes($addition + "`n")
$stream = [IO.File]::Open($patch, [IO.FileMode]::Append, [IO.FileAccess]::Write)
try { $stream.Write($newBytes, 0, $newBytes.Length) } finally { $stream.Dispose() }
$after = [IO.File]::ReadAllBytes($patch)
for ($index = 0; $index -lt $bytes.Length; $index++) {
    if ($after[$index] -ne $bytes[$index]) { throw 'Original profile prefix changed unexpectedly' }
}
Write-Output "Registered window_pilot only. Backup: $backup"
Write-Output 'DSH must reload its profile before tools appear; no schedules were created.'
