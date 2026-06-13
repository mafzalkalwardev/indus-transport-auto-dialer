"""
Professionalize all GitHub repositories: badges, descriptions, topics,
snake workflow, screenshot placeholders, and initial releases.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

OWNER = "mafzalkalwardev"
ROOT = Path(__file__).resolve().parent.parent

# Repo-specific metadata (override auto-generated defaults)
REPO_OVERRIDES: dict[str, dict] = {
    "indus-transport-auto-dialer": {
        "emoji": "📞",
        "title": "Indus Transport Auto Dialer",
        "tagline": "Professional Windows auto dialer — Google Voice, AMD, predictive pacing.",
        "features": "Multi-line dialing · AMD · CRM · Excel lists",
        "badges": [
            ("Python", "3.10+", "3776AB", "python", "https://www.python.org/"),
            ("Platform", "Windows", "0078D4", None, None),
            ("PyQt6", "GUI", "41CD52", None, None),
            ("License", "MIT", "yellow", None, "LICENSE"),
            ("PRs", "welcome", "brightgreen", None, "CONTRIBUTING.md"),
        ],
        "topics": ["python", "pyqt6", "auto-dialer", "google-voice", "telephony", "amd"],
        "description": "Windows desktop auto dialer for Indus Transports LLC using Google Voice, AMD fusion, CRM, and predictive pacing.",
    },
    "bulk-email-verifier": {
        "skip_readme": True,
        "emoji": "📧",
        "title": "Bulk Email Verifier",
        "tagline": "Self-hosted bulk email verification — free forever. No paid APIs.",
        "features": "Syntax · MX records · live SMTP dialog · CSV export",
        "topics": ["email-verification", "smtp", "nodejs", "go", "self-hosted"],
    },
    "mailforge": {
        "skip_readme": True,
        "emoji": "✉️",
        "title": "MailForge",
        "tagline": "Email tooling and automation by FT Solutions.",
        "features": "SMTP · Templates · Automation",
    },
    "python-auto-dialer-pro": {
        "emoji": "📞",
        "title": "Python Auto Dialer Pro",
        "tagline": "PyQt desktop auto dialer with Excel contacts and PyAutoGUI automation.",
        "features": "Excel import · Hotkeys · CSV logs · Resume support",
        "badges": [
            ("Python", "3.10+", "3776AB", "python", "https://www.python.org/"),
            ("License", "MIT", "yellow", None, "LICENSE"),
            ("PRs", "welcome", "brightgreen", None, "CONTRIBUTING.md"),
        ],
    },
    "google-voice-dispatch-agent": {
        "emoji": "🤖",
        "title": "Google Voice Dispatch Agent",
        "tagline": "Selenium GV sales agent with Groq scripts and local TTS.",
        "features": "Google Voice · Groq AI · Voicemail · Low cost",
        "badges": [
            ("Python", "3.10+", "3776AB", "python", "https://www.python.org/"),
            ("License", "MIT", "yellow", None, "LICENSE"),
        ],
    },
    "CallAudit-X": {
        "emoji": "📊",
        "title": "CallAudit X",
        "tagline": "AI-powered call auditing, transcription, scoring, and analytics.",
        "features": "Transcription · Scoring · Analytics · SaaS",
    },
    "mafzalkalwardev": {
        "emoji": "👋",
        "title": "Muhammad Afzal",
        "tagline": "Developer · FT Solutions · Transport & automation tools.",
        "features": "Open source · Python · Node.js · Automation",
        "profile": True,
    },
}

SKIP_REPOS = set()

SNAKE_WORKFLOW = """name: Contribution Snake

on:
  schedule:
    - cron: "0 3 * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Platane/snk@v3
        id: snake
        with:
          github_user_name: {owner}
          outputs: |
            dist/snake.svg
            dist/snake-dark.svg?palette=github-dark
      - uses: peaceiris/actions-gh-pages@v4
        if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/master'
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./dist
          destination_dir: output
          keep_files: true
"""

SCREENSHOT_PLACEHOLDER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450">
  <rect width="800" height="450" fill="#0d1117"/>
  <rect x="40" y="40" width="720" height="370" rx="12" fill="#161b22" stroke="#30363d" stroke-width="2"/>
  <text x="400" y="210" fill="#8b949e" font-family="Segoe UI, Arial, sans-serif" font-size="28" text-anchor="middle">Screenshot</text>
  <text x="400" y="250" fill="#58a6ff" font-family="Segoe UI, Arial, sans-serif" font-size="18" text-anchor="middle">{repo}</text>
  <text x="400" y="290" fill="#6e7681" font-family="Segoe UI, Arial, sans-serif" font-size="14" text-anchor="middle">Replace with app screenshot in docs/screenshots/</text>
</svg>
"""

DOCS_SCREENSHOTS_README = """# Screenshots

Add PNG or JPG captures of the application here, then update the main README:

```markdown
## Screenshots

![App screenshot](docs/screenshots/app.png)
```

Recommended: 1280×720 or 800×450, dark/light as appropriate.
"""


def gh(*args: str, check: bool = True) -> str:
    cmd = ["gh"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"gh failed: {cmd}")
    return result.stdout.strip()


def gh_json(*args: str) -> object:
    out = gh(*args)
    return json.loads(out) if out else {}


def title_from_name(name: str) -> str:
    special = {
        "crm": "CRM",
        "api": "API",
        "smtp": "SMTP",
        "mc": "MC",
        "fmcsa": "FMCSA",
        "dat": "DAT",
        "ui": "UI",
        "xlsx": "XLSX",
    }
    parts = name.replace("_", "-").split("-")
    words = []
    for p in parts:
        low = p.lower()
        words.append(special.get(low, p.capitalize()))
    return " ".join(words)


def badge(label: str, message: str, color: str, logo: str | None = None, link: str | None = None) -> str:
    logo_part = f"&logo={logo}&logoColor=white" if logo else ""
    url = f"https://img.shields.io/badge/{label}-{message.replace(' ', '%20')}-{color}?style=for-the-badge{logo_part}"
    img = f"![{label}]({url})"
    return f"[{img}]({link})" if link else img


def language_badges(lang: str | None) -> list[tuple]:
    if not lang:
        return [("License", "MIT", "yellow", None, "LICENSE"), ("PRs", "welcome", "brightgreen", None, "CONTRIBUTING.md")]
    mapping = {
        "Python": ("Python", "3.10+", "3776AB", "python", "https://www.python.org/"),
        "JavaScript": ("Node.js", "18+", "339933", "node.js", "https://nodejs.org/"),
        "TypeScript": ("TypeScript", "5+", "3178C6", "typescript", "https://www.typescriptlang.org/"),
        "Go": ("Go", "1.22+", "00ADD8", "go", "https://go.dev/"),
        "HTML": ("HTML5", "Web", "E34F26", "html5", None),
        "C#": (".NET", "8", "512BD4", "dotnet", None),
        "Java": ("Java", "17+", "007396", "openjdk", None),
    }
    primary = mapping.get(lang, (lang, "Latest", "555555", None, None))
    badges = [primary, ("License", "MIT", "yellow", None, "LICENSE"), ("PRs", "welcome", "brightgreen", None, "CONTRIBUTING.md")]
    return badges


def build_header(meta: dict, repo: str) -> str:
    emoji = meta.get("emoji", "🚀")
    title = meta.get("title", title_from_name(repo))
    tagline = meta.get("tagline", meta.get("description", f"Professional {title} project by FT Solutions."))
    features = meta.get("features", "Open source · Well documented · MIT licensed")
    badges = meta.get("badges") or language_badges(meta.get("primary_language"))
    badge_lines = "\n".join(badge(b[0], b[1], b[2], b[3] if len(b) > 3 else None, b[4] if len(b) > 4 else None) for b in badges)
    nav = meta.get("nav", "[Features](#-features) · [Quick Start](#-quick-start) · [Screenshots](#-screenshots) · [Contributing](CONTRIBUTING.md)")
    snake = ""
    if meta.get("profile"):
        snake = f"""
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/{OWNER}/{OWNER}/output/snake-dark.svg" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/{OWNER}/{OWNER}/output/snake.svg" />
  <img alt="Contribution snake" src="https://raw.githubusercontent.com/{OWNER}/{OWNER}/output/snake.svg" />
</picture>
"""
    else:
        snake = f"""
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/{OWNER}/{repo}/output/snake-dark.svg" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/{OWNER}/{repo}/output/snake.svg" />
  <img alt="Contribution snake" src="https://raw.githubusercontent.com/{OWNER}/{repo}/output/snake.svg" />
</picture>
"""
    return f"""<div align="center">

# {emoji} {title}

**{tagline}**

{features}

{badge_lines}

{nav}

</div>

---

## 🖼 Screenshots

![{title} screenshot](docs/screenshots/placeholder.svg)

*Replace `docs/screenshots/placeholder.svg` with real app screenshots.*

---

## 🐍 Contribution graph

{snake}

---
"""


def repo_meta(repo: dict) -> dict:
    name = repo["name"]
    if name in REPO_OVERRIDES:
        meta = dict(REPO_OVERRIDES[name])
    else:
        desc = repo.get("description") or ""
        meta = {
            "emoji": "🚀",
            "title": title_from_name(name),
            "tagline": desc or f"{title_from_name(name)} — professional open source project.",
            "features": "Documented · MIT licensed · Maintained",
        }
    lang = repo.get("primaryLanguage") or {}
    if lang:
        meta.setdefault("primary_language", lang.get("name"))
    meta.setdefault("title", title_from_name(name))
    if not meta.get("description"):
        meta["description"] = meta.get("tagline", meta["title"])
    return meta


def file_exists(owner: str, repo: str, path: str) -> bool:
    try:
        gh("api", f"repos/{owner}/{repo}/contents/{path}", "--jq", ".name", check=True)
        return True
    except RuntimeError:
        return False


def get_file(owner: str, repo: str, path: str) -> tuple[str, str] | None:
    try:
        data = gh_json("api", f"repos/{owner}/{repo}/contents/{path}")
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]
    except RuntimeError:
        return None


def put_file(owner: str, repo: str, path: str, content: str, message: str, sha: str | None = None) -> None:
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    args = [
        "api", f"repos/{owner}/{repo}/contents/{path}", "-X", "PUT",
        "-f", f"message={message}",
        "-f", f"content={b64}",
    ]
    if sha:
        args.extend(["-f", f"sha={sha}"])
    gh(*args)


def ensure_file(owner: str, repo: str, path: str, content: str, message: str) -> None:
    existing = get_file(owner, repo, path)
    if existing:
        if existing[0] == content:
            print(f"  skip {path} (unchanged)")
            return
        put_file(owner, repo, path, content, message, sha=existing[1])
    else:
        put_file(owner, repo, path, content, message)
    print(f"  updated {path}")


def has_professional_header(readme: str) -> bool:
    return "style=for-the-badge" in readme and "<div align=\"center\">" in readme


def upgrade_readme(owner: str, repo: str, meta: dict) -> None:
    if meta.get("skip_readme"):
        print(f"  skip README (marked skip)")
        return
    header = build_header(meta, repo)
    existing = get_file(owner, repo, "README.md")
    if existing:
        body, sha = existing
        if has_professional_header(body):
            print(f"  skip README (already professional)")
            return
        # Strip leading # title if present
        body = re.sub(r"^#\s+.+\n+", "", body.lstrip(), count=1)
        new_content = header + "\n" + body.lstrip()
        put_file(owner, repo, "README.md", new_content, "docs: add professional README header and badges", sha=sha)
        print(f"  upgraded README.md")
    else:
        content = header + f"\n## 🚀 Quick start\n\nClone the repository and follow project-specific setup in docs.\n"
        put_file(owner, repo, "README.md", content, "docs: add professional README")
        print(f"  created README.md")


def ensure_description(owner: str, repo: str, meta: dict) -> None:
    desc = meta.get("description", "")
    if not desc:
        return
    current = gh("repo", "view", f"{owner}/{repo}", "--json", "description", "--jq", ".description")
    if current and current.strip():
        return
    gh("repo", "edit", f"{owner}/{repo}", "--description", desc)
    print(f"  set description")


def ensure_topics(owner: str, repo: str, meta: dict, lang: str | None) -> None:
    topics = list(meta.get("topics") or [])
    if lang:
        lang_topic = lang.lower().replace(" ", "-").replace("#", "sharp")
        if lang_topic == "c#":
            lang_topic = "csharp"
        if lang_topic not in topics:
            topics.append(lang_topic)
    for t in ("mit", "ft-solutions"):
        if t not in topics:
            topics.append(t)
    if not topics:
        return
    topic_args = []
    for t in topics[:10]:
        topic_args.extend(["--add-topic", t])
    gh("repo", "edit", f"{owner}/{repo}", *topic_args)
    print(f"  topics: {', '.join(topics[:10])}")


def ensure_snake_workflow(owner: str, repo: str) -> None:
    path = ".github/workflows/snake.yml"
    content = SNAKE_WORKFLOW.format(owner=OWNER)
    if file_exists(owner, repo, path):
        print(f"  skip snake workflow")
        return
    put_file(owner, repo, path, content, "ci: add contribution snake workflow")
    print(f"  added snake workflow")


def ensure_screenshots(owner: str, repo: str) -> None:
    svg = SCREENSHOT_PLACEHOLDER_SVG.format(repo=repo)
    ensure_file(owner, repo, "docs/screenshots/placeholder.svg", svg, "docs: add screenshot placeholder")
    ensure_file(owner, repo, "docs/screenshots/README.md", DOCS_SCREENSHOTS_README, "docs: add screenshots guide")


def ensure_release(owner: str, repo: str) -> None:
    try:
        gh("release", "view", "--repo", f"{owner}/{repo}", check=True)
        print(f"  skip release (exists)")
    except RuntimeError:
        notes = f"Initial professional release for {repo}.\n\nIncludes LICENSE, contributing guidelines, and documentation standards."
        gh(
            "release", "create", "v1.0.0",
            "--repo", f"{owner}/{repo}",
            "--title", "v1.0.0 — Initial release",
            "--notes", notes,
        )
        print(f"  created release v1.0.0")


def process_repo(repo: dict) -> None:
    name = repo["name"]
    if name in SKIP_REPOS:
        return
    print(f"\n=== {OWNER}/{name} ===")
    meta = repo_meta(repo)
    lang = (repo.get("primaryLanguage") or {}).get("name")
    try:
        ensure_description(OWNER, name, meta)
        ensure_topics(OWNER, name, meta, lang)
        ensure_snake_workflow(OWNER, name)
        ensure_screenshots(OWNER, name)
        upgrade_readme(OWNER, name, meta)
        ensure_release(OWNER, name)
    except Exception as exc:
        print(f"  ERROR: {exc}")


def main() -> int:
    repos = gh_json("repo", "list", OWNER, "--limit", "100", "--json", "name,description,primaryLanguage,isFork")
    if not isinstance(repos, list):
        print("No repos found", file=sys.stderr)
        return 1
    repos = [r for r in repos if not r.get("isFork")]
    print(f"Processing {len(repos)} repositories...")
    for repo in repos:
        process_repo(repo)
        time.sleep(0.5)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
