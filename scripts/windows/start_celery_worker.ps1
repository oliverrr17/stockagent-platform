$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\stockagent"
$PythonExe = Join-Path $ProjectRoot ".miniconda3\envs\stock-trading-analysis\python.exe"
$AppRoot = Join-Path $ProjectRoot "stock_trading"

if (!(Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

if (!(Test-Path $AppRoot)) {
    throw "App root not found: $AppRoot"
}

$env:PYTHONPATH = "$ProjectRoot;$AppRoot"
Set-Location $ProjectRoot
& $PythonExe -m celery -A stock_trading.config worker --loglevel=info --pool=solo
