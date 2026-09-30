#!/usr/bin/env python3
"""
SCSSA Issue Form Provisioner
Provisions a new clean course repository when an administrator applies the `approved` label.
Auto-assigns the next sequential group number PER BATCH for the module.
Repo name format: FSSD-B{YY}-G{NN}-{SHORT-TITLE}  (e.g. FSSD-B24-G01-Smart-Bus)
After provisioning, appends a record to requests/projects.csv in this repository.
"""

import base64
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# Module code -> prefix mapping (must match issue_validate.py)
MODULE_MAP = {
    "COSC 32133 / BECS 32263 \u2013 Full-Stack Software Development (FSSD)": "FSSD",
}

# Batch label -> batch code mapping (must match issue_validate.py)
BATCH_MAP = {
    "22/23": "B22",
    "23/24": "B23",
    "24/25": "B24",
}

CSV_PATH = "requests/projects.csv"
CSV_HEADERS = [
    "Group No",
    "Repo Name",
    "Repo Link",
    "Project Title",
    "Module",
    "Batch",
    "Member1 Student No",
    "Member1 Name",
    "Member1 GitHub",
    "Member2 Student No",
    "Member2 Name",
    "Member2 GitHub",
    "Member3 Student No",
    "Member3 Name",
    "Member3 GitHub",
    "Member4 Student No",
    "Member4 Name",
    "Member4 GitHub",
]


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


def is_blank(value: str) -> bool:
    return not value or value.lower() == "_no response_"


def normalize_short_title(raw: str) -> str:
    """Converts short title to title case with hyphens (e.g. 'smart bus' -> 'Smart-Bus')."""
    return re.sub(r"[\s-]+", "-", raw.strip()).title()


def parse_members(form: dict) -> list:
    """
    Extracts up to 4 structured member entries from the issue form.
    Each entry is a dict with keys: index, student_no, name, github.
    """
    members = []
    for i in range(1, 5):
        student_no = form.get(f"Member {i} \u2013 Student No", "").strip()
        name = form.get(f"Member {i} \u2013 Full Name", "").strip()
        github = form.get(f"Member {i} \u2013 GitHub Username", "").strip().lstrip("@")

        if is_blank(student_no) and is_blank(name) and is_blank(github):
            continue

        members.append({
            "index": i,
            "student_no": "" if is_blank(student_no) else student_no,
            "name": "" if is_blank(name) else name,
            "github": "" if is_blank(github) else github,
        })
    return members


def get_next_group_number(org: str, module_prefix: str, batch_code: str, token: str) -> int:
    """
    Scans all org repos matching `{MODULE_PREFIX}-{BATCH_CODE}-G*` and returns
    the next sequential group number for that specific batch.
    Uses pagination to handle orgs with many repos.
    """
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


def update_csv(repo_full_name: str, token: str, row: dict):
    """
    Fetches the existing CSV from this repo (requests/projects.csv),
    appends the new row, and commits it back.
    Creates the file with headers if it does not yet exist.
    """
    endpoint = f"/repos/{repo_full_name}/contents/{CSV_PATH}"
    status, resp = api_request("GET", endpoint, token)

    if status == 200:
        # Decode existing content
        existing_content = base64.b64decode(resp["content"].replace("\n", "")).decode("utf-8")
        file_sha = resp["sha"]
    elif status == 404:
        existing_content = ""
        file_sha = None
    else:
        print(f"Warning: Could not fetch CSV ({status}): {resp}. Skipping CSV update.", file=sys.stderr)
        return

    # Build new CSV content
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, lineterminator="\n")

    if not existing_content.strip():
        writer.writeheader()
        existing_rows = []
    else:
        reader = csv.DictReader(io.StringIO(existing_content))
        existing_rows = list(reader)
        # Write header + existing rows
        writer.writeheader()
        for r in existing_rows:
            writer.writerow({h: r.get(h, "") for h in CSV_HEADERS})

    writer.writerow(row)
    new_content = output.getvalue()
    encoded = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")

    commit_data = {
        "message": f"chore: add group {row['Group No']} to projects.csv [skip ci]",
        "content": encoded,
    }
    if file_sha:
        commit_data["sha"] = file_sha

    put_status, put_resp = api_request("PUT", endpoint, token, commit_data)
    if put_status in (200, 201):
        print(f"CSV updated successfully: {CSV_PATH}")
    else:
        print(f"Warning: Failed to update CSV ({put_status}): {put_resp}", file=sys.stderr)


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
                f"### \u274c Approval Denied\n\n"
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

    # Parse structured members
    members = parse_members(form)
    if not members:
        print("Error: No team members found in issue.", file=sys.stderr)
        sys.exit(1)

    lead = members[0]
    # The project lead GitHub username drives the admin assignment
    lead_github = lead["github"] or issue_author

    # Auto-assign next group number (scoped to this batch)
    print(f"Calculating next group number for '{module_prefix}-{batch_code}'...")
    group_number = get_next_group_number(org_name, module_prefix, batch_code, app_token)
    repo_name = f"{module_prefix}-{batch_code}-G{group_number:02d}-{short_title}"

    print(f"Provisioning repository '{org_name}/{repo_name}' for issue #{issue_number}")

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
    print(f"Assigning admin role to @{lead_github}...")
    api_request("PUT", f"/repos/{org_name}/{repo_name}/collaborators/{lead_github}", app_token, {"permission": "admin"})

    # 3. Assign Teammates with Push Permission
    for m in members[1:]:
        if m["github"] and m["github"] != lead_github:
            print(f"Adding collaborator @{m['github']} with push access...")
            api_request("PUT", f"/repos/{org_name}/{repo_name}/collaborators/{m['github']}", app_token, {"permission": "push"})

    # 4. Post Celebration Comment on Issue
    new_repo_url = f"https://github.com/{org_name}/{repo_name}"

    members_table_rows = ""
    for m in members:
        role = "Admin (Lead)" if m["index"] == 1 else "Collaborator"
        members_table_rows += f"| `{m['student_no']}` | {m['name']} | @{m['github']} | {role} |\n"

    comment_body = (
        f"### \U0001f389 Repository Provisioned Successfully!\n\n"
        f"The requested repository has been created and configured.\n\n"
        f"| Attribute | Value |\n"
        f"| :--- | :--- |\n"
        f"| **Repository** | [{org_name}/{repo_name}]({new_repo_url}) |\n"
        f"| **Module** | `{raw_module}` |\n"
        f"| **Batch** | `{raw_batch}` (`{batch_code}`) |\n"
        f"| **Group Number** | `Group {group_number:02d}` |\n"
        f"| **Project Lead** | @{lead_github} *(Admin)* |\n"
        f"| **Visibility** | `Private` \U0001f512 |\n\n"
        f"**Team Members:**\n\n"
        f"| Student No | Name | GitHub | Role |\n"
        f"| :--- | :--- | :--- | :--- |\n"
        f"{members_table_rows}\n"
        f"> \U0001f680 **Next Steps:**\n"
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

    # 6. Append to projects CSV in this repo
    # Pad members list to always have 4 slots for consistent CSV columns
    padded = members + [{"student_no": "", "name": "", "github": ""}] * (4 - len(members))
    csv_row = {
        "Group No": f"G{group_number:02d}",
        "Repo Name": repo_name,
        "Repo Link": new_repo_url,
        "Project Title": raw_short_title,
        "Module": module_prefix,
        "Batch": batch_code,
        "Member1 Student No": padded[0].get("student_no", ""),
        "Member1 Name": padded[0].get("name", ""),
        "Member1 GitHub": padded[0].get("github", ""),
        "Member2 Student No": padded[1].get("student_no", ""),
        "Member2 Name": padded[1].get("name", ""),
        "Member2 GitHub": padded[1].get("github", ""),
        "Member3 Student No": padded[2].get("student_no", ""),
        "Member3 Name": padded[2].get("name", ""),
        "Member3 GitHub": padded[2].get("github", ""),
        "Member4 Student No": padded[3].get("student_no", ""),
        "Member4 Name": padded[3].get("name", ""),
        "Member4 GitHub": padded[3].get("github", ""),
    }
    print(f"Updating CSV record at '{CSV_PATH}'...")
    update_csv(repo_full_name, issue_token, csv_row)

    print(f"\u2728 Provisioning complete: '{org_name}/{repo_name}' (Batch {raw_batch}, Group {group_number:02d})")


if __name__ == "__main__":
    main()
