# Spanish Dubbing Studio - local launcher
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Port 8766 -NoBrowser
[CmdletBinding()]
param(
    [int]$Port = 8765,
    [switch]$NoBrowser,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "ERROR: $Text" -ForegroundColor Red
    Write-Host ""
    exit 1
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Fail "The virtual environment is missing. Run scripts\setup.ps1 first."
}
if (-not (Test-Path (Join-Path $Root "frontend\dist\index.html"))) {
    Fail "The web interface is not built. Run scripts\setup.ps1 (or npm run build in frontend\)."
}
if (-not (Test-Path (Join-Path $Root "tools\ffmpeg\bin\ffmpeg.exe"))) {
    Write-Host "WARNING: FFmpeg was not found in tools\ffmpeg. Setup or set VTS_FFMPEG." -ForegroundColor Yellow
}
if (-not (Test-Path (Join-Path $Root "tools\piper\piper.exe"))) {
    Write-Host "WARNING: Piper was not found in tools\piper. Windows SAPI will be used as fallback." -ForegroundColor Yellow
}

$env:PYTHONIOENCODING = "utf-8"
$env:VTS_HOST = "127.0.0.1"
$env:VTS_PORT = "$Port"
$Url = "http://127.0.0.1:$Port"

Write-Host ""
Write-Host "  Spanish Dubbing Studio" -ForegroundColor White
Write-Host "  Local dubbing to Spanish - everything runs on this PC" -ForegroundColor DarkGray
Write-Host "  $Url" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop the server." -ForegroundColor DarkGray
Write-Host ""

if (-not $NoBrowser) {
    # Wait for the API, then open the default browser. Kept in a separate
    # process so closing the server never leaves a job behind.
    $command = "Start-Sleep -Seconds 2; try { Invoke-WebRequest -Uri '$Url/api/health' -UseBasicParsing -TimeoutSec 2 | Out-Null } catch { }; Start-Process '$Url'"
    Start-Process -FilePath "powershell" -WindowStyle Hidden `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) | Out-Null
}

$arguments = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) { $arguments += "--reload" }

Push-Location (Join-Path $Root "backend")
try {
    & $VenvPython @arguments
}
finally {
    Pop-Location
    Write-Host ""
    Write-Host "Server stopped." -ForegroundColor DarkGray
}
