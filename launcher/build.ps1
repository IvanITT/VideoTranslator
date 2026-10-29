# Builds "Spanish Dubbing Studio.exe", the one-click local launcher.
#
#   powershell -ExecutionPolicy Bypass -File .\launcher\build.ps1
#
# Requires Windows PowerShell 5.1 and the .NET Framework 4.x compiler that ships
# with Windows 10/11 (C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe).
# No extra downloads are needed.

[CmdletBinding()]
param(
    [switch]$SkipShortcut
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$LauncherDir = Split-Path -Parent $PSCommandPath
$Root = Split-Path -Parent $LauncherDir
$Source = Join-Path $LauncherDir "Launcher.cs"
$Manifest = Join-Path $LauncherDir "app.manifest"
$Icon = Join-Path $LauncherDir "app.ico"
$Exe = Join-Path $Root "Spanish Dubbing Studio.exe"

$Csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $Csc)) {
    $Csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe"
}
if (-not (Test-Path $Csc)) {
    throw "No se encontró el compilador de .NET Framework (csc.exe). Instala .NET Framework 4.8."
}

function New-RoundedPath {
    param(
        [single]$X, [single]$Y, [single]$W, [single]$H, [single]$R
    )
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $R * 2
    $path.AddArc($X, $Y, $d, $d, 180, 90)
    $path.AddArc($X + $W - $d, $Y, $d, $d, 270, 90)
    $path.AddArc($X + $W - $d, $Y + $H - $d, $d, $d, 0, 90)
    $path.AddArc($X, $Y + $H - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    return $path
}

# ---------------------------------------------------------------- icon (256 px)
Add-Type -AssemblyName System.Drawing
$size = 256
$bitmap = [System.Drawing.Bitmap]::new($size, $size)
$g = [System.Drawing.Graphics]::FromImage($bitmap)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::Transparent)

$plate = New-RoundedPath 8 8 240 240 54
$background = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
    [System.Drawing.Point]::new(20, 6),
    [System.Drawing.Point]::new(236, 250),
    [System.Drawing.Color]::FromArgb(255, 25, 36, 46),
    [System.Drawing.Color]::FromArgb(255, 6, 10, 14)
)
$g.FillPath($background, $plate)

$border = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(70, 255, 255, 255), 2)
$g.DrawPath($border, $plate)

$amber = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
    [System.Drawing.Rectangle]::new(0, 0, 1, $size),
    [System.Drawing.Color]::FromArgb(255, 253, 230, 138),
    [System.Drawing.Color]::FromArgb(255, 245, 158, 11),
    [System.Drawing.Drawing2D.LinearGradientMode]::Vertical
)

$heights = @(42, 74, 116, 152, 116, 74, 42)
$barWidth = 16
$gap = 14
$totalWidth = ($heights.Count * $barWidth) + (($heights.Count - 1) * $gap)
$x = [single](($size - $totalWidth) / 2)
foreach ($h in $heights) {
    $y = [single](($size - $h) / 2)
    $bar = New-RoundedPath $x $y $barWidth $h 8
    $g.FillPath($amber, $bar)
    $bar.Dispose()
    $x += $barWidth + $gap
}

# ICO with 32-bpp DIB images at several sizes (maximum compatibility with
# Explorer, the notification area and .NET's Icon class).
function Get-IconDib {
    param([System.Drawing.Bitmap]$Bitmap)

    $w = $Bitmap.Width
    $h = $Bitmap.Height
    $rect = [System.Drawing.Rectangle]::new(0, 0, $w, $h)
    $locked = $Bitmap.LockBits(
        $rect,
        [System.Drawing.Imaging.ImageLockMode]::ReadOnly,
        [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
    )
    try {
        $stride = $locked.Stride
        $buffer = New-Object byte[] ($stride * $h)
        [System.Runtime.InteropServices.Marshal]::Copy($locked.Scan0, $buffer, 0, $buffer.Length)
    }
    finally {
        $Bitmap.UnlockBits($locked)
    }

    $stream = [System.IO.MemoryStream]::new()
    $binary = [System.IO.BinaryWriter]::new($stream)
    $binary.Write([UInt32]40)                 # BITMAPINFOHEADER
    $binary.Write([Int32]$w)
    $binary.Write([Int32]($h * 2))            # XOR + AND masks
    $binary.Write([UInt16]1)
    $binary.Write([UInt16]32)
    $binary.Write([UInt32]0)                  # BI_RGB
    $binary.Write([UInt32]($w * $h * 4))
    $binary.Write([Int32]0)
    $binary.Write([Int32]0)
    $binary.Write([UInt32]0)
    $binary.Write([UInt32]0)
    for ($y = $h - 1; $y -ge 0; $y--) {
        $binary.Write($buffer, ($y * $stride), ($w * 4))
    }
    $maskWidth = [math]::Floor(($w + 31) / 32) * 4
    $mask = New-Object byte[] ($maskWidth * $h)
    $binary.Write($mask, 0, $mask.Length)
    $binary.Flush()
    $bytes = $stream.ToArray()
    $binary.Dispose()
    $stream.Dispose()
    return ,$bytes
}

$sizes = @(16, 32, 48, 64, 128, 256)
$images = @()
foreach ($s in $sizes) {
    if ($s -eq $size) {
        $scaled = $bitmap
    }
    else {
        $scaled = [System.Drawing.Bitmap]::new($s, $s)
        $scaler = [System.Drawing.Graphics]::FromImage($scaled)
        $scaler.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $scaler.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $scaler.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $scaler.DrawImage($bitmap, 0, 0, $s, $s)
        $scaler.Dispose()
    }
    $images += ,(Get-IconDib $scaled)
    if ($s -ne $size) { $scaled.Dispose() }
}

$icoStream = [System.IO.MemoryStream]::new()
$writer = [System.IO.BinaryWriter]::new($icoStream)
$writer.Write([UInt16]0)                      # reserved
$writer.Write([UInt16]1)                      # type: icon
$writer.Write([UInt16]$sizes.Count)           # image count
$offset = 6 + (16 * $sizes.Count)
for ($i = 0; $i -lt $sizes.Count; $i++) {
    $s = $sizes[$i]
    $bytes = $images[$i]
    $writer.Write([Byte]$(if ($s -ge 256) { 0 } else { $s }))
    $writer.Write([Byte]$(if ($s -ge 256) { 0 } else { $s }))
    $writer.Write([Byte]0)                    # palette
    $writer.Write([Byte]0)                    # reserved
    $writer.Write([UInt16]1)                  # color planes
    $writer.Write([UInt16]32)                 # bits per pixel
    $writer.Write([UInt32]$bytes.Length)
    $writer.Write([UInt32]$offset)
    $offset += $bytes.Length
}
foreach ($bytes in $images) { $writer.Write($bytes) }
$writer.Flush()
[System.IO.File]::WriteAllBytes($Icon, $icoStream.ToArray())
$writer.Dispose()
$icoStream.Dispose()
$g.Dispose()
$bitmap.Dispose()
$background.Dispose()
$border.Dispose()
$amber.Dispose()
$plate.Dispose()

# -------------------------------------------------------------------- compile
Write-Host "Compilando el lanzador..." -ForegroundColor Cyan
& $Csc /nologo /target:winexe /platform:anycpu /codepage:65001 /optimize+ `
    "/out:$Exe" "/win32icon:$Icon" "/win32manifest:$Manifest" `
    /reference:System.dll /reference:System.Windows.Forms.dll /reference:System.Drawing.dll `
    $Source

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Exe)) {
    throw "La compilación del lanzador falló (código $LASTEXITCODE)."
}

$info = Get-Item $Exe
Write-Host ("Listo: {0} ({1:N0} KB)" -f $info.FullName, ($info.Length / 1KB)) -ForegroundColor Green

# ---------------------------------------------------------------- shortcuts
if (-not $SkipShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $targets = @()
    $desktop = [Environment]::GetFolderPath("Desktop")
    if ($desktop) { $targets += (Join-Path $desktop "Spanish Dubbing Studio.lnk") }
    $programs = [Environment]::GetFolderPath("Programs")
    if ($programs) { $targets += (Join-Path $programs "Spanish Dubbing Studio.lnk") }

    foreach ($link in $targets) {
        $shortcut = $shell.CreateShortcut($link)
        $shortcut.TargetPath = $Exe
        $shortcut.WorkingDirectory = $Root
        $shortcut.IconLocation = "$Exe,0"
        $shortcut.Description = "Abrir Spanish Dubbing Studio (doblaje local al español)"
        $shortcut.Save()
        Write-Host "Acceso directo: $link" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Doble clic en «Spanish Dubbing Studio.exe» para iniciar la aplicación." -ForegroundColor White
Write-Host "El icono queda en la bandeja del sistema; clic derecho para detenerla o salir."
