# Remove local dev/cache folders to keep the workspace light.
# Safe to run anytime — does not delete user CRM data in logs\ or chrome_profiles\.

param(
    [switch]$IncludeProfiles,
    [switch]$IncludeLogs
)

$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if ((Split-Path -Leaf $Root) -eq "scripts") {
    $Root = Split-Path -Parent $Root
}

Write-Host "Cleaning workspace: $Root" -ForegroundColor Cyan

$dirs = @(
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".codegraph",
    ".sixth"
)

if ($IncludeProfiles) { $dirs += "chrome_profiles" }
if ($IncludeLogs) { $dirs += "logs" }

foreach ($name in $dirs) {
    $path = Join-Path $Root $name
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
        Write-Host "  removed $name\" -ForegroundColor Yellow
    }
}

Get-ChildItem -LiteralPath $Root -Recurse -Directory -Filter "__pycache__" | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
}

$junk = @(
    "INDUS TRANSPORTS LOGO.jpg",
    "phones.xlsx",
    "phones_test.xlsx",
    "MEMORIES.md",
    "prompt.md"
)
foreach ($name in $junk) {
    $path = Join-Path $Root $name
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
        Write-Host "  removed $name" -ForegroundColor Yellow
    }
}

Write-Host "Done. Runtime folders logs\, data\, chrome_profiles\ kept (use -IncludeProfiles / -IncludeLogs to wipe)." -ForegroundColor Green
