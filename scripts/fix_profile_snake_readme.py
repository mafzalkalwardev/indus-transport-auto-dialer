"""Fix snake URLs in profile README."""
import base64
import re
import subprocess

OWNER = "mafzalkalwardev"
REPO = "mafzalkalwardev"

def gh(*args):
    return subprocess.check_output(["gh", *args], text=True).strip()

content_b64 = gh("api", f"repos/{OWNER}/{REPO}/readme", "--jq", ".content")
body = base64.b64decode(content_b64).decode()

body = body.replace(
    "output/snake-dark.svg",
    "output/github-contribution-grid-snake-dark.svg",
)
body = body.replace(
    "output/snake.svg",
    "output/github-contribution-grid-snake.svg",
)

sha = gh("api", f"repos/{OWNER}/{REPO}/contents/README.md", "--jq", ".sha")
b64 = base64.b64encode(body.encode()).decode()
subprocess.run(
    [
        "gh", "api", f"repos/{OWNER}/{REPO}/contents/README.md", "-X", "PUT",
        "-f", "message=fix: correct contribution snake image URLs",
        "-f", f"content={b64}",
        "-f", f"sha={sha}",
    ],
    check=True,
)
print("README updated")
