$ErrorActionPreference = "Stop"
$py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
Set-Location $PSScriptRoot

& $py -m PyInstaller `
    --noconfirm `
    --windowed `
    --name "KinoDraw-Standalone" `
    --icon "KinoDraw.ico" `
    --hidden-import "PySide6.QtSvg" `
    --hidden-import "PySide6.QtPrintSupport" `
    --hidden-import "reportlab" `
    --hidden-import "cv2" `
    main.py

Write-Host "Built standalone bundle in dist\KinoDraw-Standalone\"
