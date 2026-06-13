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

function Test-RepoFile($gh, $repo, $path) {
    $code = & $gh api "repos/$Owner/$repo/contents/$path" --jq .name 2>$null
    return $LASTEXITCODE -eq 0
}

function Add-RepoFile($gh, $repo, $path, $content, [switch]$WhatIf) {
    if (Test-RepoFile $gh $repo $path) {
        Write-Host "  skip $repo/$path (exists)"
        return
    }
    if ($WhatIf) {
        Write-Host "  would add $repo/$path"
        return
    }
    $b64 = Encode-Base64 $content
    & $gh api "repos/$Owner/$repo/contents/$path" -X PUT `
        -f message="Add $path (repo standards)" `
        -f content=$b64 | Out-Null
    Write-Host "  added $repo/$path"
}

$gh = Resolve-GhExe
$templateDir = Join-Path $PSScriptRoot "repo-templates"
$files = @("LICENSE", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md")

$repos = & $gh repo list $Owner --limit 100 --json name,isFork --jq '.[] | select(.isFork==false) | .name'
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
        Add-RepoFile $gh $repo $file $content -WhatIf:$WhatIf
    }
    Start-Sleep -Milliseconds 300
}

Write-Host "Finished."
