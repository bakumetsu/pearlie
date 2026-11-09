# dev only — binds 127.0.0.1:8000, no auth. Do NOT use for production.

param([switch]$Real)

$root = Split-Path -Parent $PSScriptRoot

if ($Real) {
    $env:PEARLIE_MODE = "real"
    Write-Host "Pearlie dev: REAL data mode (PEARLIE_MODE=real)"
} else {
    $env:PEARLIE_MODE = "fixture"
    Write-Host "Pearlie dev: FIXTURE mode (stubs only)"
}
if (-not $Real) { $env:PEARLIE_REAL = "" }

$backend = Start-Process `
    -FilePath (Join-Path $root "backend\.venv\Scripts\python.exe") `
    -ArgumentList "-m app.main" `
    -WorkingDirectory (Join-Path $root "backend") `
    -NoNewWindow -PassThru

try {
    Set-Location (Join-Path $root "frontend")
    npm run dev
}
finally {
    Stop-Process -Id $backend.Id
}
