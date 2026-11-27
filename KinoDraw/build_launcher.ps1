$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

& $py (Join-Path $root "launcher\make_icon.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ico = Join-Path $root "KinoDraw.ico"
$outExe = Join-Path $root "KinoDraw.exe"
& $csc /nologo /optimize+ /platform:x64 /target:winexe /win32icon:$ico `
    /out:$outExe /r:System.dll /r:System.Windows.Forms.dll `
    (Join-Path $root "launcher\Launcher.cs")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Built: $outExe ($([Math]::Round((Get-Item $outExe).Length / 1KB, 1)) KB)"
