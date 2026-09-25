#!/usr/bin/env python3
"""
SCSSA Issue Form Provisioner
Provisions a new clean course repository when an administrator applies the `approved` label.
Auto-assigns the next sequential group number PER BATCH for the module.
Repo name format: FSSD-B{YY}-G{NN}-{SHORT-TITLE}  (e.g. FSSD-B24-G01-SMART-BUS)
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# Module code → prefix mapping (must match issue_validate.py)
MODULE_MAP = {
    "COSC 32133 / BECS 32263 – Full-Stack Software Development (FSSD)": "FSSD",
}

# Batch label → batch code mapping (must match issue_validate.py)
BATCH_MAP = {
    "22/23": "B22",
    "23/24": "B23",
    "24/25": "B24",
}


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


def normalize_short_title(raw: str) -> str:
    """Converts short title to title case with hyphens (e.g. 'smart bus' → 'Smart-Bus')."""
    return re.sub(r"[\s-]+", "-", raw.strip()).title()


def get_next_group_number(org: str, module_prefix: str, batch_code: str, token: str) -> int:
    """
    Scans all org repos matching `{MODULE_PREFIX}-{BATCH_CODE}-G*` and returns
    the next sequential group number for that specific batch.
    Uses pagination to handle orgs with many repos.
    """
    # e.g. matches FSSD-B24-G01-SMART-BUS → captures "01"
    group_regex = re.compile(
        rf"^{re.escape(module_prefix)}-{re.escape(batch_code)}-G(\d+)-",
        re.IGNORECASE
    )
    max_group = 0
    page = 1

    while True:
        status, repos = api_request("GET", f"/orgs/{org}/repos?per_page=100&page={page}", token)
        if status != 200 or not isinstance(repos, list) or len(repos) == 0:
            break
        for repo in repos:
            name = repo.get("name", "")
            match = group_regex.match(name)
            if match:
                num = int(match.group(1))
                if num > max_group:
                    max_group = num
        if len(repos) < 100:
            break
        page += 1

    return max_group + 1


def wait_until_repo_ready(org: str, repo: str, token: str, max_retries: int = 5, delay: int = 2) -> bool:
    for attempt in range(1, max_retries + 1):
        status, _ = api_request("GET", f"/repos/{org}/{repo}", token)
        if status == 200:
            return True
        time.sleep(delay)
    return False


def main():
    app_token = os.environ.get("APP_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    issue_token = os.environ.get("ISSUE_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    repo_full_name = os.environ.get("REPO_FULL_NAME", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    issue_author = os.environ.get("ISSUE_AUTHOR", "")
    issue_body = os.environ.get("ISSUE_BODY", "")
    org_name = os.environ.get("ORG_NAME") or (repo_full_name.split("/")[0] if "/" in repo_full_name else "SCSSA-UoK")

    if not app_token or not issue_number or not issue_body:
        print("Error: Missing required environment variables.", file=sys.stderr)
        sys.exit(1)

    actor = os.environ.get("ACTOR", "")
    if actor:
        is_admin = False
        codeowners_path = ".github/CODEOWNERS"
        if os.path.exists(codeowners_path):
            with open(codeowners_path, "r") as f:
                if f"@{actor}" in f.read():
                    is_admin = True
                    
        if not is_admin:
            comment_body = (
                f"### ❌ Approval Denied\n\n"
                f"Sorry @{actor}, only administrators listed in `.github/CODEOWNERS` can approve repository requests."
            )
            api_request("POST", f"/repos/{repo_full_name}/issues/{issue_number}/comments", issue_token, {"body": comment_body})
            api_request("DELETE", f"/repos/{repo_full_name}/issues/{issue_number}/labels/approved", issue_token)
            print(f"Error: @{actor} is not authorized to approve.", file=sys.stderr)
            sys.exit(1)

    form = parse_issue_form(issue_body)
    raw_module = form.get("Module", "").strip()
    raw_batch = form.get("Student Batch", "").strip()
    raw_short_title = form.get("Project Short Title", "").strip()
    description = form.get("Project Description", "Student project repository").strip()
    raw_members = form.get("Team Members (GitHub Usernames)", "").strip()

    # Resolve module prefix
    module_prefix = MODULE_MAP.get(raw_module)
    if not module_prefix:
        print(f"Error: Unrecognised module '{raw_module}'.", file=sys.stderr)
        sys.exit(1)

    # Resolve batch code
    batch_code = BATCH_MAP.get(raw_batch)
    if not batch_code:
        print(f"Error: Unrecognised batch '{raw_batch}'.", file=sys.stderr)
        sys.exit(1)

    # Normalize short title
    if not raw_short_title or raw_short_title.lower() == "_no response_":
        print("Error: No short title found in issue.", file=sys.stderr)
        sys.exit(1)
    short_title = normalize_short_title(raw_short_title)

    # Parse members
    members = []
    if raw_members and raw_members.lower() != "_no response_":
        members = [m.strip().lstrip("@") for m in re.split(r"[,;\s]+", raw_members) if m.strip()]

    # Auto-assign next group number (scoped to this batch)
    print(f"🔢 Calculating next group number for '{module_prefix}-{batch_code}'...")
    group_number = get_next_group_number(org_name, module_prefix, batch_code, app_token)
    repo_name = f"{module_prefix}-{batch_code}-G{group_number:02d}-{short_title}"

    print(f"🚀 Provisioning repository '{org_name}/{repo_name}' for issue #{issue_number}")

    # 1. Idempotency Check
    status, _ = api_request("GET", f"/repos/{org_name}/{repo_name}", app_token)
    if status == 200:
        print(f"Repository '{org_name}/{repo_name}' already exists. Skipping creation.")
    elif status == 404:
        print(f"Creating new repository '{org_name}/{repo_name}'...")
        payload = {
            "name": repo_name,
            "description": description,
            "private": True,
            "auto_init": True,
        }
        status, resp = api_request("POST", f"/orgs/{org_name}/repos", app_token, payload)
        if status not in (200, 201):
            print(f"Failed to create repo: HTTP {status} - {resp}", file=sys.stderr)
            sys.exit(1)

        wait_until_repo_ready(org_name, repo_name, app_token)

    # 2. Assign Project Lead as Admin
    if issue_author:
        print(f"Assigning admin role to @{issue_author}...")
        api_request("PUT", f"/repos/{org_name}/{repo_name}/collaborators/{issue_author}", app_token, {"permission": "admin"})

    # 3. Assign Teammates with Push Permission
    for member in members:
        if member == issue_author:
            continue
        print(f"Adding collaborator @{member} with push access...")
        api_request("PUT", f"/repos/{org_name}/{repo_name}/collaborators/{member}", app_token, {"permission": "push"})

    # 4. Post Celebration Comment on Issue
    new_repo_url = f"https://github.com/{org_name}/{repo_name}"
    members_bullets = "\n".join(f"- @{m}" for m in members) if members else "- None (Individual project)"

    comment_body = (
        f"### 🎉 Repository Provisioned Successfully!\n\n"
        f"The requested repository has been created and configured.\n\n"
        f"| Attribute | Value |\n"
        f"| :--- | :--- |\n"
        f"| **Repository** | [{org_name}/{repo_name}]({new_repo_url}) |\n"
        f"| **Module** | `{raw_module}` |\n"
        f"| **Batch** | `{raw_batch}` (`{batch_code}`) |\n"
        f"| **Group Number** | `Group {group_number:02d}` |\n"
        f"| **Project Lead** | @{issue_author} *(Admin)* |\n"
        f"| **Visibility** | `Private` 🔒 |\n\n"
        f"**Team Members:**\n{members_bullets}\n\n"
        f"> 🚀 **Next Steps:**\n"
        f"> 1. Team members should check their notifications or email to accept collaborator invites.\n"
        f"> 2. Clone the repository:\n"
        f">    ```bash\n"
        f">    git clone {new_repo_url}.git\n"
        f">    ```\n"
        f"> 3. Add your code, commit, and push!\n"
    )
    api_request("POST", f"/repos/{repo_full_name}/issues/{issue_number}/comments", issue_token, {"body": comment_body})

    # 5. Update Labels and Close Issue
    api_request("POST", f"/repos/{repo_full_name}/issues/{issue_number}/labels", issue_token, {"labels": ["provisioned"]})
    api_request("DELETE", f"/repos/{repo_full_name}/issues/{issue_number}/labels/approved", issue_token)
    api_request("DELETE", f"/repos/{repo_full_name}/issues/{issue_number}/labels/pending-approval", issue_token)
    api_request("PATCH", f"/repos/{repo_full_name}/issues/{issue_number}", issue_token, {"state": "closed", "state_reason": "completed"})

    print(f"✨ Provisioning complete: '{org_name}/{repo_name}' (Batch {raw_batch}, Group {group_number:02d})")


if __name__ == "__main__":
    main()
