param(
    [string]$TaskName = "StockAgentDailyIngestion",
    [string]$Time = "18:30"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\stockagent"
$ScriptPath = Join-Path $ProjectRoot "scripts\windows\run_daily_ingestion.ps1"

if (!(Test-Path $ScriptPath)) {
    throw "Script not found: $ScriptPath"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`""
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force
