# One-time setup of the development environment on Windows: .venv with Python 3.12 and the app's requirements,
# then a quick test run.   powershell -ExecutionPolicy Bypass -File dev\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv\Scripts\python.exe)) {
    Write-Host ">> Creating .venv (Python 3.12)"
    py -3.12 -m venv .venv
}
Write-Host ">> Installing requirements"
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning "ffmpeg is not on PATH - the timelapse and share tests need it (winget install Gyan.FFmpeg)"
}
Write-Host ">> Quick test run"
.venv\Scripts\python.exe tests\run.py --quick
