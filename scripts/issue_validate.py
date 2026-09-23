#!/usr/bin/env python3
"""
SCSSA Issue Form Request Validator
Validates student repository requests submitted via GitHub Issue Forms.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

REPO_REGEX = re.compile(r"^e[0-9]{2}-(co2060|3yp|4yp)-[A-Za-z0-9-]+$")
GITHUB_USER_REGEX = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")
MAX_MEMBERS = 6


def api_request(method: str, endpoint: str, token: str = "", data: dict = None):
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "scssa-issue-validator",
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
    """Parses key-value fields from GitHub Issue Form markdown body."""
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


def update_issue_labels(repo_full_name: str, issue_number: str, token: str, add_labels: list, remove_labels: list):
    """Adds and removes labels cleanly."""
    if add_labels:
        api_request("POST", f"/repos/{repo_full_name}/issues/{issue_number}/labels", token, {"labels": add_labels})
    for lbl in remove_labels:
        api_request("DELETE", f"/repos/{repo_full_name}/issues/{issue_number}/labels/{lbl}", token)


def upsert_comment(repo_full_name: str, issue_number: str, token: str, comment_text: str):
    bot_marker = "<!-- scssa-issue-validator-bot -->"
    full_comment = f"{bot_marker}\n{comment_text}"

    status, comments = api_request("GET", f"/repos/{repo_full_name}/issues/{issue_number}/comments", token)
    if status == 200 and isinstance(comments, list):
        for c in comments:
            if bot_marker in c.get("body", ""):
                comment_id = c["id"]
                api_request("PATCH", f"/repos/{repo_full_name}/issues/comments/{comment_id}", token, {"body": full_comment})
                return

    api_request("POST", f"/repos/{repo_full_name}/issues/{issue_number}/comments", token, {"body": full_comment})


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    repo_full_name = os.environ.get("REPO_FULL_NAME", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    issue_author = os.environ.get("ISSUE_AUTHOR", "")
    issue_body = os.environ.get("ISSUE_BODY", "")
    org_name = os.environ.get("ORG_NAME") or (repo_full_name.split("/")[0] if "/" in repo_full_name else "SCSSA-UoK")

    if not issue_body or not issue_number:
        print("Error: Missing issue body or number.", file=sys.stderr)
        sys.exit(1)

    form = parse_issue_form(issue_body)

    repo_name = form.get("Repository Name", "").strip()
    category = form.get("Project Category", "").strip()
    description = form.get("Project Description", "").strip()
    raw_members = form.get("Team Members (GitHub Usernames)", "").strip()
    visibility = form.get("Repository Visibility", "private").strip().lower()

    if "private" in visibility:
        visibility = "private"
    elif "public" in visibility:
        visibility = "public"

    # Parse members list
    members = []
    if raw_members and raw_members.lower() != "_no response_":
        members = [m.strip().lstrip("@") for m in re.split(r"[,;\s]+", raw_members) if m.strip()]

    errors = []
    checks = {}

    # 1. Repo name regex check
    if not repo_name or repo_name.lower() == "_no response_":
        errors.append("Repository Name is required.")
    elif not REPO_REGEX.match(repo_name):
        errors.append(
            f"Invalid repository name `{repo_name}`. It must match `^e[0-9]{{2}}-(co2060|3yp|4yp)-[A-Za-z0-9-]+$`.\n"
            f"Examples: `e23-co2060-Attendance-System`, `e22-3yp-Smart-Campus`."
        )
    else:
        checks["Repository Name Format"] = f"✅ Valid (`{repo_name}`)"

    # 2. Category alignment
    if category and repo_name and category in ("co2060", "3yp", "4yp"):
        if f"-{category}-" not in repo_name:
            errors.append(f"Repository name `{repo_name}` does not match selected category `{category}`.")
        else:
            checks["Category Alignment"] = f"✅ Matches `{category}`"

    # 3. Description check
    if not description or description.lower() == "_no response_":
        errors.append("Project Description is required.")
    else:
        checks["Description"] = "✅ Provided"

    # 4. Members validation
    if len(members) > MAX_MEMBERS:
        errors.append(f"Too many team members listed ({len(members)}). Maximum allowed is {MAX_MEMBERS}.")
    else:
        users_to_verify = set(members)
        if issue_author:
            users_to_verify.add(issue_author)

        for u in users_to_verify:
            if not GITHUB_USER_REGEX.match(u):
                errors.append(f"Invalid username syntax: `@{u}`.")
                continue
            status, _ = api_request("GET", f"/users/{u}", token)
            if status == 404:
                errors.append(f"GitHub user `@{u}` does not exist.")

        if not errors:
            checks["Team Accounts"] = f"✅ All verified ({', '.join(f'@{u}' for u in users_to_verify)})"

    # 5. Org availability check
    if repo_name and not errors:
        status, _ = api_request("GET", f"/repos/{org_name}/{repo_name}", token)
        if status == 200:
            errors.append(f"Repository `{org_name}/{repo_name}` already exists in `{org_name}`.")
        elif status == 404:
            checks["Org Availability"] = f"✅ Name available in `{org_name}`"

    if errors:
        comment = (
            "### 🤖 SCSSA Request Bot\n\n"
            "**Status:** ❌ **Action Required**\n\n"
            "Please edit your issue description and correct the following:\n\n"
            + "\n".join(f"- {err}" for err in errors)
            + "\n\n---\n"
            "*Once you edit the issue, the bot will automatically re-check your inputs.*"
        )
        update_issue_labels(repo_full_name, issue_number, token, add_labels=["needs-revision"], remove_labels=["pending-approval"])
        upsert_comment(repo_full_name, issue_number, token, comment)
        print("Validation FAILED:\n" + "\n".join(errors), file=sys.stderr)
        sys.exit(1)
    else:
        checks_table = "\n".join(f"| {k} | {v} |" for k, v in checks.items())
        members_str = ", ".join(f"`@{m}`" for m in members) if members else "None (Individual project)"
        comment = (
            "### 🤖 SCSSA Request Bot\n\n"
            "**Status:** ✅ **Validation Passed**\n\n"
            "Your project request has been verified and is ready for administrator approval.\n\n"
            "| Check | Status |\n"
            "| :--- | :--- |\n"
            f"{checks_table}\n"
            f"| **Target Repository** | `{org_name}/{repo_name}` |\n"
            f"| **Project Lead** | `@{issue_author}` (Admin) |\n"
            f"| **Team Members** | {members_str} |\n"
            f"| **Visibility** | `{visibility}` |\n\n"
            "---\n"
            "👩‍🏫 **Administrator Action:** Add the label **`approved`** to provision this repository immediately."
        )
        update_issue_labels(repo_full_name, issue_number, token, add_labels=["pending-approval"], remove_labels=["needs-revision"])
        upsert_comment(repo_full_name, issue_number, token, comment)
        print("Validation PASSED successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
