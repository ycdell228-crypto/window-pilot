# Bounded observe/action worker. stdin is one JSON request; stdout one JSON result.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$progressClock = [Diagnostics.Stopwatch]::StartNew()
function Progress($name) {
    [Console]::Error.WriteLine('UIA_STAGE ' + $name + ' ' + $progressClock.ElapsedMilliseconds + ' ' +
        [Threading.Thread]::CurrentThread.ApartmentState)
}
Progress 'script_start'
$stage = 'load_builtin_providers'
$attempted = $false
try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    Add-Type -AssemblyName UIAutomationClientsideProviders
    Progress 'assemblies_loaded'
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class UiaReadDpi {
    [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] public static extern bool IsChild(IntPtr parent, IntPtr child);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hwnd, System.Text.StringBuilder text, int count);
    [StructLayout(LayoutKind.Sequential)] public struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hwnd, out Rect rect);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hwnd, ref Point point);
}
'@
    [void][UiaReadDpi]::SetProcessDpiAwarenessContext([IntPtr](-4))
    Progress 'interop_compiled'
    $stage = 'read_bound_root'
    $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]([long]$request.hwnd))
    if ($null -eq $root) { throw 'UIA_ROOT_UNAVAILABLE' }
    Progress 'root_resolved'
    # FromHandle initializes UIA's proxy registry before explicit built-in provider registration.
    # Registering first can throw NullReferenceException; omitting it yields generic Pane proxies.
    $stage = 'register_builtin_providers'
    [System.Windows.Automation.ClientSettings]::RegisterClientSideProviderAssembly(
        [Reflection.AssemblyName]::new('UIAutomationClientsideProviders, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35'))
    $stage = 'read_bound_root'
    Progress 'proxies_registered'
    $initial = $root.Current
    if ([long]$initial.NativeWindowHandle -ne [long]$request.hwnd -or $initial.ProcessId -ne $request.pid) {
        throw 'UIA_ROOT_IDENTITY_MISMATCH'
    }
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $nodes = [Collections.Generic.List[object]]::new()
    $elements = @{}
    $state = @{ truncated = $false; foreign_process_subtrees_skipped = 0 }
    function LimitedText($value, $limit) {
        $value = [string]$value
        if ($value.Length -gt $limit) { return $value.Substring(0, $limit) }
        return $value
    }
    function Visit($element, $parent, $depth) {
        if ($nodes.Count -ge $request.max_nodes) { $state.truncated = $true; return }
        $current = $element.Current
        # First version excludes foreign-process providers/subtrees, including embedded browsers.
        if ($current.ProcessId -ne $request.pid) {
            $state.foreign_process_subtrees_skipped++
            return
        }
        $handle = [long]$current.NativeWindowHandle
        if ($handle -ne 0 -and $handle -ne [long]$request.hwnd -and
            -not [UiaReadDpi]::IsChild([IntPtr]([long]$request.hwnd), [IntPtr]$handle)) {
            throw 'UIA_ROOT_IDENTITY_MISMATCH: native element is outside bound window'
        }
        $index = $nodes.Count
        $rect = $current.BoundingRectangle
        $bounds = $null
        if (-not $rect.IsEmpty -and -not [double]::IsInfinity($rect.X) -and -not [double]::IsInfinity($rect.Y)) {
            $bounds = @{ x = $rect.X; y = $rect.Y; width = $rect.Width; height = $rect.Height }
        }
        $patterns = @($element.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName })
        $runtimeId = @($element.GetRuntimeId())
        $runtimeKey = $runtimeId -join ','
        if ($elements.ContainsKey($runtimeKey)) { throw 'UIA_AMBIGUOUS_RUNTIME_ID' }
        $elements[$runtimeKey] = $element
        $patternState = @{}
        if ($patterns -contains 'SelectionItemPatternIdentifiers.Pattern') {
            $patternState.selected = $element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Current.IsSelected
        }
        if ($patterns -contains 'ExpandCollapsePatternIdentifiers.Pattern') {
            $patternState.expand_collapse = [string]$element.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Current.ExpandCollapseState
        }
        if ($patterns -contains 'ScrollPatternIdentifiers.Pattern') {
            $scrollState = $element.GetCurrentPattern([System.Windows.Automation.ScrollPattern]::Pattern).Current
            $patternState.horizontal_scroll_percent = $scrollState.HorizontalScrollPercent
            $patternState.vertical_scroll_percent = $scrollState.VerticalScrollPercent
        }
        if ($patterns -contains 'ValuePatternIdentifiers.Pattern' -and -not $current.IsPassword) {
            $patternState.value_read_only = $element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.IsReadOnly
        }
        $name = if ($current.IsPassword) { '[password control: name redacted]' } else { LimitedText $current.Name 256 }
        $hash = [Security.Cryptography.SHA256]::Create()
        try { $nameHash = [Convert]::ToBase64String($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes(
            $(if ($current.IsPassword) { '[redacted]' } else { [string]$current.Name })))) } finally { $hash.Dispose() }
        $nodes.Add(@{
            index = $index; parent_index = $parent; depth = $depth
            runtime_id = $runtimeId; name_sha256 = $nameHash; pattern_state = $patternState
            name = $name; automation_id = (LimitedText $current.AutomationId 128)
            control_type = $current.ControlType.ProgrammaticName
            class_name = (LimitedText $current.ClassName 128)
            process_id = $current.ProcessId; native_window_handle = [long]$current.NativeWindowHandle
            state = @{ enabled = $current.IsEnabled; offscreen = $current.IsOffscreen
                       keyboard_focusable = $current.IsKeyboardFocusable; has_keyboard_focus = $current.HasKeyboardFocus
                       password = $current.IsPassword }
            bounds_screen = $bounds; supported_patterns = $patterns
        })
        $child = $walker.GetFirstChild($element)
        if ($null -ne $child -and $depth -ge $request.max_depth) { $state.truncated = $true; return }
        while ($null -ne $child) {
            if ($nodes.Count -ge $request.max_nodes) { $state.truncated = $true; return }
            Visit $child $index ($depth + 1)
            $child = $walker.GetNextSibling($child)
        }
    }
    Visit $root $null 0
    Progress 'tree_read'
    $final = $root.Current
    if ([long]$final.NativeWindowHandle -ne [long]$request.hwnd -or $final.ProcessId -ne $request.pid) {
        throw 'UIA_ROOT_IDENTITY_MISMATCH'
    }
    $status = if ($nodes.Count -eq 0 -or ($nodes.Count -eq 1 -and -not $state.truncated -and
                  $state.foreign_process_subtrees_skipped -eq 0)) { 'empty' } else { 'ok' }
    $result = @{ status = $status; nodes = @($nodes.ToArray()); truncated = $state.truncated
                 foreign_process_subtrees_skipped = $state.foreign_process_subtrees_skipped }
    if ($request.mode -eq 'action') {
        $stage = 'validate_observation'
        function CheckRoot {
            $identity = $request.identity
            [uint32]$actualPid = 0
            $tid = [UiaReadDpi]::GetWindowThreadProcessId([IntPtr]([long]$request.hwnd), [ref]$actualPid)
            $process = [Diagnostics.Process]::GetProcessById([int]$actualPid)
            try {
                $class = [Text.StringBuilder]::new(256)
                [void][UiaReadDpi]::GetClassName([IntPtr]([long]$request.hwnd), $class, 256)
                if ($actualPid -ne $identity.pid -or $tid -ne $identity.tid -or
                    $process.StartTime.ToFileTimeUtc() -ne [long]$identity.created -or
                    -not [string]::Equals($process.MainModule.FileName, $identity.exe, [StringComparison]::OrdinalIgnoreCase) -or
                    $class.ToString() -cne $identity.klass) { throw 'UIA_WINDOW_IDENTITY_CHANGED' }
            } finally { $process.Dispose() }
            $rect = [UiaReadDpi+Rect]::new(); $point = [UiaReadDpi+Point]::new()
            if (-not [UiaReadDpi]::GetClientRect([IntPtr]([long]$request.hwnd), [ref]$rect) -or
                -not [UiaReadDpi]::ClientToScreen([IntPtr]([long]$request.hwnd), [ref]$point)) { throw 'UIA_WINDOW_GEOMETRY_CHANGED' }
            $geometry = $request.geometry
            if ($point.X -ne $geometry.x -or $point.Y -ne $geometry.y -or
                ($rect.Right - $rect.Left) -ne $geometry.width -or ($rect.Bottom - $rect.Top) -ne $geometry.height) { throw 'UIA_WINDOW_GEOMETRY_CHANGED' }
        }
        function Fingerprint($node) {
            $bounds = $node.bounds_screen
            [ordered]@{ runtime_id = @($node.runtime_id); parent = $node.parent_index; depth = $node.depth
                pid = $node.process_id; hwnd = $node.native_window_handle; type = $node.control_type
                class = $node.class_name; automation_id = $node.automation_id; name_hash = $node.name_sha256
                enabled = $node.state.enabled; password = $node.state.password; offscreen = $node.state.offscreen
                rect = @($bounds.x, $bounds.y, $bounds.width, $bounds.height)
                patterns = @($node.supported_patterns | Sort-Object)
                selected = $node.pattern_state.selected; expanded = $node.pattern_state.expand_collapse
                h_scroll = $node.pattern_state.horizontal_scroll_percent; v_scroll = $node.pattern_state.vertical_scroll_percent
                read_only = $node.pattern_state.value_read_only } | ConvertTo-Json -Depth 8 -Compress
        }
        CheckRoot
        if ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 -ge $request.deadline_epoch) { throw 'UIA_STALE_OBSERVATION' }
        $expected = @($request.expected_nodes)
        if ($expected.Count -ne $nodes.Count) { throw 'UIA_OBSERVATION_CHANGED' }
        for ($i = 0; $i -lt $nodes.Count; $i++) {
            if ((Fingerprint $expected[$i]) -cne (Fingerprint $nodes[$i])) { throw 'UIA_OBSERVATION_CHANGED' }
        }
        $key = @($request.runtime_id) -join ','
        if (-not $elements.ContainsKey($key)) { throw 'UIA_CONTROL_NOT_IN_OBSERVATION' }
        $element = $elements[$key]
        $selected = @($nodes | Where-Object { ($_.runtime_id -join ',') -eq $key })
        if ($selected.Count -ne 1) { throw 'UIA_AMBIGUOUS_RUNTIME_ID' }
        $selected = $selected[0]
        if (-not $selected.state.enabled) { throw 'UIA_CONTROL_DISABLED' }
        if ($selected.state.password) { throw 'UIA_PASSWORD_CONTROL_REFUSED' }
        if ($selected.state.offscreen -or $null -eq $selected.bounds_screen -or
            $selected.bounds_screen.width -le 0 -or $selected.bounds_screen.height -le 0) { throw 'UIA_CONTROL_NOT_VISIBLE' }
        $mapping = @{ invoke = 'Invoke'; set_value = 'Value'; select = 'SelectionItem'
                      expand = 'ExpandCollapse'; collapse = 'ExpandCollapse'; scroll = 'Scroll' }
        $patternName = $mapping[[string]$request.action]
        if (-not $patternName -or $selected.supported_patterns -notcontains ($patternName + 'PatternIdentifiers.Pattern')) { throw 'UIA_PATTERN_UNSUPPORTED' }
        if ($request.action -eq 'set_value' -and $selected.pattern_state.value_read_only) { throw 'UIA_VALUE_READ_ONLY' }
        $patternType = [type]('System.Windows.Automation.' + $patternName + 'Pattern')
        $pattern = $element.GetCurrentPattern($patternType::Pattern)
        # Final same-element and root recheck immediately before the single provider call.
        CheckRoot
        if ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 -ge $request.deadline_epoch) { throw 'UIA_STALE_OBSERVATION' }
        if (-not $element.Current.IsEnabled -or $element.Current.IsPassword -or $element.Current.ProcessId -ne $request.pid -or
            (($element.GetRuntimeId() -join ',') -cne $key)) { throw 'UIA_CONTROL_CHANGED' }
        $latestBounds = $element.Current.BoundingRectangle
        if ($latestBounds.X -ne $selected.bounds_screen.x -or $latestBounds.Y -ne $selected.bounds_screen.y -or
            $latestBounds.Width -ne $selected.bounds_screen.width -or $latestBounds.Height -ne $selected.bounds_screen.height) { throw 'UIA_CONTROL_GEOMETRY_CHANGED' }
        $ancestor = $element; $ancestorNode = $selected
        while ($true) {
            if ($null -eq $ancestor -or $ancestor.Current.ProcessId -ne $request.pid -or
                (($ancestor.GetRuntimeId() -join ',') -cne ($ancestorNode.runtime_id -join ','))) { throw 'UIA_CONTROL_ANCESTRY_CHANGED' }
            if ($null -eq $ancestorNode.parent_index) { break }
            $ancestor = $walker.GetParent($ancestor)
            $ancestorNode = $nodes[[int]$ancestorNode.parent_index]
        }
        $stage = 'dispatch'
        $attempted = $true
        switch ([string]$request.action) {
            'invoke' { $pattern.Invoke() }
            'set_value' { $pattern.SetValue([string]$request.value) }
            'select' { $pattern.Select() }
            'expand' { $pattern.Expand() }
            'collapse' { $pattern.Collapse() }
            'scroll' { $pattern.Scroll([System.Windows.Automation.ScrollAmount]::$($request.horizontal),
                                      [System.Windows.Automation.ScrollAmount]::$($request.vertical)) }
        }
        $result = @{ status = 'provider_returned'; action_attempted = $true; effect = 'unverified' }
    }
} catch {
    # Discard partial trees after any provider error. Never return them as a complete observation.
    $message = $_.Exception.GetBaseException().Message
    $status = if ($message -like '*UIA_ROOT_IDENTITY_MISMATCH*') { 'identity_changed' }
              elseif ($_.Exception.GetBaseException() -is [System.NotSupportedException]) { 'unsupported' }
              else { 'unavailable' }
    if ($request.mode -eq 'action') {
        # Provider messages may echo a SetValue input; never return/log them.
        $code = ($message -split ':', 2)[0]
        $allowedCodes = @('UIA_ROOT_UNAVAILABLE', 'UIA_ROOT_IDENTITY_MISMATCH', 'UIA_AMBIGUOUS_RUNTIME_ID',
            'UIA_WINDOW_IDENTITY_CHANGED', 'UIA_WINDOW_GEOMETRY_CHANGED', 'UIA_STALE_OBSERVATION',
            'UIA_OBSERVATION_CHANGED', 'UIA_CONTROL_NOT_IN_OBSERVATION', 'UIA_CONTROL_DISABLED',
            'UIA_PASSWORD_CONTROL_REFUSED', 'UIA_CONTROL_NOT_VISIBLE', 'UIA_PATTERN_UNSUPPORTED',
            'UIA_VALUE_READ_ONLY', 'UIA_CONTROL_CHANGED', 'UIA_CONTROL_GEOMETRY_CHANGED', 'UIA_CONTROL_ANCESTRY_CHANGED')
        $known = if ($allowedCodes -contains $code) { $code } else { 'UIA_PROVIDER_ERROR' }
        $result = @{ status = $(if ($attempted) { 'unknown' } else { 'rejected' }); action_attempted = $attempted
                     effect = $(if ($attempted) { 'unverified' } else { 'not_sent' }); error_stage = $stage
                     error = $known; hresult = $_.Exception.GetBaseException().HResult }
    } else {
        $result = @{ status = $status; nodes = @(); error_stage = $stage
                     error = $message.Substring(0, [Math]::Min(400, $message.Length)) }
    }
}
[Console]::Out.WriteLine(($result | ConvertTo-Json -Depth 18 -Compress))
