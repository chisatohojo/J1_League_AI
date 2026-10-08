# Explicit opt-in installer only. No administrator rights or external modules.
[CmdletBinding()]
param(
    [string]$Data
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-DashboardShortcutOwnership {
    param($Shortcut, [string]$Marker, [string]$Pythonw, [string]$Root, [string]$Launcher)
    $prefix = '"' + $Launcher + '"'
    return ($Shortcut.Description -ceq $Marker -and
            $Shortcut.TargetPath -ieq $Pythonw -and
            $Shortcut.WorkingDirectory -ieq $Root -and
            ($Shortcut.Arguments -ceq $prefix -or
             ($Shortcut.Arguments.StartsWith($prefix, [StringComparison]::Ordinal) -and
              $Shortcut.Arguments.Substring($prefix.Length) -cmatch '^ --data "[^"\r\n]+"$')))
}

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonw = Join-Path $repositoryRoot '.venv\Scripts\pythonw.exe'
$serverPython = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$launcher = Join-Path $repositoryRoot 'scripts\launch_dashboard.py'
foreach ($requiredFile in @($pythonw, $serverPython, $launcher)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw 'Missing dashboard launcher or venv python/pythonw. Set up the repository first.'
    }
}

# SpecialFolder honors redirected Desktop paths, including OneDrive.
$desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
if (-not $desktop -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
    throw 'The Windows Desktop directory is unavailable.'
}
$shortcutPath = Join-Path $desktop 'J1 AI Predict.lnk'
$ownerMarker = 'J1AI Windows dashboard launcher v1 | ' + $repositoryRoot
$arguments = '"' + $launcher + '"'
if ($Data) {
    $dataPath = (Resolve-Path -LiteralPath $Data).Path
    if ([IO.Path]::GetExtension($dataPath) -ine '.json' -or
        -not (Test-Path -LiteralPath $dataPath -PathType Leaf)) {
        throw '-Data must be an explicit existing prepared JSON file.'
    }
    # Valid Windows filenames contain no double quotes. No shell interpolation.
    $arguments += ' --data "' + $dataPath + '"'
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $null
try {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    if (Test-Path -LiteralPath $shortcutPath) {
        if (-not (Test-DashboardShortcutOwnership $shortcut $ownerMarker $pythonw $repositoryRoot $launcher)) {
            throw 'STOP: An unrelated J1 AI Predict shortcut already exists. It was not overwritten.'
        }
    }
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $repositoryRoot
    $shortcut.Description = $ownerMarker
    $shortcut.WindowStyle = 1 # pythonw has no console; browser app window is visible.
    # Valid built-in Windows icon; custom J1AI artwork remains a future task.
    $standardIcon = Join-Path ([Environment]::SystemDirectory) 'shell32.dll'
    if (-not (Test-Path -LiteralPath $standardIcon -PathType Leaf)) {
        throw 'Windows standard icon library is unavailable.'
    }
    $shortcut.IconLocation = $standardIcon + ',0'
    $shortcut.Save()
    Write-Output 'Installed J1 AI Predict desktop shortcut. No server or browser was started.'
}
finally {
    if ($null -ne $shortcut) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shortcut) }
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
}
