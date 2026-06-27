#!/usr/bin/env python3
"""Seed additional Galaxy Brain Q&A (bronze tier = 8 accepted answers)."""
from __future__ import annotations

import json
import subprocess
import textwrap

OWNER = "mafzalkalwardev"
DIALER = "indus-transport-auto-dialer"

FAQ = [
    (
        "How do I load an Excel contact list for dialing?",
        textwrap.dedent(
            """
            1. Open the **Dialer** tab after signing in.
            2. Click **Import Excel** and choose your `.xlsx` file (phone column required).
            3. Confirm column mapping if prompted.
            4. Press **Start dialing** — the queue runs from the imported sheet.

            Keep one campaign file per shift; the dialer logs outcomes under `logs/` locally.
            """
        ).strip(),
    ),
    (
        "What should I do if Google Voice stops connecting?",
        textwrap.dedent(
            """
            1. Close the dialer and any orphaned Chrome windows.
            2. Run **Repair Start.bat** (or re-run `Start Auto Dialer.bat`).
            3. In **Settings**, re-verify each Google Voice line profile.
            4. Check that Chrome can open `voice.google.com` in the saved profile.

            If profiles were copied from an admin PC, ensure `chrome_profiles/` and `dialer_config.json` match the export package.
            """
        ).strip(),
    ),
    (
        "Where can I find call logs after a dialing session?",
        textwrap.dedent(
            """
            Call outcomes are written under the `logs/` folder in your install directory.

            Open **Call Logs** in the app for a searchable view, or inspect the raw CSV/JSON files for integration with your CRM workflow.
            """
        ).strip(),
    ),
    (
        "How do I run the dialer in test mode before going live?",
        textwrap.dedent(
            """
            Set `"dry_run_mode": true` in `dialer_config.json`, then run `python scripts/dry_run_controller_smoke.py` for a headless check.

            Dry run simulates ring/no-answer cycles without placing real calls — use it after config changes or on a new PC.
            """
        ).strip(),
    ),
    (
        "What files are included in a client export package?",
        textwrap.dedent(
            """
            A typical admin export includes:

            - `dialer_config.json`
            - `logs/`, `data/`, `chrome_profiles/`
            - Agent credentials created in **Administration → Export client package**

            Copy the folder contents into the agent install directory, then launch with `Start Auto Dialer.bat`.
            """
        ).strip(),
    ),
]


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True).strip()


def gql(query: str, **variables) -> dict:
    args = ["api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        if isinstance(v, int):
            args.extend(["-F", f"{k}={v}"])
        else:
            args.extend(["-f", f"{k}={v}"])
    data = json.loads(gh(*args))
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def repo_id() -> str:
    return gql(
        "query($o:String!,$n:String!){repository(owner:$o,name:$n){id}}",
        o=OWNER,
        n=DIALER,
    )["repository"]["id"]


def qa_category_id() -> str:
    nodes = gql(
        "query($o:String!,$n:String!){repository(owner:$o,name:$n){discussionCategories(first:20){nodes{id name isAnswerable}}}}",
        o=OWNER,
        n=DIALER,
    )["repository"]["discussionCategories"]["nodes"]
    for node in nodes:
        if node.get("isAnswerable") and "q&a" in node["name"].lower():
            return node["id"]
    raise RuntimeError("No Q&A category")


def seed(title: str, answer: str) -> None:
    rid = repo_id()
    cat = qa_category_id()
    d = gql(
        """
        mutation($repoId:ID!,$cat:ID!,$title:String!,$body:String!){
          createDiscussion(input:{repositoryId:$repoId,categoryId:$cat,title:$title,body:$body}){
            discussion{id number url}
          }
        }""",
        repoId=rid,
        cat=cat,
        title=title,
        body=f"**Question:** {title}\n\nWhat is the recommended workflow?",
    )["createDiscussion"]["discussion"]
    cid = gql(
        "mutation($id:ID!,$body:String!){addDiscussionComment(input:{discussionId:$id,body:$body}){comment{id}}}",
        id=d["id"],
        body=answer,
    )["addDiscussionComment"]["comment"]["id"]
    gql(
        "mutation($id:ID!){markDiscussionCommentAsAnswer(input:{id:$id}){discussion{url}}}",
        id=cid,
    )
    print(f"#{d['number']} {d['url']}")


def answer_existing(number: int, answer: str) -> None:
    data = gql(
        """
        query($o:String!,$n:String!,$num:Int!){
          repository(owner:$o,name:$n){
            discussion(number:$num){
              id title
              category { isAnswerable name }
            }
          }
        }""",
        o=OWNER,
        n=DIALER,
        num=number,
    )
    disc = data["repository"]["discussion"]
    if not disc:
        print(f"Skip #{number} — not found")
        return
    if not disc["category"]["isAnswerable"]:
        print(f"Skip #{number} ({disc['category']['name']}) — not answerable")
        return
    cid = gql(
        "mutation($id:ID!,$body:String!){addDiscussionComment(input:{discussionId:$id,body:$body}){comment{id}}}",
        id=disc["id"],
        body=answer,
    )["addDiscussionComment"]["comment"]["id"]
    gql(
        "mutation($id:ID!){markDiscussionCommentAsAnswer(input:{id:$id}){discussion{url}}}",
        id=cid,
    )
    print(f"Answered discussion #{number}: {disc['title']}")


def main() -> None:
    answer_existing(
        45,
        "Use the **admin export package** flow: administrator exports client package from Settings, agent copies `dialer_config.json`, `logs/`, `data/`, and `chrome_profiles/` into the install folder, then runs `Start Auto Dialer.bat`. See `CLIENT.md` for the full checklist.",
    )
    answer_existing(
        57,
        "Flagship repos: **indus-transport-auto-dialer** (PyQt6 dialer), **bulk-email-verifier**, **google-voice-dispatch-agent**, **CallAudit-X**, and **fiverr-lead-extractor-crm**. Full index: https://github.com/mafzalkalwardev/ft-solutions-hub",
    )
    answer_existing(
        8,
        "See `README.md` for install, `CLIENT.md` for agent deployment, and `docs/GITHUB_ACHIEVEMENTS.md` for contributor workflow. Discussions Q&A covers operator FAQs.",
    )
    for title, body in FAQ:
        seed(title, body)
    print("Galaxy Brain batch complete (target: 8+ accepted answers).")


if __name__ == "__main__":
    main()
