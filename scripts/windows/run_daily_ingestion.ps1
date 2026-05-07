$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\stockagent"
$PythonExe = Join-Path $ProjectRoot ".miniconda3\envs\stock-trading-analysis\python.exe"
$OutputDir = Join-Path $ProjectRoot "output\scheduler"

if (!(Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogPath = Join-Path $OutputDir "daily-ingestion-$Timestamp.log"
$StdoutPath = Join-Path $OutputDir "daily-ingestion-$Timestamp.stdout.log"
$StderrPath = Join-Path $OutputDir "daily-ingestion-$Timestamp.stderr.log"

"[$(Get-Date -Format s)] Starting daily ingestion run" | Out-File -LiteralPath $LogPath -Encoding UTF8

try {
    $process = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList `
            (Join-Path $ProjectRoot "stock_trading\manage.py"),
            "run_daily_ingestion_now",
            "--json" `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -PassThru `
        -Wait

    if (Test-Path $StdoutPath) {
        Get-Content -LiteralPath $StdoutPath | Out-File -LiteralPath $LogPath -Append -Encoding UTF8
    }
    if (Test-Path $StderrPath) {
        Get-Content -LiteralPath $StderrPath | Out-File -LiteralPath $LogPath -Append -Encoding UTF8
    }

    if ($process.ExitCode -ne 0) {
        "[$(Get-Date -Format s)] Daily ingestion failed with exit code $($process.ExitCode)" | Out-File -LiteralPath $LogPath -Append -Encoding UTF8
        exit $process.ExitCode
    }

    "[$(Get-Date -Format s)] Daily ingestion finished successfully" | Out-File -LiteralPath $LogPath -Append -Encoding UTF8
}
catch {
    "[$(Get-Date -Format s)] Daily ingestion failed: $($_.Exception.Message)" | Out-File -LiteralPath $LogPath -Append -Encoding UTF8
    throw
}
