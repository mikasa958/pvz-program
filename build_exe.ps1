# Build single-file Tower Defense game executable (Windows).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
    $python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
}

Write-Host "Installing dependencies..."
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt
& $python -m pip install pyinstaller

Write-Host "Building TowerDefense.exe (this may take a few minutes)..."
& $python -m PyInstaller --noconfirm --clean tower_defense.spec

$exePath = Join-Path $PSScriptRoot "dist\TowerDefense.exe"
if (-not (Test-Path $exePath)) {
    throw "Build failed: $exePath was not created."
}

Write-Host ""
Write-Host "Done. Executable:"
Write-Host "  $exePath"
Write-Host ""
Write-Host "Double-click TowerDefense.exe to play. Logs are written next to the exe under logs\"
