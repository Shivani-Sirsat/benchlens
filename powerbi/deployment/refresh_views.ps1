#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Refresh BenchLens reporting views and report status.

.DESCRIPTION
    Wraps `benchlens reports views refresh` + `benchlens reports views check`.
    Intended as the pre-step before a Power BI Service scheduled refresh.

.EXAMPLE
    .\refresh_views.ps1
#>

$ErrorActionPreference = "Stop"

Write-Host "[BenchLens] Activating venv..." -ForegroundColor Cyan
$repoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Push-Location $repoRoot
try {
    & "$repoRoot\.venv\Scripts\Activate.ps1"

    Write-Host "[BenchLens] Refreshing reporting views..." -ForegroundColor Cyan
    python -m benchlens.main reports views refresh
    if ($LASTEXITCODE -ne 0) { throw "View refresh failed." }

    Write-Host "[BenchLens] Verifying view installation..." -ForegroundColor Cyan
    python -m benchlens.main reports views check
    if ($LASTEXITCODE -ne 0) { throw "View check reported missing views." }

    Write-Host "[BenchLens] All views OK." -ForegroundColor Green
}
finally {
    Pop-Location
}
