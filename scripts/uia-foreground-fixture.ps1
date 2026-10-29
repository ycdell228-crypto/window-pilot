# Project-owned foreground input fixture; no user data or self-activation.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
$window=[Windows.Window]::new(); $window.Title='Window Pilot Foreground Fixture'
# This explicitly selected foreground acceptance fixture stays visible above other apps; it still does not activate itself.
$window.Topmost=$true
$window.Width=640; $window.Height=460; $window.Left=140; $window.Top=120; $window.ShowActivated=$false
$panel=[Windows.Controls.StackPanel]::new(); $panel.Margin=[Windows.Thickness]::new(20); $window.Content=$panel
function Add($item,$id,$name) {
    [Windows.Automation.AutomationProperties]::SetAutomationId($item,$id)
    [Windows.Automation.AutomationProperties]::SetName($item,$name)
    $item.Margin=[Windows.Thickness]::new(0,6,0,6); [void]$panel.Children.Add($item)
}
$inputBox=[Windows.Controls.TextBox]::new(); $inputBox.Text='initial'; $inputBox.Height=32
Add $inputBox 'foreground-value' 'Foreground value'
$echo=[Windows.Controls.TextBlock]::new(); $echo.Text='Echo: initial'; Add $echo 'foreground-echo' 'Echo: initial'
$inputBox.Add_TextChanged({$echo.Text='Echo: '+$inputBox.Text; [Windows.Automation.AutomationProperties]::SetName($echo,$echo.Text)})
$password=[Windows.Controls.PasswordBox]::new(); $password.Height=30; Add $password 'foreground-password' 'Protected fixture field'
$canvas=[Windows.Controls.Canvas]::new(); $canvas.Height=100; $canvas.Background=[Windows.Media.Brushes]::LightGray
Add $canvas 'drag-canvas' 'Drag canvas'
$thumb=[Windows.Controls.Primitives.Thumb]::new(); $thumb.Width=40; $thumb.Height=40
$thumb.Background=[Windows.Media.Brushes]::Magenta
[Windows.Automation.AutomationProperties]::SetAutomationId($thumb,'drag-thumb')
[Windows.Automation.AutomationProperties]::SetName($thumb,'Draggable thumb')
[Windows.Controls.Canvas]::SetLeft($thumb,40); [Windows.Controls.Canvas]::SetTop($thumb,24); [void]$canvas.Children.Add($thumb)
$dragEcho=[Windows.Controls.TextBlock]::new(); $dragEcho.Text='Drag x: 40'; Add $dragEcho 'drag-echo' 'Drag x: 40'
$thumb.Add_DragDelta({param($sender,$e)
    $x=[Math]::Max(0,[Math]::Min(500,[Windows.Controls.Canvas]::GetLeft($thumb)+$e.HorizontalChange))
    [Windows.Controls.Canvas]::SetLeft($thumb,$x); $dragEcho.Text='Drag x: '+[Math]::Round($x)
    [Windows.Automation.AutomationProperties]::SetName($dragEcho,$dragEcho.Text)
})
$other=[Windows.Controls.Button]::new(); $other.Content='Other focus'; Add $other 'other-focus' 'Other focus'
# Only this self-owned fixture can arm a real focus migration during DragStarted.
$script:focusLossArmed=$false
$arm=[Windows.Controls.Button]::new(); $arm.Content='Arm protected focus migration'
Add $arm 'arm-focus-loss' 'Arm protected focus migration'
$arm.Add_Click({$script:focusLossArmed=$true})
$thumb.Add_DragStarted({ if ($script:focusLossArmed) { $script:focusLossArmed=$false; [void]$password.Focus() } })
$timer=[Windows.Threading.DispatcherTimer]::new(); $timer.Interval=[TimeSpan]::FromMinutes(10)
$timer.Add_Tick({$window.Close()}); $timer.Start()
$window.Show(); $window.Add_Closed({$window.Dispatcher.InvokeShutdown()}); [Windows.Threading.Dispatcher]::Run()
