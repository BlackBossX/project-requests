#!/usr/bin/env python3
"""
SCSSA Issue Form Provisioner
Provisions a new clean course repository when an administrator applies the `approved` label.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request


def api_request(method: str, endpoint: str, token: str, data: dict = None):
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "scssa-issue-provisioner",
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


def parse_issue_form(body: str) -> dict:
    fields = {}
    current_key = None
    buffer = []

    for line in body.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("### "):
            if current_key and buffer:
                fields[current_key] = "\n".join(buffer).strip()
                buffer = []
            current_key = line_clean[4:].strip()
        elif current_key is not None:
            buffer.append(line)

    if current_key and buffer:
        fields[current_key] = "\n".join(buffer).strip()

    return fields


def wait_until_repo_ready(org: str, repo: str, token: str, max_retries: int = 5, delay: int = 2) -> bool:
    for attempt in range(1, max_retries + 1):
        status, _ = api_request("GET", f"/repos/{org}/{repo}", token)
        if status == 200:
            return True
        time.sleep(delay)
    return False


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    repo_full_name = os.environ.get("REPO_FULL_NAME", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    issue_author = os.environ.get("ISSUE_AUTHOR", "")
    issue_body = os.environ.get("ISSUE_BODY", "")
    org_name = os.environ.get("ORG_NAME") or (repo_full_name.split("/")[0] if "/" in repo_full_name else "SCSSA-UoK")

    if not token or not issue_number or not issue_body:
        print("Error: Missing required environment variables.", file=sys.stderr)
        sys.exit(1)

    form = parse_issue_form(issue_body)
    repo_name = form.get("Repository Name", "").strip()
    description = form.get("Project Description", "Student project repository").strip()
    raw_members = form.get("Team Members (GitHub Usernames)", "").strip()
    visibility = form.get("Repository Visibility", "private").strip().lower()

    if "private" in visibility:
        visibility = "private"
    elif "public" in visibility:
        visibility = "public"

    members = []
    if raw_members and raw_members.lower() != "_no response_":
        members = [m.strip().lstrip("@") for m in re.split(r"[,;\s]+", raw_members) if m.strip()]

    if not repo_name:
        print("Error: No repository name found in issue.", file=sys.stderr)
        sys.exit(1)

    print(f"🚀 Provisioning repository '{org_name}/{repo_name}' for issue #{issue_number}")

    # 1. Idempotency Check
    status, _ = api_request("GET", f"/repos/{org_name}/{repo_name}", token)
    if status == 200:
        print(f"Repository '{org_name}/{repo_name}' already exists. Skipping creation.")
    elif status == 404:
        print(f"Creating new clean repository '{org_name}/{repo_name}'...")
        payload = {
            "name": repo_name,
            "description": description,
            "private": (visibility == "private"),
            "auto_init": True,
        }
        status, resp = api_request("POST", f"/orgs/{org_name}/repos", token, payload)
        if status not in (200, 201):
            print(f"Failed to create repo: HTTP {status} - {resp}", file=sys.stderr)
            sys.exit(1)

        wait_until_repo_ready(org_name, repo_name, token)

    # 2. Assign Project Lead as Admin
    if issue_author:
        print(f"Assigning admin role to @{issue_author}...")
        api_request("PUT", f"/repos/{org_name}/{repo_name}/collaborators/{issue_author}", token, {"permission": "admin"})

    # 3. Assign Teammates with Push Permission
    for member in members:
        if member == issue_author:
            continue
        print(f"Adding collaborator @{member} with push access...")
        api_request("PUT", f"/repos/{org_name}/{repo_name}/collaborators/{member}", token, {"permission": "push"})

    # 4. Post Celebration Comment on Issue
    new_repo_url = f"https://github.com/{org_name}/{repo_name}"
    members_bullets = "\n".join(f"- @{m}" for m in members) if members else "- None (Individual project)"

    comment_body = (
        f"### 🎉 Repository Provisioned Successfully!\n\n"
        f"The requested repository has been created and configured.\n\n"
        f"| Attribute | Value |\n"
        f"| :--- | :--- |\n"
        f"| **Repository** | [{org_name}/{repo_name}]({new_repo_url}) |\n"
        f"| **Project Lead** | @{issue_author} *(Admin)* |\n"
        f"| **Visibility** | `{visibility.capitalize()}` 🔒 |\n\n"
        f"**Team Members:**\n{members_bullets}\n\n"
        f"> 🚀 **Next Steps:**\n"
        f"> 1. Team members should check their notifications or email to accept collaborator invites.\n"
        f"> 2. Clone the repository:\n"
        f">    ```bash\n"
        f">    git clone {new_repo_url}.git\n"
        f">    ```\n"
        f"> 3. Add your code, commit, and push!\n"
    )
    api_request("POST", f"/repos/{repo_full_name}/issues/{issue_number}/comments", token, {"body": comment_body})

    # 5. Update Labels and Close Issue
    api_request("POST", f"/repos/{repo_full_name}/issues/{issue_number}/labels", token, {"labels": ["provisioned"]})
    api_request("DELETE", f"/repos/{repo_full_name}/issues/{issue_number}/labels/approved", token)
    api_request("DELETE", f"/repos/{repo_full_name}/issues/{issue_number}/labels/pending-approval", token)
    api_request("PATCH", f"/repos/{repo_full_name}/issues/{issue_number}", token, {"state": "closed", "state_reason": "completed"})

    print("✨ Provisioning and issue lifecycle completed successfully.")


if __name__ == "__main__":
    main()
