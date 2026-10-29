param(
    [ValidateSet('Plan','Install','Status','Start','Stop','Disable','Enable','Uninstall')][string]$Action = 'Plan',
    [string]$Python = 'python', [string]$Config = '', [switch]$Apply,
    [string]$ExpectedSid = ''
)
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$runtime = Join-Path $project '.local\admin-service'
$manifest = Join-Path $runtime 'service.json'
$entry = Join-Path $PSScriptRoot 'runtime_entry.py'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$sid = $identity.User.Value
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$admin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$session = [Diagnostics.Process]::GetCurrentProcess().SessionId
if ($session -eq 0 -or ($ExpectedSid -and $sid -ne $ExpectedSid)) { throw 'Requires the same logged-in user, not SYSTEM/session 0 or another administrator account' }
$digest = [Security.Cryptography.SHA256]::Create()
try { $tag = ([BitConverter]::ToString($digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($sid + '|' + $project)))).Replace('-','').Substring(0,16).ToLowerInvariant() } finally { $digest.Dispose() }
$taskName = 'WindowPilot-WindowService-' + $tag
$marker = 'WindowPilot administrator window executor: ' + $project
function Quote-Argument([string]$Value) {
    if ($Value.Contains('"')) { throw 'Unexpected quote in an argument' }
    return '"' + $Value + '"'
}
function Escape-Xml([string]$Value) { return [Security.SecurityElement]::Escape($Value) }
function Existing-Task {
    $task = Get-ScheduledTask -TaskPath '\' -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task -and $task.Description -ne $marker) { throw 'Task name belongs to another installation; refusing to modify it' }
    return $task
}
function Existing-Settings {
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { throw 'No installed service manifest; first review Plan then Install -Apply' }
    $value = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($value.user_sid -ne $sid -or $value.project -ne $project -or $value.task_name -ne $taskName) { throw 'Installed manifest does not match this user/project/task' }
    return $value
}
function Call-Executor([string]$Command) {
    $value = Existing-Settings
    & $value.python -I -S $entry $Command --service-file $manifest
    if ($LASTEXITCODE -ne 0) { throw 'Executor command failed; no automatic restart/replay' }
}
if ($Action -eq 'Status') {
    $task = Existing-Task
    [pscustomobject]@{ task_name=$taskName; task_registered=[bool]$task; task_state=if($task){[string]$task.State}else{'not_installed'}; user_sid=$sid; session=$session } | ConvertTo-Json
    if (Test-Path -LiteralPath $manifest -PathType Leaf) {
        try { Call-Executor 'executor-status' }
        catch {
            $info = if ($task) { Get-ScheduledTaskInfo -TaskPath '\' -TaskName $taskName } else { $null }
            $failure = Get-ChildItem -LiteralPath $runtime -Filter 'startup-error-*.json' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            [pscustomobject]@{ connected=$false; error=[string]$_; last_task_result=if($info){$info.LastTaskResult}else{$null}; startup_diagnostic=if($failure){$failure.FullName}else{$null}; automatic_retry=$false } | ConvertTo-Json
            exit 1
        }
    }
    exit 0
}
if ($Action -in @('Start','Stop')) {
    if (-not $Apply) { Write-Output "Preview only. $Action -Apply changes service state, not user windows."; exit 0 }
    if ($Action -eq 'Stop') { Call-Executor 'executor-stop'; exit 0 }
    $task = Existing-Task
    if (-not $task -or $task.State -eq 'Disabled') { throw 'Task absent/disabled; explicitly install or enable first' }
    Start-ScheduledTask -TaskPath '\' -TaskName $taskName
    Write-Output 'Requested this dedicated service task only. Run Status; no actions or failed calls are replayed.'
    exit 0
}
if ($Action -ne 'Plan' -and -not $Apply) {
    Write-Output "Preview only: use -Action Plan to review files, then -Action $Action -Apply for the explicit system change."
    exit 0
}
# Only these explicit Apply operations request UAC; no elevation during Plan/Status/ordinary tools.
if ($Action -in @('Install','Disable','Enable','Uninstall') -and -not $admin) {
    $arguments = @('-NoProfile','-File',$PSCommandPath,'-Action',$Action,'-Apply','-Python',$Python,'-ExpectedSid',$sid)
    if ($Config) { $arguments += @('-Config',$Config) }
    $argumentLine = ($arguments | ForEach-Object { Quote-Argument $_ }) -join ' '
    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $argumentLine -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Administrator operation failed ($($process.ExitCode)); inspect this installation before retrying" }
    Write-Output 'Administrator operation finished. Status is the read-only runtime check.'
    exit 0
}
if ($Action -in @('Disable','Enable','Uninstall')) {
    $null = Existing-Settings
    $task = Existing-Task
    if (-not $task) { throw 'Dedicated task not installed; no other tasks were changed' }
    if ($Action -in @('Disable','Uninstall')) {
        Disable-ScheduledTask -TaskPath '\' -TaskName $taskName | Out-Null
        # Disable does not kill a process. Ask only this same-user executor to stop.
        try { Call-Executor 'executor-stop' } catch { Stop-ScheduledTask -TaskPath '\' -TaskName $taskName }
    } else { Enable-ScheduledTask -TaskPath '\' -TaskName $taskName | Out-Null }
    if ($Action -eq 'Uninstall') {
        $backup = Join-Path $runtime ('task.before-uninstall-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.xml')
        [IO.File]::WriteAllText($backup,(Export-ScheduledTask -TaskPath '\' -TaskName $taskName),[Text.Encoding]::Unicode)
        Unregister-ScheduledTask -TaskPath '\' -TaskName $taskName -Confirm:$false
    }
    Write-Output "$Action completed for $taskName only. Private history/config retained; no user software closed."
    exit 0
}
if (-not $Config) { $Config = Join-Path $project 'config.local.json' }
$Config = [IO.Path]::GetFullPath($Config)
if (-not $Config.StartsWith($project.TrimEnd('\') + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Config must stay inside this project' }
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'Config file missing' }
if (Test-Path -LiteralPath $Python -PathType Leaf) { $Python = (Resolve-Path -LiteralPath $Python).Path }
else { $Python = (Get-Command -Name $Python -CommandType Application -ErrorAction Stop).Source }
$executorPython = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $executorPython -PathType Leaf)) { throw 'Matching pythonw.exe is required to start the executor without a console window' }
$settings = [ordered]@{ version=1; project=$project; config=$Config; python=$Python; executor_python=$executorPython; user_sid=$sid; task_name=$taskName; pipe_base=('\\.\pipe\WindowPilot.'+$tag) }
$actionArgs = (@('-I','-S',$entry,'admin-serve','--service-file',$manifest) | ForEach-Object { Quote-Argument $_ }) -join ' '
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>$(Escape-Xml $marker)</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>$(Escape-Xml $sid)</UserId><Delay>PT10S</Delay></LogonTrigger></Triggers>
  <Principals><Principal id="WindowPilotUser"><UserId>$(Escape-Xml $sid)</UserId><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>false</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><Hidden>false</Hidden><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT0S</ExecutionTimeLimit></Settings>
  <Actions Context="WindowPilotUser"><Exec><Command>$(Escape-Xml $executorPython)</Command><Arguments>$(Escape-Xml $actionArgs)</Arguments><WorkingDirectory>$(Escape-Xml $project)</WorkingDirectory></Exec></Actions>
</Task>
"@
[IO.Directory]::CreateDirectory($runtime) | Out-Null
if ($Action -eq 'Plan') {
    [IO.File]::WriteAllText((Join-Path $runtime 'service.plan.json'),($settings | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $runtime 'task.plan.xml'),$xml,[Text.Encoding]::Unicode)
    [pscustomobject]@{ action='Plan: local review files only'; task_name=$taskName; settings=(Join-Path $runtime 'service.plan.json'); task_xml=(Join-Path $runtime 'task.plan.xml'); run_as=$sid; interactive_session=$session; privilege='HighestAvailable'; autostart='this user logon only'; system_changes=$false } | ConvertTo-Json
    exit 0
}
if ($Action -ne 'Install' -or -not $admin) { throw 'Install requires explicit Apply and the same elevated user' }
$task = Existing-Task
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
if ($task) {
    [IO.File]::WriteAllText((Join-Path $runtime "task.before-install-$stamp.xml"),(Export-ScheduledTask -TaskPath '\' -TaskName $taskName),[Text.Encoding]::Unicode)
    Stop-ScheduledTask -TaskPath '\' -TaskName $taskName
}
if (Test-Path -LiteralPath $manifest) { Copy-Item -LiteralPath $manifest -Destination (Join-Path $runtime "service.before-install-$stamp.json") }
# Restrict only this project's runtime directory; no global UAC, task-folder or system ACL changes.
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true,$false)
foreach ($ruleSid in @($sid,'S-1-5-18','S-1-5-32-544')) {
    $rule = New-Object Security.AccessControl.FileSystemAccessRule(([Security.Principal.SecurityIdentifier]::new($ruleSid)),'FullControl','ContainerInherit,ObjectInherit','None','Allow')
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $runtime -AclObject $acl
[IO.File]::WriteAllText($manifest,($settings | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
Register-ScheduledTask -TaskPath '\' -TaskName $taskName -Xml $xml -Force | Out-Null
Start-ScheduledTask -TaskPath '\' -TaskName $taskName
Write-Output "Installed/started $taskName. Only the window executor is elevated; DSH is unchanged."
