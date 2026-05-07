param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$FrontendDir = Join-Path $ProjectRoot "frontend"
$BackendPython = Join-Path $ProjectRoot ".miniconda3\envs\stock-trading-analysis\python.exe"
$ManagePy = Join-Path $ProjectRoot "stock_trading\manage.py"
$BackendUrl = "http://127.0.0.1:8000/api/status/operations/"
$FrontendUrl = "http://127.0.0.1:5173/"
$BackendLogDir = Join-Path $ProjectRoot "output\backend"
$FrontendLogDir = Join-Path $ProjectRoot "output\frontend"
$BackendStdout = Join-Path $BackendLogDir "runserver.stdout.log"
$BackendStderr = Join-Path $BackendLogDir "runserver.stderr.log"
$FrontendStdout = Join-Path $FrontendLogDir "vite.stdout.log"
$FrontendStderr = Join-Path $FrontendLogDir "vite.stderr.log"
$ViteBin = Join-Path $FrontendDir "node_modules\vite\bin\vite.js"

function Get-NpmCommand {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) {
        $npm = Get-Command npm -ErrorAction SilentlyContinue
    }
    if (-not $npm) {
        throw "npm was not found on PATH."
    }
    return $npm.Source
}

function Get-BackendProcesses {
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" `
            -and $_.CommandLine -like "*$ManagePy*" `
            -and $_.CommandLine -like "*runserver*"
    }
}

function Get-FrontendProcesses {
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "node.exe" -and $_.CommandLine -like "*$FrontendDir*"
    }
}

function Get-EsbuildProcesses {
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "esbuild.exe" -and $_.ExecutablePath -like "$FrontendDir*"
    }
}

function Stop-RepoProcesses {
    foreach ($process in @(Get-BackendProcesses) + @(Get-FrontendProcesses) + @(Get-EsbuildProcesses)) {
        if ($process) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-HttpStatusCode {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        return [int]$response.StatusCode
    }
    catch {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        return $null
    }
}

function Wait-ForHttpStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [int[]]$AcceptStatusCodes,
        [int]$Attempts = 30,
        [int]$DelaySeconds = 1
    )

    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        $statusCode = Get-HttpStatusCode -Url $Url
        if ($null -ne $statusCode -and $AcceptStatusCodes -contains $statusCode) {
            return $statusCode
        }
        Start-Sleep -Seconds $DelaySeconds
    }

    throw "Service at $Url did not become ready. Expected one of: $($AcceptStatusCodes -join ', ')."
}

function Ensure-FrontendDependencies {
    param(
        [Parameter(Mandatory = $true)]
        [string]$NpmCommand
    )

    if (Test-Path $ViteBin) {
        return
    }

    Write-Output "Installing frontend dependencies with npm ci..."
    Push-Location $FrontendDir
    try {
        & $NpmCommand ci
    }
    finally {
        Pop-Location
    }
}

if (!(Test-Path $BackendPython)) {
    throw "Backend Python executable not found: $BackendPython"
}

$NpmCommand = Get-NpmCommand
New-Item -ItemType Directory -Force -Path $BackendLogDir | Out-Null
New-Item -ItemType Directory -Force -Path $FrontendLogDir | Out-Null

if ($Restart) {
    Stop-RepoProcesses
    Start-Sleep -Seconds 1
}

$backendProcess = $null
$backendProcesses = @(Get-BackendProcesses)
$backendStatus = $null

if ($backendProcesses.Count -gt 0) {
    $backendStatus = Get-HttpStatusCode -Url $BackendUrl
    if ($backendStatus -notin 200, 401, 403) {
        Stop-RepoProcesses
        Start-Sleep -Seconds 1
        $backendProcesses = @()
    }
}

if ($backendProcesses.Count -eq 0) {
    $backendProcess = Start-Process `
        -FilePath $BackendPython `
        -ArgumentList $ManagePy, "runserver", "127.0.0.1:8000" `
        -WorkingDirectory $ProjectRoot `
        -PassThru `
        -RedirectStandardOutput $BackendStdout `
        -RedirectStandardError $BackendStderr
}

$backendStatus = Wait-ForHttpStatus -Url $BackendUrl -AcceptStatusCodes @(200, 401, 403)
$backendPid = if ($backendProcess) { $backendProcess.Id } else { (@(Get-BackendProcesses) | Select-Object -First 1).ProcessId }

$frontendProcess = $null
$frontendProcesses = @(Get-FrontendProcesses)
$frontendStatus = $null

if ($frontendProcesses.Count -gt 0) {
    $frontendStatus = Get-HttpStatusCode -Url $FrontendUrl
    if ($frontendStatus -ne 200) {
        foreach ($process in @($frontendProcesses) + @(Get-EsbuildProcesses)) {
            if ($process) {
                Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Seconds 1
        $frontendProcesses = @()
    }
}

if ($frontendProcesses.Count -eq 0) {
    Ensure-FrontendDependencies -NpmCommand $NpmCommand
    $frontendProcess = Start-Process `
        -FilePath $NpmCommand `
        -ArgumentList "run", "dev", "--", "--host", "127.0.0.1" `
        -WorkingDirectory $FrontendDir `
        -PassThru `
        -RedirectStandardOutput $FrontendStdout `
        -RedirectStandardError $FrontendStderr
}

$frontendStatus = Wait-ForHttpStatus -Url $FrontendUrl -AcceptStatusCodes @(200)
$frontendPid = if ($frontendProcess) { $frontendProcess.Id } else { (@(Get-FrontendProcesses) | Select-Object -First 1).ProcessId }

Write-Output "Backend:  http://127.0.0.1:8000/ (pid=$backendPid, status=$backendStatus)"
Write-Output "Frontend: http://127.0.0.1:5173/ (pid=$frontendPid, status=$frontendStatus)"
Write-Output "Backend logs:  $BackendStdout | $BackendStderr"
Write-Output "Frontend logs: $FrontendStdout | $FrontendStderr"
Write-Output "Use -Restart to stop and relaunch repo-local backend/frontend processes."
