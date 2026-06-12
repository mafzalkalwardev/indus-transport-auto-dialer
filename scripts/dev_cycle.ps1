# FT Solutions Auto Dialer — local test + optional push cycle
# Usage:
#   .\scripts\dev_cycle.ps1           # tests only
#   .\scripts\dev_cycle.ps1 -Push     # tests, commit, push

param(
    [switch]$Push,
    [string]$Message = "Auto cycle: tests pass, dialer reliability updates"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "==> pytest" -ForegroundColor Cyan
python -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> prepare test dial list (optional CRM test contacts)" -ForegroundColor Cyan
python scripts/prepare_test_dial.py

if ($Push) {
    Write-Host "==> git commit + push" -ForegroundColor Cyan
    git add -A
    git status --short
    git commit -m $Message
    git push origin main
}

Write-Host "Done." -ForegroundColor Green
