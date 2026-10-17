[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$Python,
    [switch]$Register
)
$ErrorActionPreference = 'Stop'
$configPath = (Resolve-Path -LiteralPath $Config).Path
$settings = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($settings.timezone -ne 'Asia/Tokyo') { throw 'timezone must be Asia/Tokyo' }
foreach ($slot in @('morning','evening')) {
    if ($settings.$slot -notmatch '^([01][0-9]|2[0-3]):[0-5][0-9]$') { throw 'Invalid schedule time' }
}
$codeRoot = Split-Path $PSScriptRoot -Parent
if (-not $Python) { $Python = Join-Path $settings.source_root '.venv/Scripts/python.exe' }
$pythonPath = (Resolve-Path -LiteralPath $Python).Path
$plans = @(
    [pscustomobject]@{ Name='J1AI-Champion-Morning'; Slot='morning'; At=$settings.morning },
    [pscustomobject]@{ Name='J1AI-Champion-Evening'; Slot='evening'; At=$settings.evening }
)
foreach ($plan in $plans) {
    $plan | Add-Member NoteProperty Executable $pythonPath
    $plan | Add-Member NoteProperty Arguments ('-B -m scripts.update_champion_dashboard --config "{0}" --slot {1}' -f $configPath,$plan.Slot)
    $plan | Add-Member NoteProperty WorkingDirectory $codeRoot
}
if (-not $Register) {
    $plans | ConvertTo-Json -Depth 3
    Write-Output 'PLAN ONLY. No tasks registered. Explicit approval and -Register are required.'
    return
}
if ($settings.enabled -ne $true) { throw 'Updates are disabled in config; registration refused' }
if ((Get-TimeZone).Id -ne 'Tokyo Standard Time') { throw 'Task registration requires Windows local timezone Tokyo Standard Time' }
# Check both names before registering either; never replace an unrelated task.
foreach ($plan in $plans) {
    if (Get-ScheduledTask -TaskName $plan.Name -ErrorAction SilentlyContinue) {
        throw ('Task already exists; inspect it before changing: ' + $plan.Name)
    }
}
foreach ($plan in $plans) {
    if ($PSCmdlet.ShouldProcess($plan.Name, 'Register daily Champion-only update')) {
        $action = New-ScheduledTaskAction -Execute $plan.Executable -Argument $plan.Arguments -WorkingDirectory $plan.WorkingDirectory
        $trigger = New-ScheduledTaskTrigger -Daily -At $plan.At
        $taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
        $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $plan.Name -Action $action -Trigger $trigger -Settings $taskSettings -Principal $principal
    }
}
