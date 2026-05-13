$root = $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "GrassDefense" `
    (Join-Path $root "pvz_pygame.py")

if ($LASTEXITCODE -eq 0) {
    Copy-Item -LiteralPath (Join-Path $root "dist\GrassDefense.exe") -Destination (Join-Path $root "GrassDefense.exe") -Force
    Write-Host "Build finished: $root\dist\GrassDefense.exe"
    Write-Host "Copied to: $root\GrassDefense.exe"
}
