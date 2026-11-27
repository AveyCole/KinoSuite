param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PdfFiles
)

$ErrorActionPreference = "Stop"
$py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\pythonw.exe"
if (-not (Test-Path $py)) {
    $py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
}
$main = Join-Path $PSScriptRoot "main.py"
Start-Process -FilePath $py -ArgumentList (@($main) + $PdfFiles) -WorkingDirectory $PSScriptRoot
