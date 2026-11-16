# panel-standin.ps1 -- a throwaway stand-in for the usage panel, so the pet can be tested
# for z-order and corner placement WITHOUT touching the real widget.
# Same colour as the frozen contract (#1B1F27), Topmost = true (the widget sets Topmost),
# frameless. Pure ASCII.
#
#   .\panel-standin.ps1 -X 1150 -Y 520 -W 400 -H 340 -Seconds 60
param(
  [int]$X = 1150, [int]$Y = 520, [int]$W = 400, [int]$H = 340,
  [int]$Seconds = 60,
  [switch]$ReassertTopmost
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = 'DSH usage (stand-in)'
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$form.StartPosition = 'Manual'
$form.Location = New-Object System.Drawing.Point $X, $Y
$form.Size = New-Object System.Drawing.Size $W, $H
$form.BackColor = [System.Drawing.Color]::FromArgb(27, 31, 39)   # #1B1F27
$form.TopMost = $true
$form.ShowInTaskbar = $false
$form.Add_Paint({
  param($s, $e)
  $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(60, 255, 255, 255)), 1
  $e.Graphics.DrawRectangle($pen, 0, 0, $W - 1, $H - 1)
  $font = New-Object System.Drawing.Font 'Consolas', 9
  $br = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(200, 220, 230))
  $e.Graphics.DrawString("PANEL STAND-IN (not the real widget)`n$W x $H at $X,$Y", $font, $br, 10, 10)
})
$form.Show()
[void][System.Windows.Forms.Application]::DoEvents()
Write-Host "[panel-standin] hwnd=0x$($form.Handle.ToString('x')) rect=$X,$Y $W x $H topmost=$($form.TopMost)"

# Simulate the real widget: it re-asserts Topmost on a timer, which can push a topmost pet
# behind it. That is exactly the integration risk we want to measure.
if ($ReassertTopmost) {
  $t = New-Object System.Windows.Forms.Timer
  $t.Interval = 1500
  $t.Add_Tick({ $form.TopMost = $false; $form.TopMost = $true })
  $t.Start()
}

$deadline = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $deadline) {
  [System.Windows.Forms.Application]::DoEvents()
  Start-Sleep -Milliseconds 60
}
$form.Close()
Write-Host '[panel-standin] closed'
