# GitHub profile achievements — speedrun guide

Badges can take **up to 24 hours** to appear on your profile after the qualifying action.

## Your current progress (repo: `indus-transport-auto-dialer`)

| Badge | Requirement | Your status | Next step |
|-------|-------------|-------------|-----------|
| **Pull Shark** | 2 / 16 / 128 merged PRs (you authored) | **3 merged** — base tier done | Run `pull-shark -Count 13` for **bronze** |
| **Pair Extraordinaire** | 1 / 10 / 24 co-authored merged PRs | **1** (PR #4) — base tier done | Run `pair -Count 9` for **bronze** |
| **Quickdraw** | Close issue or PR within 5 min | Unknown | Run `quickdraw` once |
| **YOLO** | Merge your PR without review | Unknown | Run `yolo` once (no branch protection on `master`) |
| **Galaxy Brain** | 2 / 8 / 16 accepted discussion answers | Not started | Discussions **enabled** — post Q&A, mark answers |
| **Starstruck** | 16 / 128 / 512 stars on a repo | 0 stars | Promote repo; hard to automate ethically |

## One-command automation (fastest)

From repo root, with [GitHub CLI](https://cli.github.com/) logged in (`gh auth login`):

```powershell
# Check progress
.\scripts\github_achievements.ps1 -Mode status

# One-time badges (~1 minute)
.\scripts\github_achievements.ps1 -Mode quickdraw
.\scripts\github_achievements.ps1 -Mode yolo

# Pull Shark bronze: 13 more merges (you have 3, need 16)
.\scripts\github_achievements.ps1 -Mode pull-shark -Count 13

# Pair Extraordinaire bronze: 9 co-authored merges (you have 1, need 10)
.\scripts\github_achievements.ps1 -Mode pair -Count 9

# Everything above in one run (from a clean master checkout)
.\scripts\github_achievements.ps1 -Mode all -Count 13
```

**Important:** Run `pull-shark` / `pair` from a **clean `master` checkout** (or a git worktree) so local WIP does not block branch switches:

```powershell
git worktree add ..\Auto-Dialer-achievements master
cd ..\Auto-Dialer-achievements
copy "..\Auto Dialer\scripts\github_achievements.ps1" scripts\
copy "..\Auto Dialer\docs\github-achievement-log.md" docs\
.\scripts\github_achievements.ps1 -Mode all -Count 13
```

Each automated PR only appends one line to `docs/github-achievement-log.md` — minimal noise, easy to audit.

## Legitimate shortcuts (real work, still counts)

1. **Merge open feature PRs** — PR #17, #16 count toward Pull Shark and may unlock YOLO if merged without review.
2. **Close stale issues with real fixes** — e.g. #6 (screenshots) was addressed in README; close with a comment linking the commit.
3. **Galaxy Brain** — In [Discussions](https://github.com/mafzalkalwardev/indus-transport-auto-dialer/discussions):
   - Post a FAQ: "How do I install on a client PC?"
   - Answer with steps from `CLIENT.md`
   - A second account (or collaborator) must mark the reply as **Answer**.
4. **Dependabot PRs** — Merging them improves the repo but **does not** count toward Pull Shark (author is `dependabot`, not you).

## Achievement tiers reference

| Badge | Base | Bronze | Silver | Gold |
|-------|------|--------|--------|------|
| Pull Shark | 2 | 16 | 128 | 1024 |
| Pair Extraordinaire | 1 | 10 | 24 | 48 |
| Galaxy Brain | 2 | 8 | 16 | 32 |
| Starstruck | 16 | 128 | 512 | 4096 |

## Already configured on this repo

- **Discussions** — enabled for Galaxy Brain practice
- **Contribution snake** — `.github/workflows/snake.yml` updates profile graph SVGs
- **No branch protection** on `master` — YOLO merges allowed
