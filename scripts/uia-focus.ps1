# Exact-window focus/point safety probe. Never reads names, values or text.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$stage = 'startup'
function Stage($value) {
    $script:stage=$value
    [Console]::Error.WriteLine('FOREGROUND_STAGE '+$value+' '+[Threading.Thread]::CurrentThread.ApartmentState)
}
try {
Stage 'assemblies_load'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName UIAutomationClientsideProviders
Add-Type -AssemblyName WindowsBase
Stage 'dpi_init'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ForegroundProbeDpi {
    [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
}
'@
if (-not [ForegroundProbeDpi]::SetProcessDpiAwarenessContext([IntPtr](-4))) { throw 'dpi' }
$providersRegistered=$false
Stage 'request_wait'
while ($null -ne ($line = [Console]::ReadLine())) {
    try {
        Stage 'request_json'
        $q = $line | ConvertFrom-Json
        Stage 'root_resolve'
        $root = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]([long]$q.hwnd))
        if ($null -eq $root) { throw 'root' }
        Stage 'providers_register'
        if (-not $providersRegistered) {
          [Windows.Automation.ClientSettings]::RegisterClientSideProviderAssembly(
            [Reflection.AssemblyName]::new('UIAutomationClientsideProviders, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35'))
          $providersRegistered=$true
        }
        Stage 'root_identity'
        $r=$root.Current
        if ($r.ProcessId -ne $q.pid -or [long]$r.NativeWindowHandle -ne [long]$q.hwnd) { throw 'root_identity' }
        if ($q.mode -eq 'point') {
            Stage 'point_resolve'
            $element = [Windows.Automation.AutomationElement]::FromPoint([Windows.Point]::new($q.x,$q.y))
        } elseif ($q.mode -eq 'focus') {
            Stage 'focus_resolve'
            $element = [Windows.Automation.AutomationElement]::FocusedElement
        } else { throw 'mode' }
        Stage 'element_safety'
        if ($null -eq $element) { throw 'unavailable' }
        $current = $element.Current
        if ($current.ProcessId -ne $q.pid -or -not $current.IsEnabled -or $current.IsPassword) { throw 'protected' }
        Stage 'runtime_identity'
        $key = $element.GetRuntimeId() -join ','
        $rootKey = $root.GetRuntimeId() -join ','
        Stage 'ancestor_chain'
        $cursor = $element; $inside = $false
        for ($i=0; $i -lt 64 -and $null -ne $cursor; $i++) {
            if ($cursor.Current.IsPassword -or $cursor.Current.ProcessId -ne $q.pid) { throw 'protected' }
            if (($cursor.GetRuntimeId() -join ',') -eq $rootKey) { $inside = $true; break }
            $cursor = [Windows.Automation.TreeWalker]::RawViewWalker.GetParent($cursor)
        }
        if (-not $inside) { throw 'outside' }
        Stage 'response_write'
        [Console]::WriteLine((@{ok=$true; fingerprint=$key; stage=$stage; apartment=[string][Threading.Thread]::CurrentThread.ApartmentState} | ConvertTo-Json -Compress))
    } catch {
        # Provider exceptions may contain sensitive data. Never return them.
        [Console]::WriteLine((@{ok=$false; stage=$stage; apartment=[string][Threading.Thread]::CurrentThread.ApartmentState} | ConvertTo-Json -Compress))
    }
    Stage 'request_wait'
}
} catch {
    [Console]::WriteLine((@{ok=$false; stage=$stage; apartment=[string][Threading.Thread]::CurrentThread.ApartmentState} | ConvertTo-Json -Compress))
}
