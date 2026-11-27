$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
$ico = Join-Path $root "KinoShop.ico"

& $py -m PyInstaller --noconfirm --windowed --name KinoShop --icon $ico `
    --add-data "plugins;plugins" (Join-Path $root "main.py")
