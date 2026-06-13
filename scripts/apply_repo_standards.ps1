# Apply standard LICENSE and policy markdown files to all GitHub repos (skip if file exists).
param(
    [string]$Owner = "mafzalkalwardev",
    [switch]$WhatIf
)
$ErrorActionPreference = "Stop"

function Resolve-GhExe {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $path = "${env:ProgramFiles}\GitHub CLI\gh.exe"
    if (Test-Path $path) { return $path }
    throw "GitHub CLI not found"
}

function Encode-Base64([string]$Text) {
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text))
}

function Test-RepoFile {
    param($Gh, [string]$Owner, [string]$Repo, [string]$Path)
    try {
        & $Gh api "repos/$Owner/$Repo/contents/$Path" --jq .name 2>$null | Out-Null
    } catch {
        return $false
    }
    return $LASTEXITCODE -eq 0
}

function Add-RepoFile {
    param($Gh, [string]$Owner, [string]$Repo, [string]$Path, [string]$Content, [switch]$WhatIf)
    if (Test-RepoFile -Gh $Gh -Owner $Owner -Repo $Repo -Path $Path) {
        Write-Host "  skip $Repo/$Path (exists)"
        return
    }
    if ($WhatIf) {
        Write-Host "  would add $Repo/$Path"
        return
    }
    $b64 = Encode-Base64 $Content
    & $Gh api "repos/$Owner/$Repo/contents/$Path" -X PUT `
        -f message="Add $Path (repo standards)" `
        -f content=$b64 1>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "  failed $Repo/$Path (exit $LASTEXITCODE)"
        return
    }
    Write-Host "  added $Repo/$Path"
}

$gh = Resolve-GhExe
$templateDir = Join-Path $PSScriptRoot "repo-templates"
$files = @("LICENSE", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md")

$reposJson = & $gh repo list $Owner --limit 100 --json name,isFork
$repos = ($reposJson | ConvertFrom-Json) | Where-Object { -not $_.isFork } | ForEach-Object { $_.name }
$skip = @("mafzalkalwardev")

foreach ($repo in $repos) {
    if ($skip -contains $repo) {
        Write-Host "skip profile repo: $repo"
        continue
    }
    Write-Host "Processing $Owner/$repo ..."
    foreach ($file in $files) {
        $src = Join-Path $templateDir $file
        if (-not (Test-Path $src)) { continue }
        $content = Get-Content $src -Raw
        Add-RepoFile -Gh $gh -Owner $Owner -Repo $repo -Path $file -Content $content -WhatIf:$WhatIf
    }
    Start-Sleep -Milliseconds 400
}

Write-Host "Finished. Processed $($repos.Count) repositories."
