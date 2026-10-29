# Spanish Dubbing Studio - one-command Windows setup
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
#
# Installs Python dependencies in .venv, downloads FFmpeg + Piper, builds the
# web interface and (unless -SkipModels) downloads the minimal model set.
[CmdletBinding()]
param(
    [switch]$SkipModels,
    [switch]$SkipBinaries,
    [switch]$SkipFrontend,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) {
    Write-Host "    OK  $Text" -ForegroundColor Green
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "ERROR: $Text" -ForegroundColor Red
    exit 1
}

function Download-File([string]$Url, [string]$Destination) {
    Write-Host "    Downloading $Url"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
}

Write-Host "Spanish Dubbing Studio - local setup" -ForegroundColor White
Write-Host "Project folder: $Root"

# ---------------------------------------------------------------- Python 3.10-3.12
Write-Step "Locating Python (3.11 recommended; 3.13 is not supported yet)"
$PythonExe = $null
foreach ($version in @("3.11", "3.12", "3.10")) {
    try {
        $candidate = (& py "-$version" -c "import sys; print(sys.executable)" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            $candidate = ($candidate | Select-Object -First 1).Trim()
            if (Test-Path $candidate) {
                $PythonExe = $candidate
                break
            }
        }
    }
    catch { }
}
if (-not $PythonExe) {
    foreach ($name in @("python", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            $version = (& $command.Source -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))" 2>$null)
            if ($version -in @("3.10", "3.11", "3.12")) {
                $PythonExe = $command.Source
                break
            }
        }
    }
}
if (-not $PythonExe) {
    Fail @"
Python 3.10, 3.11 or 3.12 was not found.
Install Python 3.11 (64-bit) and enable "Add python.exe to PATH":
  winget install Python.Python.3.11
Then close this window, open a new one and run setup again.
"@
}
Write-Ok "Python: $PythonExe"

# --------------------------------------------------------------------- venv + pip
Write-Step "Preparing the Python virtual environment (.venv)"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if ($Force -and (Test-Path (Join-Path $Root ".venv"))) {
    Remove-Item -Recurse -Force (Join-Path $Root ".venv")
}
if (-not (Test-Path $VenvPython)) {
    & $PythonExe -m venv (Join-Path $Root ".venv")
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment." }
}
& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { Fail "Could not update pip." }
Write-Ok "Virtual environment ready"

Write-Step "Installing Python dependencies (CPU build of PyTorch)"
& $VenvPython -m pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.5.1"
if ($LASTEXITCODE -ne 0) { Fail "Could not install PyTorch (CPU)." }
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "Could not install the Python requirements." }
Write-Ok "Python dependencies installed"

# ----------------------------------------------------------------------- binaries
if (-not $SkipBinaries) {
    Write-Step "Installing local tools (FFmpeg and Piper)"
    $tools = Join-Path $Root "tools"
    New-Item -ItemType Directory -Force $tools | Out-Null

    $ffmpegExe = Join-Path $tools "ffmpeg\bin\ffmpeg.exe"
    if (-not (Test-Path $ffmpegExe)) {
        $zip = Join-Path $env:TEMP "vts-ffmpeg-essentials.zip"
        $extract = Join-Path $env:TEMP "vts-ffmpeg-extract"
        if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
        Download-File "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" $zip
        Expand-Archive -Path $zip -DestinationPath $extract -Force
        $inner = Get-ChildItem $extract -Directory | Select-Object -First 1
        if (-not $inner) { Fail "The FFmpeg archive had an unexpected layout." }
        $target = Join-Path $tools "ffmpeg"
        if (Test-Path $target) { Remove-Item -Recurse -Force $target }
        Move-Item $inner.FullName $target
        Remove-Item -Force $zip -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $extract -ErrorAction SilentlyContinue
        if (-not (Test-Path $ffmpegExe)) { Fail "FFmpeg was not installed correctly." }
    }
    Write-Ok "FFmpeg: $ffmpegExe"

    $piperExe = Join-Path $tools "piper\piper.exe"
    if (-not (Test-Path $piperExe)) {
        $zip = Join-Path $env:TEMP "vts-piper-windows.zip"
        $extract = Join-Path $env:TEMP "vts-piper-extract"
        if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
        Download-File "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip" $zip
        Expand-Archive -Path $zip -DestinationPath $extract -Force
        $inner = Get-ChildItem $extract -Recurse -Filter "piper.exe" | Select-Object -First 1
        if (-not $inner) { Fail "The Piper archive did not contain piper.exe." }
        $target = Join-Path $tools "piper"
        if (Test-Path $target) { Remove-Item -Recurse -Force $target }
        New-Item -ItemType Directory -Force $target | Out-Null
        Copy-Item (Join-Path $inner.Directory.FullName "*") $target -Recurse -Force
        Remove-Item -Force $zip -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $extract -ErrorAction SilentlyContinue
        if (-not (Test-Path $piperExe)) { Fail "Piper was not installed correctly." }
    }
    Write-Ok "Piper: $piperExe"
}
else {
    Write-Host "    Skipping binary downloads (-SkipBinaries)." -ForegroundColor Yellow
}

# ----------------------------------------------------------------------- frontend
if (-not $SkipFrontend) {
    Write-Step "Building the web interface (React + Vite)"
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) {
        $npm = Get-Command npm -ErrorAction SilentlyContinue
    }
    if (-not $npm) {
        Fail @"
Node.js was not found. Install Node.js 20 LTS or newer:
  winget install OpenJS.NodeJS.LTS
Then close this window, open a new one and run setup again.
"@
    }
    Push-Location (Join-Path $Root "frontend")
    try {
        & $npm.Source install --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { Fail "npm install failed." }
        & $npm.Source run build
        if ($LASTEXITCODE -ne 0) { Fail "The frontend build failed." }
    }
    finally {
        Pop-Location
    }
    Write-Ok "Interface built in frontend\dist"
}
else {
    Write-Host "    Skipping the frontend build (-SkipFrontend)." -ForegroundColor Yellow
}

# ------------------------------------------------------------------------- models
if (-not $SkipModels) {
    Write-Step "Downloading the minimal model set (about 500 MB)"
    Write-Host "    whisper-tiny + marian-en-es + Piper es_MX-ald-medium"
    Write-Host "    Files are stored under models\\. Nothing else is downloaded automatically."
    & $VenvPython (Join-Path $Root "backend\download_models.py") --minimal
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    Model download failed or was interrupted." -ForegroundColor Yellow
        Write-Host "    You can retry later from the app's Modelos page." -ForegroundColor Yellow
    }
    else {
        Write-Ok "Minimal models installed"
    }
}
else {
    Write-Host "    Skipping model downloads (-SkipModels)." -ForegroundColor Yellow
}

# ------------------------------------------------------------------------ verify
Write-Step "Verification"
& $VenvPython (Join-Path $Root "backend\verify_install.py")

# ---------------------------------------------------------------------- shortcut
$LauncherExe = Join-Path $Root "Spanish Dubbing Studio.exe"
if (Test-Path $LauncherExe) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $desktop = [Environment]::GetFolderPath("Desktop")
        if ($desktop) {
            $link = Join-Path $desktop "Spanish Dubbing Studio.lnk"
            $shortcut = $shell.CreateShortcut($link)
            $shortcut.TargetPath = $LauncherExe
            $shortcut.WorkingDirectory = $Root
            $shortcut.IconLocation = "$LauncherExe,0"
            $shortcut.Description = "Abrir Spanish Dubbing Studio (doblaje local al español)"
            $shortcut.Save()
            Write-Ok "Desktop shortcut created: $link"
        }
    }
    catch {
        Write-Host "    Could not create the desktop shortcut (not a problem)." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Setup finished." -ForegroundColor Green
Write-Host "Start the app with a double click on:" -ForegroundColor White
Write-Host "  Spanish Dubbing Studio.exe   (or the Desktop shortcut)"
Write-Host "Console alternative:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1"
Write-Host ""
Write-Host "The app opens at http://127.0.0.1:8765 and only accepts local connections."
