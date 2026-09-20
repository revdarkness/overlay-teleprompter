# Creates Desktop and Start Menu shortcuts for the Overlay Teleprompter,
# and assigns Ctrl+Alt+P as the launch hotkey.

$ErrorActionPreference = 'Stop'

$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $here 'teleprompter.pyw'

if (-not (Test-Path $script)) {
    Write-Host "Could not find teleprompter.pyw next to this installer." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# ---------------------------------------------------------------- find python
$pythonw = $null
$cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
if ($cmd) { $pythonw = $cmd.Source }

if (-not $pythonw) {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\pythonw.exe",
        "$env:PROGRAMFILES\Python3*\pythonw.exe",
        "C:\Python3*\pythonw.exe",
        "$env:WINDIR\pyw.exe"
    )
    foreach ($pattern in $candidates) {
        $hit = Get-Item $pattern -ErrorAction SilentlyContinue |
               Sort-Object FullName -Descending |
               Select-Object -First 1
        if ($hit) { $pythonw = $hit.FullName; break }
    }
}

if (-not $pythonw) {
    Write-Host ""
    Write-Host "Python was not found on this machine." -ForegroundColor Yellow
    Write-Host "Install it from https://www.python.org/downloads/ and tick"
    Write-Host "'Add python.exe to PATH' during setup, then run this installer again."
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Using: $pythonw"

# ------------------------------------------------------------ build shortcuts
$shell   = New-Object -ComObject WScript.Shell
$quote   = [char]34
$targets = @(
    [Environment]::GetFolderPath('Desktop'),
    (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs')
)

foreach ($folder in $targets) {
    if (-not (Test-Path $folder)) { continue }
    $path = Join-Path $folder 'Teleprompter.lnk'

    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath       = $pythonw
    $lnk.Arguments        = $quote + $script + $quote
    $lnk.WorkingDirectory = $here
    $lnk.IconLocation     = "$env:SystemRoot\System32\shell32.dll,177"
    $lnk.Description      = 'Overlay Teleprompter'
    $lnk.WindowStyle      = 1
    $lnk.Hotkey           = 'CTRL+ALT+P'
    $lnk.Save()

    Write-Host "Created: $path" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. Launch it three ways:" -ForegroundColor Cyan
Write-Host "  1. Double-click Teleprompter on your Desktop"
Write-Host "  2. Press Ctrl+Alt+P from anywhere"
Write-Host "  3. Type 'Teleprompter' into the Start menu"
Write-Host ""
Write-Host "Tip: right-click the Desktop shortcut and Pin to taskbar for one-click access."
Write-Host ""
Read-Host "Press Enter to close"
