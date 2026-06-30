#!/usr/bin/env python3
"""Seed Galaxy Brain discussions and update profile README achievements section."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import textwrap

OWNER = "mafzalkalwardev"
DIALER = "indus-transport-auto-dialer"
PROFILE = OWNER

FAQ = [
    (
        "How do I install the Auto Dialer on a client PC?",
        textwrap.dedent(
            """
            Use an **admin export package** so agents only see sign-in:

            1. On the administrator PC, open **Settings** and connect Google Voice lines.
            2. Go to **Administration → Export client package…** and create the agent login.
            3. On the client PC, install the same app and copy the export folder into the app directory (`logs`, `data`, `chrome_profiles`, `dialer_config.json`).
            4. Run the app — the first screen should be **Agent sign-in** only.

            See `CLIENT.md` in the repository for the full checklist.
            """
        ).strip(),
    ),
    (
        "What does dry_run_mode do in dialer_config.json?",
        textwrap.dedent(
            """
            Set `"dry_run_mode": true` to exercise the dialer **without placing real calls**.

            The scheduler simulates `DIALING → RINGING → NO_ANSWER` so you can verify queueing, logging, retries, cooldown, and UI updates safely. Keep it `false` for production calling.

            Run `python scripts/dry_run_controller_smoke.py` for a quick headless check.
            """
        ).strip(),
    ),
]


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True).strip()


def gql(query: str, **variables: str) -> dict:
    args = ["api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        args.extend(["-f", f"{k}={v}"])
    raw = gh(*args)
    data = json.loads(raw)
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def create_qa_category() -> str:
    data = gql(
        """
        mutation($repoId: ID!) {
          createDiscussionCategory(input: {
            repositoryId: $repoId,
            name: "Q&A",
            description: "Questions and answers for operators and developers",
            emoji: ":speech_balloon:"
          }) {
            discussionCategory { id name isAnswerable }
          }
        }
        """,
        repoId=get_repo_node_id(),
    )
    cat = data["createDiscussionCategory"]["discussionCategory"]
    print(f"Created category {cat['name']} ({cat['id']})")
    return cat["id"]


def get_qa_category_id() -> str:
    try:
        return _find_qa_category_id()
    except RuntimeError:
        return create_qa_category()


def _find_qa_category_id() -> str:
    data = gql(
        """
        query($owner: String!, $name: String!) {
          repository(owner: $owner, name: $name) {
            discussionCategories(first: 20) { nodes { id name isAnswerable } }
          }
        }
        """,
        owner=OWNER,
        name=DIALER,
    )
    nodes = data["repository"]["discussionCategories"]["nodes"]
    answerable = [n for n in nodes if n.get("isAnswerable")]
    if answerable:
        for node in answerable:
            if "q&a" in node["name"].lower() or "question" in node["name"].lower():
                return node["id"]
        return answerable[0]["id"]
    raise RuntimeError(
        "No answerable discussion category found. "
        "Create a Q&A category in repo Discussions settings."
    )


def create_discussion(category_id: str, title: str, body: str) -> str:
    data = gql(
        """
        mutation($repoId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
          createDiscussion(input: {repositoryId: $repoId, categoryId: $categoryId, title: $title, body: $body}) {
            discussion { id url number }
          }
        }
        """,
        repoId=get_repo_node_id(),
        categoryId=category_id,
        title=title,
        body=body,
    )
    d = data["createDiscussion"]["discussion"]
    print(f"Discussion #{d['number']}: {d['url']}")
    return d["id"]


def get_repo_node_id() -> str:
    data = gql(
        """
        query($owner: String!, $name: String!) {
          repository(owner: $owner, name: $name) { id }
        }
        """,
        owner=OWNER,
        name=DIALER,
    )
    return data["repository"]["id"]


def add_answer(discussion_id: str, body: str) -> str:
    data = gql(
        """
        mutation($discussionId: ID!, $body: String!) {
          addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
            comment { id }
          }
        }
        """,
        discussionId=discussion_id,
        body=body,
    )
    return data["addDiscussionComment"]["comment"]["id"]


def mark_answer(comment_id: str) -> None:
    gql(
        """
        mutation($id: ID!) {
          markDiscussionCommentAsAnswer(input: {id: $id}) {
            discussion { url }
          }
        }
        """,
        id=comment_id,
    )
    print(f"Marked answer: {comment_id}")


def seed_galaxy_brain() -> None:
    cat = get_qa_category_id()
    print(f"Using category {cat}")
    for title, answer in FAQ:
        did = create_discussion(cat, title, f"**Question:** {title}\n\nLooking for the recommended workflow from the maintainers.")
        cid = add_answer(did, answer)
        mark_answer(cid)


ACHIEVEMENTS_SECTION = """
---

## GitHub Achievements & Highlights

<div align="center">

### Achievements

<a href="https://github.com/mafzalkalwardev?tab=achievements" title="Pull Shark">
  <img src="https://github.githubassets.com/images/modules/profile/achievements/pull-shark-bronze.png" width="72" alt="Pull Shark bronze" />
</a>
<a href="https://github.com/mafzalkalwardev?tab=achievements" title="Pair Extraordinaire">
  <img src="https://github.githubassets.com/images/modules/profile/achievements/pair-extraordinaire-bronze.png" width="72" alt="Pair Extraordinaire bronze" />
</a>
<a href="https://github.com/mafzalkalwardev?tab=achievements" title="YOLO">
  <img src="https://github.githubassets.com/images/modules/profile/achievements/yolo-default.png" width="72" alt="YOLO" />
</a>
<a href="https://github.com/mafzalkalwardev?tab=achievements" title="Quickdraw">
  <img src="https://github.githubassets.com/images/modules/profile/achievements/quickdraw-default.png" width="72" alt="Quickdraw" />
</a>
<a href="https://github.com/mafzalkalwardev/indus-transport-auto-dialer/discussions" title="Galaxy Brain">
  <img src="https://github.githubassets.com/images/modules/profile/achievements/galaxy-brain-default.png" width="72" alt="Galaxy Brain" />
</a>

<br/>

[![Achievements](https://img.shields.io/badge/Achievements-View_Profile-2563eb?style=for-the-badge)](https://github.com/mafzalkalwardev?tab=achievements)
[![Pull Shark](https://img.shields.io/badge/Pull_Shark-Bronze-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/mafzalkalwardev?achievement=pull-shark&tab=achievements)
[![Open Source](https://img.shields.io/badge/Open_Source-51_repos-059669?style=for-the-badge&logo=github&logoColor=white)](https://github.com/mafzalkalwardev?tab=repositories)

### Highlights

| Highlight | Status |
|:--|:--|
| **GitHub Pro** | Active |
| **Developer Program Member** | Active |
| **GitHub Campus Expert** | [Apply here](https://education.github.com/experts) if you are a student |
| **Public Sponsor** | [Sponsor any maintainer publicly ($1+)](https://github.com/sponsors) for the badge |
| **Galaxy Brain** | Answer discussions — see [Auto Dialer Q&A](https://github.com/mafzalkalwardev/indus-transport-auto-dialer/discussions) |

</div>

---
"""


def update_profile_readme() -> None:
    meta = json.loads(gh("api", f"repos/{PROFILE}/{PROFILE}/contents/README.md"))
    body = base64.b64decode(meta["content"]).decode()
    sha = meta["sha"]

    marker = "## GitHub Achievements & Highlights"
    if marker in body:
        start = body.index(marker)
        end = body.find("\n---\n", start + len(marker))
        if end == -1:
            end = start
        else:
            end += len("\n---\n")
        body = body[:start] + ACHIEVEMENTS_SECTION.strip() + "\n\n" + body[end:].lstrip("-").lstrip("\n")
    else:
        anchor = "## GitHub Stats"
        if anchor not in body:
            raise RuntimeError("Could not find insertion point in profile README")
        body = body.replace(anchor, ACHIEVEMENTS_SECTION.strip() + "\n\n" + anchor, 1)

    b64 = base64.b64encode(body.encode()).decode()
    subprocess.run(
        [
            "gh", "api", f"repos/{PROFILE}/{PROFILE}/contents/README.md", "-X", "PUT",
            "-f", "message=docs: showcase GitHub achievements and highlights on profile",
            "-f", f"content={b64}",
            "-f", f"sha={sha}",
        ],
        check=True,
    )
    print("Profile README updated.")


def pin_showcase_repos() -> None:
    repos = [
        "indus-transport-auto-dialer",
        "bulk-email-verifier",
        "fiverr-lead-extractor-crm",
        "CallAudit-X",
        "playwright-website-scraper-pro",
        "google-voice-dispatch-agent",
    ]
    ids = []
    for name in repos:
        data = gql(
            """
            query($owner: String!, $name: String!) {
              repository(owner: $owner, name: $name) { id name }
            }
            """,
            owner=OWNER,
            name=name,
        )
        repo = data.get("repository")
        if repo:
            ids.append(repo["id"])
            print(f"Pin candidate: {repo['name']}")
    user = gql("query { viewer { id } }")["viewer"]["id"]
    try:
        gql(
            """
            mutation($repoIds: [ID!]!) {
              updatePinnedItems(input: {repositoryIds: $repoIds}) {
                pinnedItems { ... on Repository { nameWithOwner } }
              }
            }
            """,
            repoIds=ids,
        )
        print(f"Pinned {len(ids)} repositories on profile.")
    except Exception as exc:
        print(f"Pin API unavailable ({exc}). Pin repos manually at github.com/{OWNER}?tab=repositories.")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in {"galaxy", "all"}:
        seed_galaxy_brain()
    if cmd in {"profile", "all"}:
        update_profile_readme()
    if cmd in {"pins", "all"}:
        pin_showcase_repos()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
