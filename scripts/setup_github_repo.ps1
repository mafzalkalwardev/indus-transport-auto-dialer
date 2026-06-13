# Run after: gh auth login --web
# Configures repo topics and verifies Dependabot / Actions access.
$ErrorActionPreference = "Stop"
$repo = "mafzalkalwardev/indus-transport-auto-dialer"

gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Run: gh auth login --hostname github.com --git-protocol https --web"
    exit 1
}

Write-Host "Adding repository topics..."
gh repo edit $repo `
  --add-topic python `
  --add-topic pyqt6 `
  --add-topic auto-dialer `
  --add-topic google-voice `
  --add-topic telephony `
  --add-topic amd `
  --add-topic predictive-dialer

Write-Host "Repository settings:"
gh repo view $repo --json nameWithOwner,url,repositoryTopics

Write-Host "Current collaborators:"
gh api "repos/$repo/collaborators" --jq ".[].login"

Write-Host ""
Write-Host "To invite a collaborator, run:"
Write-Host "  gh api repos/$repo/collaborators/USERNAME -X PUT -f permission=push"
