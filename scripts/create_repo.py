#!/usr/bin/env python3
"""
SCSSA Project Repository Provisioner
Creates repositories from template upon PR merge, assigns admin and collaborator roles,
and sends notifications back to students on the merged PR.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import yaml


def api_request(method: str, endpoint: str, token: str, data: dict = None):
    """Executes an authenticated HTTP request to GitHub REST API."""
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "scssa-repo-provisioner",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data else None
    if body:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            parsed = json.loads(error_body)
        except Exception:
            parsed = {"message": error_body}
        return e.code, parsed
    except Exception as e:
        return 500, {"message": str(e)}


def wait_until_repo_ready(org: str, repo: str, token: str, max_retries: int = 5, delay: int = 2) -> bool:
    """Waits for GitHub to complete asynchronous repository creation from template."""
    for attempt in range(1, max_retries + 1):
        status, _ = api_request("GET", f"/repos/{org}/{repo}", token)
        if status == 200:
            print(f"  ✓ Repository '{org}/{repo}' is ready (attempt {attempt}).")
            return True
        print(f"  ... waiting for repository to initialize ({attempt}/{max_retries})...")
        time.sleep(delay)
    return False


def get_changed_request_files(commit_sha: str) -> list:
    """Extracts new or modified YAML files in requests/ from the merge commit."""
    diff_targets = [
        ["git", "diff", "--name-status", f"{commit_sha}^1", commit_sha],
        ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", commit_sha],
    ]
    for cmd in diff_targets:
        try:
            out = subprocess.check_output(cmd, text=True).strip()
            if out:
                files = []
                for line in out.splitlines():
                    parts = line.split(maxsplit=1)
                    if len(parts) == 2 and parts[0] in ("A", "M"):
                        p = parts[1]
                        if p.startswith("requests/") and (p.endswith(".yml") or p.endswith(".yaml")):
                            files.append(p)
                if files:
                    return list(set(files))
        except subprocess.CalledProcessError:
            continue

    # Fallback to local files if diff could not resolve
    if os.path.isdir("requests"):
        return [
            os.path.join("requests", f)
            for f in os.listdir("requests")
            if f.endswith(".yml") or f.endswith(".yaml")
        ]
    return []


def get_associated_pr(repo_full_name: str, commit_sha: str, token: str):
    """Finds the pull request associated with the merge commit."""
    status, pulls = api_request("GET", f"/repos/{repo_full_name}/commits/{commit_sha}/pulls", token)
    if status == 200 and isinstance(pulls, list) and len(pulls) > 0:
        pr = pulls[0]
        return pr.get("number"), pr.get("user", {}).get("login")
    return None, None


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    commit_sha = os.environ.get("COMMIT_SHA", "HEAD")
    repo_full_name = os.environ.get("REPO_FULL_NAME", "")
    org_name = os.environ.get("ORG_NAME") or (repo_full_name.split("/")[0] if "/" in repo_full_name else "SCSSA-UoK")
    template_repo = os.environ.get("TEMPLATE_REPO", "project-template")

    if not token:
        print("❌ Error: GITHUB_TOKEN environment variable is missing.", file=sys.stderr)
        sys.exit(1)

    print(f"🚀 Initializing provisioning for organization: '{org_name}'")

    request_files = get_changed_request_files(commit_sha)
    if not request_files:
        print("ℹ️ No new request files found in this commit. Exiting.")
        return

    pr_number, pr_author = get_associated_pr(repo_full_name, commit_sha, token)
    print(f"📌 Associated Pull Request: #{pr_number} by @{pr_author}")

    for file_path in request_files:
        if not os.path.exists(file_path):
            continue

        print(f"\n📂 Processing request: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
            except Exception as e:
                print(f"Failed to read {file_path}: {e}", file=sys.stderr)
                continue

        repo_name = data.get("repo")
        description = data.get("description", "Student project repository")
        visibility = str(data.get("visibility", "private")).lower()
        members = data.get("members", [])

        if not repo_name:
            print("⚠️ Skipped: Missing `repo` field.")
            continue

        # 1. Idempotency Check
        status, _ = api_request("GET", f"/repos/{org_name}/{repo_name}", token)
        if status == 200:
            print(f"ℹ️ Repository '{org_name}/{repo_name}' already exists. Skipping creation.")
        elif status == 404:
            print(f"🔨 Creating new clean repository '{org_name}/{repo_name}'...")
            create_endpoint = f"/orgs/{org_name}/repos"
            payload = {
                "name": repo_name,
                "description": description,
                "private": (visibility == "private"),
                "auto_init": True,
            }
            status, resp = api_request("POST", create_endpoint, token, payload)
            if status not in (200, 201):
                print(f"❌ Failed to create repository: HTTP {status} - {resp}", file=sys.stderr)
                continue

            wait_until_repo_ready(org_name, repo_name, token)

        # 2. Grant Admin rights to PR Author
        lead_user = pr_author or (members[0] if members else None)
        if lead_user:
            print(f"👑 Granting admin role to @{lead_user}...")
            api_request("PUT", f"/repos/{org_name}/{repo_name}/collaborators/{lead_user}", token, {"permission": "admin"})

        # 3. Add Teammates with write/push rights
        for member in members:
            if member == lead_user:
                continue
            print(f"🤝 Adding collaborator @{member} with push permission...")
            api_request("PUT", f"/repos/{org_name}/{repo_name}/collaborators/{member}", token, {"permission": "push"})

        # 4. Post celebration & onboarding comment to the PR
        new_repo_url = f"https://github.com/{org_name}/{repo_name}"
        if pr_number:
            members_bullets = "\n".join(f"- @{m}" for m in members)
            comment_body = (
                f"### 🎉 Repository Provisioned Successfully!\n\n"
                f"Your new clean repository is ready for your project.\n\n"
                f"| Attribute | Value |\n"
                f"| :--- | :--- |\n"
                f"| **Repository** | [{org_name}/{repo_name}]({new_repo_url}) |\n"
                f"| **Project Lead** | @{lead_user} *(Admin)* |\n"
                f"| **Visibility** | `{visibility.capitalize()}` 🔒 |\n\n"
                f"**Team Members:**\n{members_bullets}\n\n"
                f"> 🚀 **Next Steps:**\n"
                f"> 1. Team members should check their notifications or email to accept collaborator invites.\n"
                f"> 2. Clone the repository:\n"
                f">    ```bash\n"
                f">    git clone {new_repo_url}.git\n"
                f">    ```\n"
                f"> 3. Add your project code, commit, and push!\n"
            )
            api_request("POST", f"/repos/{repo_full_name}/issues/{pr_number}/comments", token, {"body": comment_body})

    print("✨ Provisioning completed successfully.")


if __name__ == "__main__":
    main()
