# Spanish Dubbing Studio - install or verify dependencies
#
# Double-click "Instalar o Verificar.bat" (or run this script) to check whether
# this computer has everything needed. If something is missing, it offers to run
# scripts\setup.ps1.
#
#   powershell -ExecutionPolicy Bypass -File .\instalar-o-verificar.ps1
#   powershell -ExecutionPolicy Bypass -File .\instalar-o-verificar.ps1 -VerifyOnly
#   powershell -ExecutionPolicy Bypass -File .\instalar-o-verificar.ps1 -Install
#
# Optional install flags: -SkipModels -SkipBinaries -SkipFrontend -Force

[CmdletBinding()]
param(
    [switch]$VerifyOnly,
    [switch]$Install,
    [switch]$SkipModels,
    [switch]$SkipBinaries,
    [switch]$SkipFrontend,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSCommandPath
Set-Location $Root
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) {
    Write-Host "  [OK]    $Text" -ForegroundColor Green
}

function Write-Missing([string]$Text) {
    Write-Host "  [FALTA] $Text" -ForegroundColor Yellow
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "ERROR: $Text" -ForegroundColor Red
    exit 1
}

function Find-Python {
    foreach ($version in @("3.11", "3.12", "3.10")) {
        try {
            $candidate = (& py "-$version" -c "import sys; print(sys.executable)" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $candidate) {
                $candidate = ($candidate | Select-Object -First 1).Trim()
                if (Test-Path $candidate) { return $candidate }
            }
        }
        catch { }
    }
    foreach ($name in @("python", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            $version = (& $command.Source -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))" 2>$null)
            if ($version -in @("3.10", "3.11", "3.12")) { return $command.Source }
        }
    }
    return $null
}

function Get-Report {
    $checks = New-Object System.Collections.Generic.List[object]
    $allOk = $true

    $python = Find-Python
    if ($python) {
        Write-Ok "Python compatible: $python"
        $checks.Add([pscustomobject]@{ Name = "Python"; Ok = $true })
    }
    else {
        Write-Missing "Python 3.10, 3.11 or 3.12 (3.11 recommended)"
        $checks.Add([pscustomobject]@{ Name = "Python"; Ok = $false })
        $allOk = $false
    }

    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        Write-Ok "Entorno virtual: .venv"
        $checks.Add([pscustomobject]@{ Name = "venv"; Ok = $true })
    }
    else {
        Write-Missing "Entorno virtual .venv (ejecuta scripts\setup.ps1)"
        $checks.Add([pscustomobject]@{ Name = "venv"; Ok = $false })
        $allOk = $false
    }

    $depsOk = $false
    if (Test-Path $venvPython) {
        & $venvPython -c "import uvicorn, fastapi, torch, faster_whisper, transformers, soundfile, numpy, psutil" 2>$null | Out-Null
        $depsOk = ($LASTEXITCODE -eq 0)
    }
    if ($depsOk) {
        Write-Ok "Dependencias Python (uvicorn, FastAPI, PyTorch, Whisper, Marian, audio)"
        $checks.Add([pscustomobject]@{ Name = "python-deps"; Ok = $true })
    }
    else {
        Write-Missing "Dependencias Python; ejecuta: .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
        $checks.Add([pscustomobject]@{ Name = "python-deps"; Ok = $false })
        $allOk = $false
    }

    $binaries = @(
        @{ Name = "FFmpeg"; Path = Join-Path $Root "tools\ffmpeg\bin\ffmpeg.exe" },
        @{ Name = "FFprobe"; Path = Join-Path $Root "tools\ffmpeg\bin\ffprobe.exe" },
        @{ Name = "Piper"; Path = Join-Path $Root "tools\piper\piper.exe" }
    )
    foreach ($binary in $binaries) {
        if (Test-Path $binary.Path) {
            Write-Ok "$($binary.Name): $($binary.Path)"
            $checks.Add([pscustomobject]@{ Name = $binary.Name; Ok = $true })
        }
        else {
            Write-Missing "$($binary.Name): $($binary.Path)"
            $checks.Add([pscustomobject]@{ Name = $binary.Name; Ok = $false })
            $allOk = $false
        }
    }

    $frontend = Join-Path $Root "frontend\dist\index.html"
    if (Test-Path $frontend) {
        Write-Ok "Interfaz compilada: frontend\dist"
        $checks.Add([pscustomobject]@{ Name = "frontend"; Ok = $true })
    }
    else {
        Write-Missing "Interfaz compilada (npm install && npm run build en frontend\)"
        $checks.Add([pscustomobject]@{ Name = "frontend"; Ok = $false })
        $allOk = $false
    }

    $asr = @("whisper-tiny", "whisper-base", "whisper-small") |
        Where-Object { Test-Path (Join-Path $Root "models\$_\model.bin") } |
        Select-Object -First 1
    $translation = @(
        "marian-en-es", "marian-fr-es", "marian-de-es", "marian-pt-es",
        "marian-it-es", "nllb-200-distilled-600M"
    ) | Where-Object { Test-Path (Join-Path $Root "models\$_\pytorch_model.bin") } |
        Select-Object -First 1
    $tts = Get-ChildItem (Join-Path $Root "models\piper") -Recurse -Filter "*.onnx" `
        -ErrorAction SilentlyContinue | Select-Object -First 1

    if ($asr) {
        Write-Ok "Reconocimiento de voz: $asr"
        $checks.Add([pscustomobject]@{ Name = "asr"; Ok = $true })
    }
    else {
        Write-Missing "Modelo de reconocimiento de voz (Whisper)"
        $checks.Add([pscustomobject]@{ Name = "asr"; Ok = $false })
        $allOk = $false
    }
    if ($translation) {
        Write-Ok "Traducción: $translation"
        $checks.Add([pscustomobject]@{ Name = "translation"; Ok = $true })
    }
    else {
        Write-Missing "Modelo de traducción (MarianMT o NLLB)"
        $checks.Add([pscustomobject]@{ Name = "translation"; Ok = $false })
        $allOk = $false
    }
    if ($tts) {
        Write-Ok "Voz en español: $($tts.Name)"
        $checks.Add([pscustomobject]@{ Name = "tts"; Ok = $true })
    }
    else {
        Write-Missing "Voz Piper en español"
        $checks.Add([pscustomobject]@{ Name = "tts"; Ok = $false })
        $allOk = $false
    }

    if (Test-Path $venvPython) {
        & $venvPython (Join-Path $Root "backend\verify_install.py") --strict | Out-Host
        if ($LASTEXITCODE -ne 0) { $allOk = $false }
    }

    return [pscustomobject]@{ AllOk = $allOk; Checks = $checks }
}

Write-Host "Spanish Dubbing Studio - Instalar o verificar dependencias" -ForegroundColor White
Write-Host "Carpeta del proyecto: $Root"
Write-Step "Comprobando el entorno"

$report = Get-Report

if ($VerifyOnly) {
    if ($report.AllOk) {
        Write-Host ""
        Write-Host "Todo está listo para usar la aplicación." -ForegroundColor Green
        exit 0
    }
    Write-Host ""
    Write-Host "Faltan componentes. Ejecuta este script sin -VerifyOnly para instalarlos." -ForegroundColor Yellow
    exit 1
}

if (-not $Install) {
    if ($report.AllOk) {
        Write-Host ""
        Write-Host "Todo está listo para usar la aplicación." -ForegroundColor Green
        exit 0
    }
    Write-Host ""
    $answer = Read-Host "¿Instalar ahora las dependencias que faltan? [S/N]"
    if ($answer -notmatch "^[SsYy]") {
        Write-Host "Instalación cancelada. No se modificó nada." -ForegroundColor Yellow
        exit 1
    }
}

$setup = Join-Path $Root "scripts\setup.ps1"
if (-not (Test-Path $setup)) {
    Fail "No se encontró scripts\setup.ps1. Descarga el proyecto completo."
}

$setupArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $setup)
if ($SkipModels) { $setupArgs += "-SkipModels" }
if ($SkipBinaries) { $setupArgs += "-SkipBinaries" }
if ($SkipFrontend) { $setupArgs += "-SkipFrontend" }
if ($Force) { $setupArgs += "-Force" }

Write-Step "Instalando dependencias con scripts\setup.ps1"
& powershell @setupArgs
if ($LASTEXITCODE -ne 0) {
    Fail "La instalación no terminó correctamente. Revisa el mensaje anterior."
}

Write-Step "Verificación final"
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Fail "No se creó .venv. Revisa la instalación de Python."
}
& $venvPython (Join-Path $Root "backend\verify_install.py") --strict
if ($LASTEXITCODE -ne 0) {
    if ($SkipModels) {
        Write-Host ""
        Write-Host "Dependencias instaladas. Faltan modelos: descárgalos desde la página Modelos." -ForegroundColor Yellow
        exit 0
    }
    Fail "La verificación final encontró componentes pendientes."
}

Write-Host ""
Write-Host "Instalación completa. Abre Spanish Dubbing Studio.exe." -ForegroundColor Green
exit 0
