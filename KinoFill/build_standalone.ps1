$ErrorActionPreference = "Stop"
$py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
Set-Location $PSScriptRoot

& $py -m PyInstaller `
    --noconfirm `
    --windowed `
    --name "KinoFill-Standalone" `
    --icon "KinoFill.ico" `
    --hidden-import "PySide6.QtPdf" `
    --hidden-import "PySide6.QtPrintSupport" `
    main.py

Write-Host "Built standalone bundle in dist\KinoFill-Standalone\"
