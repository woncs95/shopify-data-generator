$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Set-Location $Root
if (-not (Test-Path $Python)) {
    throw "Local .venv is missing. Create it with: python -m venv .venv"
}

$Arguments = @(
    "-m",
    "streamlit",
    "run",
    "shopify_registration_app.py",
    "--global.developmentMode=false",
    "--server.port",
    "8501",
    "--server.headless",
    "true",
    "--server.fileWatcherType",
    "none",
    "--browser.gatherUsageStats",
    "false"
)

Write-Host "Starting Shopify Product Registration UI..."
Write-Host "Open: http://localhost:8501"
Write-Host ""
Write-Host "Keep this window open while using the app."
Write-Host ""

& $Python @Arguments
