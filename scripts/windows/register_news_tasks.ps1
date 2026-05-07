param(
    [string]$CrawlTaskName = "StockAgentNewsCrawl",
    [string]$DigestTaskName = "StockAgentNewsDigest",
    [string[]]$CrawlTimes = @("08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00", "21:00", "22:00"),
    [string]$DigestTime = "18:35"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\stockagent"
$CrawlScriptPath = Join-Path $ProjectRoot "scripts\windows\run_news_crawl.ps1"
$DigestScriptPath = Join-Path $ProjectRoot "scripts\windows\run_news_digest.ps1"

if (!(Test-Path $CrawlScriptPath)) {
    throw "Script not found: $CrawlScriptPath"
}
if (!(Test-Path $DigestScriptPath)) {
    throw "Script not found: $DigestScriptPath"
}

$crawlAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$CrawlScriptPath`""
$digestAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$DigestScriptPath`""

$crawlTriggers = @()
foreach ($Time in $CrawlTimes) {
    $crawlTriggers += New-ScheduledTaskTrigger -Daily -At $Time
}
$digestTrigger = New-ScheduledTaskTrigger -Daily -At $DigestTime

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName $CrawlTaskName -Action $crawlAction -Trigger $crawlTriggers -Principal $principal -Settings $settings -Force
Register-ScheduledTask -TaskName $DigestTaskName -Action $digestAction -Trigger $digestTrigger -Principal $principal -Settings $settings -Force
