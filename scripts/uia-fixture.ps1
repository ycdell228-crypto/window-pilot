# Project-owned WPF fixture; never activates itself or writes user data.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
$window = [Windows.Window]::new()
$window.Title = 'Window Pilot UIA Fixture'
$window.Width = 720; $window.Height = 680
$window.Left = 100; $window.Top = 100
$window.ShowActivated = $false
$panel = [Windows.Controls.StackPanel]::new()
$panel.Margin = [Windows.Thickness]::new(16)
$window.Content = $panel
function Identify($control, $id, $name) {
    [Windows.Automation.AutomationProperties]::SetAutomationId($control, $id)
    [Windows.Automation.AutomationProperties]::SetName($control, $name)
    $control.Margin = [Windows.Thickness]::new(0, 3, 0, 3)
    [void]$panel.Children.Add($control)
}
$counter = [Windows.Controls.TextBlock]::new(); $counter.Text = 'Invoked: 0'
Identify $counter 'invoke-status' 'Invoked: 0'
$script:invoked = 0
$button = [Windows.Controls.Button]::new(); $button.Content = 'Invoke fixture button'
$button.Add_Click({ $script:invoked++; $counter.Text = 'Invoked: ' + $script:invoked
    [Windows.Automation.AutomationProperties]::SetName($counter, $counter.Text) })
Identify $button 'invoke-button' 'Invoke fixture button'
$disabled = [Windows.Controls.Button]::new(); $disabled.Content = 'Disabled fixture button'; $disabled.IsEnabled = $false
Identify $disabled 'disabled-button' 'Disabled fixture button'
$inputBox = [Windows.Controls.TextBox]::new(); $inputBox.Text = 'initial'
Identify $inputBox 'value-field' 'Value field'
$echo = [Windows.Controls.TextBlock]::new(); $echo.Text = 'Value echo: initial'
Identify $echo 'value-status' 'Value echo: initial'
$inputBox.Add_TextChanged({ $echo.Text = 'Value echo: ' + $inputBox.Text
    [Windows.Automation.AutomationProperties]::SetName($echo, $echo.Text) })
$password = [Windows.Controls.PasswordBox]::new()
Identify $password 'password-field' 'Password field'
$list = [Windows.Controls.ListBox]::new(); $list.Height = 65
foreach ($label in @('Option A', 'Option B')) {
    $item = [Windows.Controls.ListBoxItem]::new(); $item.Content = $label
    [Windows.Automation.AutomationProperties]::SetAutomationId($item, $label.Replace(' ', '-'))
    [void]$list.Items.Add($item)
}
$list.SelectedIndex = 0
Identify $list 'selection-list' 'Selection list'
$expander = [Windows.Controls.Expander]::new(); $expander.Header = 'Expandable section'
$content = [Windows.Controls.TextBlock]::new(); $content.Text = 'Expanded content'
$expander.Content = $content
Identify $expander 'expander' 'Expandable section'
$scroll = [Windows.Controls.ScrollViewer]::new(); $scroll.Height = 140
$scroll.VerticalScrollBarVisibility = 'Visible'; $scroll.HorizontalScrollBarVisibility = 'Disabled'
$scrollPanel = [Windows.Controls.StackPanel]::new()
foreach ($number in 1..20) {
    $line = [Windows.Controls.TextBlock]::new(); $line.Text = "Scrollable row $number"; $line.Height = 30
    [void]$scrollPanel.Children.Add($line)
}
$scroll.Content = $scrollPanel
Identify $scroll 'scroll-view' 'Scrollable area'
$timer = [Windows.Threading.DispatcherTimer]::new()
$timer.Interval = [TimeSpan]::FromMinutes(10)
$timer.Add_Tick({ $window.Close() }); $timer.Start()
$window.Show()
$window.Add_Closed({ $window.Dispatcher.InvokeShutdown() })
[Windows.Threading.Dispatcher]::Run()
