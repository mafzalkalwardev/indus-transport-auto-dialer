"""Scan all repos for failed workflow runs."""
import json
import subprocess
import time

OWNER = "mafzalkalwardev"


def gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def main():
    _, out, _ = gh("repo", "list", OWNER, "--limit", "100", "--json", "name,isFork")
    repos = [r["name"] for r in json.loads(out) if not r.get("isFork")]
    failures = []
    for repo in repos:
        code, out, err = gh(
            "run", "list", "--repo", f"{OWNER}/{repo}", "--limit", "5",
            "--json", "databaseId,conclusion,status,name,workflowName,url,headBranch,event",
        )
        if code != 0:
            continue
        runs = json.loads(out) if out else []
        for run in runs:
            if run.get("conclusion") == "failure":
                failures.append({**run, "repo": repo})
        time.sleep(0.15)
    print(json.dumps(failures, indent=2))
    print(f"\nTOTAL_FAILURES={len(failures)}", flush=True)


if __name__ == "__main__":
    main()
