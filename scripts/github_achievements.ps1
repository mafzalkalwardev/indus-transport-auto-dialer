# GitHub profile achievements - fast progress on your own repo.
# Requires: gh auth login
#
# Usage:
#   .\scripts\github_achievements.ps1 -Mode status
#   .\scripts\github_achievements.ps1 -Mode quickdraw
#   .\scripts\github_achievements.ps1 -Mode yolo
#   .\scripts\github_achievements.ps1 -Mode pull-shark -Count 13
#   .\scripts\github_achievements.ps1 -Mode pair -Count 9
#   .\scripts\github_achievements.ps1 -Mode all -Count 13 -PairCount 9

param(
    [ValidateSet("status", "quickdraw", "yolo", "pull-shark", "pair", "all", "discussions")]
    [string]$Mode = "status",
    [int]$Count = 13,
    [int]$PairCount = 9,
    [string]$Repo = "mafzalkalwardev/indus-transport-auto-dialer",
    [string]$BaseBranch = "master",
    [string]$CoAuthorName = "Cursor",
    [string]$CoAuthorEmail = "cursoragent@cursor.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Invoke-Git {
    param([string[]]$GitArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $lines = @()
    & git @GitArgs 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $lines += $_.ToString()
        }
        else {
            $lines += "$_"
        }
    }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0) {
        throw "git command failed (exit $code): $($lines -join [Environment]::NewLine)"
    }
    return ($lines -join [Environment]::NewLine).Trim()
}

function Invoke-Gh {
    param([string[]]$GhArgs)
    # gh writes success messages (checkmarks) to stderr; ignore NativeCommandError when exit code is 0.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $lines = @()
    & gh @GhArgs 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $lines += $_.ToString()
        }
        else {
            $lines += "$_"
        }
    }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0) {
        throw "gh command failed (exit $code): $($lines -join [Environment]::NewLine)"
    }
    return ($lines -join [Environment]::NewLine).Trim()
}

function Get-AchievementStatus {
    $user = Invoke-Gh @("api", "user", "-q", ".login")
    $mergedJson = Invoke-Gh @(
        "pr", "list", "-R", $Repo, "--state", "merged", "--author", $user,
        "--limit", "200", "--json", "number,title,mergedAt"
    )
    $merged = $mergedJson | ConvertFrom-Json
    $openJson = Invoke-Gh @("pr", "list", "-R", $Repo, "--state", "open", "--limit", "20", "--json", "number")
    $open = $openJson | ConvertFrom-Json
    Write-Host ""
    Write-Host "GitHub user: $user"
    Write-Host "Merged PRs (you): $($merged.Count)"
    Write-Host "Pull Shark tiers: base=2 bronze=16 silver=128"
    Write-Host "Pair Extraordinaire tiers: base=1 bronze=10 silver=24"
    Write-Host "Open PRs: $($open.Count)"
    if ($merged.Count -lt 16) {
        $need = 16 - $merged.Count
        Write-Host "Next: pull-shark -Count $need for bronze Pull Shark"
    }
}

function Invoke-Quickdraw {
    $title = "chore: achievement quickdraw $(Get-Date -Format 'yyyy-MM-dd HHmmss')"
    Write-Host "Creating issue..."
    $issueUrl = Invoke-Gh @(
        "issue", "create", "-R", $Repo, "-t", $title,
        "-b", "Closed immediately for Quickdraw achievement."
    )
    Start-Sleep -Seconds 2
    $number = ($issueUrl -split "/")[-1]
    Invoke-Gh @("issue", "close", $number, "-R", $Repo) | Out-Null
    Write-Host "Quickdraw done - closed issue #$number"
}

function Ensure-AchievementLog {
    $path = Join-Path $Root "docs\github-achievement-log.md"
    if (-not (Test-Path $path)) {
        $header = @"
# GitHub achievement log

Automated micro-entries for Pull Shark / Pair Extraordinaire progress.

| # | Branch | Merged (UTC) | Co-authored |
|---|--------|--------------|-------------|

"@
        New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null
        Set-Content -Path $path -Value $header -Encoding UTF8
    }
}

function Update-AchievementLog {
    param([int]$Index, [string]$Branch, [bool]$CoAuthor)
    Ensure-AchievementLog
    $path = Join-Path $Root "docs\github-achievement-log.md"
    $co = if ($CoAuthor) { "yes" } else { "no" }
    $line = "| $Index | $Branch | $(Get-Date -Format 'yyyy-MM-dd HH:mm') | $co |"
    Add-Content -Path $path -Value $line -Encoding UTF8
}

function Invoke-PullSharkBatch {
    param(
        [int]$BatchCount,
        [bool]$CoAuthor = $false,
        [string]$Label = "pull-shark"
    )

    if ($BatchCount -le 0) {
        Write-Host "Skipping $Label batch (Count=0)."
        return
    }

    Ensure-AchievementLog
    Invoke-Git @("fetch", "origin", $BaseBranch) | Out-Null
    Invoke-Git @("checkout", $BaseBranch) | Out-Null
    Invoke-Git @("pull", "origin", $BaseBranch) | Out-Null

    for ($i = 1; $i -le $BatchCount; $i++) {
        $stamp = Get-Date -Format "yyyyMMddHHmmss"
        $branch = "achievement/$Label-$stamp-$i"
        $msg = "docs: achievement log entry $Label $i"

        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & git checkout -b $branch "origin/$BaseBranch" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Invoke-Git @("checkout", "-b", $branch, $BaseBranch) | Out-Null
        }
        $ErrorActionPreference = $prev

        Update-AchievementLog -Index $i -Branch $branch -CoAuthor $CoAuthor
        Invoke-Git @("add", "docs/github-achievement-log.md") | Out-Null

        if ($CoAuthor) {
            $commitMsg = @"
$msg

Co-authored-by: $CoAuthorName <$CoAuthorEmail>
"@
            Invoke-Git @("commit", "-m", $commitMsg) | Out-Null
        }
        else {
            Invoke-Git @("commit", "-m", $msg) | Out-Null
        }

        Invoke-Git @("push", "-u", "origin", $branch) | Out-Null
        $prUrl = Invoke-Gh @(
            "pr", "create", "-R", $Repo, "--base", $BaseBranch, "--head", $branch,
            "--title", $msg, "--body", "Micro doc update for GitHub achievement progress."
        )
        $prNum = ($prUrl -split "/")[-1]
        Invoke-Gh @("pr", "merge", $prNum, "-R", $Repo, "--merge", "--admin", "--delete-branch") | Out-Null
        Write-Host "Merged PR #$prNum ($i/$BatchCount) [$Label]"
        Invoke-Git @("checkout", $BaseBranch) | Out-Null
        Invoke-Git @("pull", "origin", $BaseBranch) | Out-Null
        Start-Sleep -Milliseconds 600
    }
    Write-Host "$Label batch complete: $BatchCount merges."
}

function Invoke-Yolo {
    $openJson = Invoke-Gh @(
        "pr", "list", "-R", $Repo, "--state", "open",
        "--json", "number,headRefName"
    )
    $prs = $openJson | ConvertFrom-Json
    $pick = $prs | Where-Object { $_.headRefName -like "achievement/*" } | Select-Object -First 1
    if (-not $pick) {
        Write-Host "Creating one achievement PR for YOLO..."
        Invoke-PullSharkBatch -BatchCount 1 -CoAuthor $false -Label "yolo"
        $openJson = Invoke-Gh @(
            "pr", "list", "-R", $Repo, "--state", "open",
            "--json", "number,headRefName"
        )
        $prs = $openJson | ConvertFrom-Json
        $pick = $prs | Where-Object { $_.headRefName -like "achievement/*" } | Select-Object -First 1
    }
    if (-not $pick) {
        Write-Host "YOLO skipped - no open achievement PR (may already be merged)."
        return
    }
    Write-Host "YOLO merge PR #$($pick.number) without review..."
    Invoke-Gh @("pr", "merge", "$($pick.number)", "-R", $Repo, "--merge", "--admin", "--delete-branch") | Out-Null
    Write-Host "YOLO done."
}

function Enable-Discussions {
    Write-Host "Enabling GitHub Discussions..."
    Invoke-Gh @("api", "-X", "PATCH", "repos/$Repo", "-f", "has_discussions=true") | Out-Null
    Write-Host "Discussions enabled."
}

switch ($Mode) {
    "status" { Get-AchievementStatus }
    "quickdraw" { Invoke-Quickdraw }
    "yolo" { Invoke-Yolo }
    "pull-shark" { Invoke-PullSharkBatch -BatchCount $Count -CoAuthor $false -Label "pull-shark" }
    "pair" { Invoke-PullSharkBatch -BatchCount $Count -CoAuthor $true -Label "pair" }
    "discussions" { Enable-Discussions }
    "all" {
        Write-Host "=== Quickdraw ==="
        Invoke-Quickdraw
        Write-Host "=== Discussions ==="
        Enable-Discussions
        Write-Host "=== Pull Shark ($Count) ==="
        Invoke-PullSharkBatch -BatchCount $Count -CoAuthor $false -Label "pull-shark"
        Write-Host "=== Pair Extraordinaire ($PairCount) ==="
        Invoke-PullSharkBatch -BatchCount $PairCount -CoAuthor $true -Label "pair"
        Write-Host "=== YOLO ==="
        Invoke-Yolo
        Write-Host "=== Status ==="
        Get-AchievementStatus
    }
}
