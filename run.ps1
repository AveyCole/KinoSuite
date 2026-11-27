$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\pythonw.exe"
Start-Process -FilePath $pyw -ArgumentList "`"$(Join-Path $root 'main.py')`"" -WorkingDirectory $root
