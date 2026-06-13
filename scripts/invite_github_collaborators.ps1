# Invite GitHub collaborators from config and agent records.
$ErrorActionPreference = "Stop"

function Resolve-GhExe {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $path = "${env:ProgramFiles}\GitHub CLI\gh.exe"
    if (Test-Path $path) { return $path }
    throw "GitHub CLI not found. Install: winget install GitHub.cli -e -h --accept-package-agreements"
}

$gh = Resolve-GhExe
$root = Split-Path $PSScriptRoot -Parent
$repo = "mafzalkalwardev/indus-transport-auto-dialer"

$usernames = New-Object System.Collections.Generic.HashSet[string]
$configPath = Join-Path $root "config\github_collaborators.json"
if (Test-Path $configPath) {
    $cfg = Get-Content $configPath -Raw | ConvertFrom-Json
    foreach ($u in @($cfg.collaborators)) {
        if ($u) { [void]$usernames.Add($u.ToString().Trim()) }
    }
    $permission = $cfg.default_permission
} else {
    $permission = "push"
}

$agentsPath = Join-Path $root "data\agents.json"
if (Test-Path $agentsPath) {
    $agents = Get-Content $agentsPath -Raw | ConvertFrom-Json
    foreach ($agent in @($agents)) {
        $ghUser = $agent.github_username
        if ($ghUser) { [void]$usernames.Add($ghUser.ToString().Trim()) }
    }
}

$owner = (& $gh api user --jq .login).Trim()
[void]$usernames.Remove($owner)

if ($usernames.Count -eq 0) {
    Write-Host "No collaborator usernames configured."
    Write-Host "Edit config\github_collaborators.json or add github_username to data\agents.json"
    exit 0
}

foreach ($user in $usernames) {
    Write-Host "Inviting $user ($permission)..."
    try {
        & $gh api "repos/$repo/collaborators/$user" -X PUT -f "permission=$permission" 2>&1 | Out-Host
        Write-Host "  OK: $user"
    } catch {
        Write-Warning "  Failed for ${user}: $_"
    }
}

Write-Host "Done. Current collaborators:"
& $gh api "repos/$repo/collaborators" --jq ".[].login"
