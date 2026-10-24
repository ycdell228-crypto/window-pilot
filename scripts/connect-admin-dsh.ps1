param(
    [ValidateSet('Bridge','Direct')][string]$Mode = 'Bridge',
    [string]$Python = 'python',
    [string]$Profile = (Join-Path $env:USERPROFILE '.dsh\profiles\desktop'),
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$serviceFile = Join-Path $project '.local\admin-service\service.json'
$config = Join-Path $project 'config.local.json'
if (Test-Path -LiteralPath $Python -PathType Leaf) { $Python = (Resolve-Path -LiteralPath $Python).Path }
else { $Python = (Get-Command -Name $Python -CommandType Application -ErrorAction Stop).Source }
if (Test-Path -LiteralPath $serviceFile -PathType Leaf) {
    $service = Get-Content -LiteralPath $serviceFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($service.project -ne $project -or $service.python -ne $Python) { throw 'Use the same project/Python as the reviewed service install' }
    $config = $service.config
}
$patch = Join-Path $Profile 'cordis.patch.yml'
$bytes = [IO.File]::ReadAllBytes($patch)
$text = [Text.UTF8Encoding]::new($false,$true).GetString($bytes)
$matches = [regex]::Matches($text,'(?m)^(?<indent> *)- id: window-pilot-mcp *\r?$')
if ($matches.Count -ne 1) { throw 'Expected exactly one existing window-pilot-mcp plugin; no profile changes' }
$begin = $matches[0].Index
$indent = $matches[0].Groups['indent'].Value.Length
$end = $text.Length
foreach ($candidate in [regex]::Matches($text.Substring($begin + $matches[0].Length),'(?m)^(?<indent> *)- ')) {
    if ($candidate.Groups['indent'].Value.Length -le $indent) { $end = $begin + $matches[0].Length + $candidate.Index; break }
}
$block = $text.Substring($begin,$end-$begin)
if ($block -notmatch "name: ['`"]?(?:@deepseek-ai/dsh-mcp-client|window-pilot-dsh)" -or $block -notmatch 'serverName: *window_pilot' -or $block -notmatch 'transport: *stdio') { throw 'Unexpected plugin type/namespace/transport; inspect manually' }
$arguments = if ($Mode -eq 'Bridge') { @('-m','window_pilot','bridge','--service-file',$serviceFile) } else { @('-m','window_pilot','serve','--config',$config) }
$changes = [ordered]@{ command=(ConvertTo-Json -Compress $Python); args=(ConvertTo-Json -Compress $arguments); cwd=(ConvertTo-Json -Compress $project); PYTHONPATH=(ConvertTo-Json -Compress (Join-Path $project 'src')) }
$newBlock = $block
foreach ($field in $changes.Keys) {
    $pattern = '(?m)^( *' + [regex]::Escape($field) + ': *)[^\r\n]*(\r?)$'
    if ([regex]::Matches($newBlock,$pattern).Count -ne 1) { throw "Expected one inline $field field; no profile changes" }
    if ($field -eq 'args' -and $newBlock -notmatch '(?m)^ *args: *\[') { throw 'Multiline args require manual review; no profile changes' }
    $replacement = $changes[$field]
    $newBlock = [regex]::Replace($newBlock,$pattern,[Text.RegularExpressions.MatchEvaluator]{ param($m) $m.Groups[1].Value + $replacement + $m.Groups[2].Value })
}
if (-not $Apply) {
    [pscustomobject]@{ preview_only=$true; mode=$Mode; plugin='window-pilot-mcp'; command=$Python; args=$arguments; profile=$patch; changes='only command/args/cwd/PYTHONPATH inside this plugin block' } | ConvertTo-Json -Depth 5
    exit 0
}
if ($Mode -eq 'Bridge') {
    if (-not (Test-Path -LiteralPath $serviceFile)) { throw 'Install reviewed service first; profile unchanged' }
    $probe = & $Python -I -S (Join-Path $PSScriptRoot 'runtime_entry.py') executor-status --service-file $serviceFile
    if ($LASTEXITCODE -ne 0) { throw 'Actual administrator executor connection failed; profile unchanged' }
    $status = $probe | ConvertFrom-Json
    if (-not $status.health.executor.is_administrator -or $status.health.executor.mode -ne 'administrator_service') { throw 'Actual executor not verified high-integrity; profile unchanged' }
}
$backups = Join-Path $project '.local\backups'
[IO.Directory]::CreateDirectory($backups) | Out-Null
$backup = Join-Path $backups ('cordis.patch.before-' + $Mode.ToLowerInvariant() + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.yml')
[IO.File]::WriteAllBytes($backup,$bytes)
if ((Get-FileHash -LiteralPath $backup).Hash -ne (Get-FileHash -LiteralPath $patch).Hash) { throw 'Backup verification failed or profile changed; no write' }
$updated = $text.Substring(0,$begin) + $newBlock + $text.Substring($end)
$temporary = $patch + '.window-pilot-update.tmp'
[IO.File]::WriteAllText($temporary,$updated,[Text.UTF8Encoding]::new($false))
[IO.File]::Replace($temporary,$patch,[System.Management.Automation.Language.NullString]::Value)
Write-Output "Updated only window-pilot-mcp to $Mode. Backup: $backup. DSH stays ordinary; reconnect this plugin when idle."
