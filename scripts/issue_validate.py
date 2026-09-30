#!/usr/bin/env python3
"""
SCSSA Issue Form Request Validator
Validates student repository requests submitted via GitHub Issue Forms.
Repo name format: FSSD-B{YY}-G{NN}-{SHORT-TITLE}
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

MODULE_MAP = {
    "COSC 32133 / BECS 32263 \u2013 Full-Stack Software Development (FSSD)": "FSSD",
}

BATCH_MAP = {
    "22/23": "B22",
    "23/24": "B23",
    "24/25": "B24",
}

SHORT_TITLE_REGEX = re.compile(r"^[A-Za-z0-9]+([- ][A-Za-z0-9]+){0,3}$")
GITHUB_USER_REGEX = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")
MAX_MEMBERS = 4


def api_request(method, endpoint, token="", data=None):
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "scssa-issue-validator"}
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
    return re.sub(r"[\s-]+", "-", raw.strip()).title()


def parse_members(form: dict) -> list:
    """
    Reads the 12 individual member input fields (4 members x 3 fields each).
    Skips rows where all three fields are blank (unused optional slots).
    """
    members = []
    for i in range(1, 5):
        student_no = form.get(f"Member {i} \u00b7 Student No", "").strip()
        name       = form.get(f"Member {i} \u00b7 Full Name", "").strip()
        github     = form.get(f"Member {i} \u00b7 GitHub Username", "").strip().lstrip("@")

        if is_blank(student_no) and is_blank(name) and is_blank(github):
            continue

        members.append({
            "index":      i,
            "student_no": "" if is_blank(student_no) else student_no,
            "name":       "" if is_blank(name) else name,
            "github":     "" if is_blank(github) else github,
        })
    return members


def update_issue_labels(repo_full_name, issue_number, token, add_labels, remove_labels):
    if add_labels:
        api_request("POST", f"/repos/{repo_full_name}/issues/{issue_number}/labels", token, {"labels": add_labels})
    for lbl in remove_labels:
        api_request("DELETE", f"/repos/{repo_full_name}/issues/{issue_number}/labels/{lbl}", token)


def upsert_comment(repo_full_name, issue_number, token, comment_text):
    bot_marker   = "<!-- scssa-issue-validator-bot -->"
    full_comment = f"{bot_marker}\n{comment_text}"
    status, comments = api_request("GET", f"/repos/{repo_full_name}/issues/{issue_number}/comments", token)
    if status == 200 and isinstance(comments, list):
        for c in comments:
            if bot_marker in c.get("body", ""):
                api_request("PATCH", f"/repos/{repo_full_name}/issues/comments/{c['id']}", token, {"body": full_comment})
                return
    api_request("POST", f"/repos/{repo_full_name}/issues/{issue_number}/comments", token, {"body": full_comment})


def main():
    token          = os.environ.get("GITHUB_TOKEN", "")
    repo_full_name = os.environ.get("REPO_FULL_NAME", "")
    issue_number   = os.environ.get("ISSUE_NUMBER", "")
    issue_author   = os.environ.get("ISSUE_AUTHOR", "")
    issue_body     = os.environ.get("ISSUE_BODY", "")

    if not issue_body or not issue_number:
        print("Error: Missing issue body or number.", file=sys.stderr)
        sys.exit(1)

    form = parse_issue_form(issue_body)

    raw_module      = form.get("Module", "").strip()
    raw_batch       = form.get("Student Batch", "").strip()
    raw_short_title = form.get("Project Short Title", "").strip()
    description     = form.get("Project Description", "").strip()

    errors = []
    checks = {}

    # 1. Module
    module_prefix = MODULE_MAP.get(raw_module)
    if not module_prefix:
        errors.append(f"Unrecognised module: `{raw_module}`. Please select a valid module from the dropdown.")
    else:
        checks["Module"] = f"\u2705 `{raw_module}`"

    # 2. Batch
    batch_code = BATCH_MAP.get(raw_batch)
    if not batch_code:
        errors.append(f"Unrecognised batch: `{raw_batch}`. Please select `22/23`, `23/24`, or `24/25`.")
    else:
        checks["Batch"] = f"\u2705 `{raw_batch}` \u2192 `{batch_code}`"

    # 3. Short title
    if is_blank(raw_short_title):
        errors.append("Project Short Title is required.")
    elif not SHORT_TITLE_REGEX.match(raw_short_title):
        errors.append(
            f"Invalid short title `{raw_short_title}`. "
            f"Use 1\u20134 words with letters/digits separated by spaces or hyphens."
        )
    else:
        normalized = normalize_short_title(raw_short_title)
        checks["Short Title"] = f"\u2705 Will be stored as `{normalized}`"

    # 4. Description
    if is_blank(description):
        errors.append("Project Description is required.")
    else:
        checks["Description"] = "\u2705 Provided"

    # 5. Members
    members = parse_members(form)

    if not members:
        errors.append("At least Member 1 (Project Lead) must be filled in with Student No, Full Name, and GitHub Username.")
    elif len(members) > MAX_MEMBERS:
        errors.append(f"Too many team members ({len(members)}). Maximum is {MAX_MEMBERS}.")
    else:
        for m in members:
            i = m["index"]
            if not m["student_no"]:
                errors.append(f"Member {i}: Student No is required.")
            if not m["name"]:
                errors.append(f"Member {i}: Full Name is required.")
            if not m["github"]:
                errors.append(f"Member {i}: GitHub Username is required.")
            elif not GITHUB_USER_REGEX.match(m["github"]):
                errors.append(f"Member {i}: Invalid GitHub username `@{m['github']}`.")
            else:
                status, _ = api_request("GET", f"/users/{m['github']}", token)
                if status == 404:
                    errors.append(f"Member {i}: GitHub user `@{m['github']}` does not exist.")

        if not errors:
            checks["Team Members"] = f"\u2705 {len(members)} member(s) verified"

    # 6. Expected repo name preview
    if module_prefix and batch_code and not is_blank(raw_short_title) and SHORT_TITLE_REGEX.match(raw_short_title):
        normalized = normalize_short_title(raw_short_title)
        checks["Expected Repo Name"] = f"\U0001f522 `{module_prefix}-{batch_code}-G??-{normalized}` *(group number assigned on approval)*"

    if errors:
        comment = (
            "### \U0001f916 SCSSA Request Bot\n\n"
            "**Status:** \u274c **Action Required**\n\n"
            "Please edit your issue and correct the following:\n\n"
            + "\n".join(f"- {err}" for err in errors)
            + "\n\n---\n*Once you edit the issue, the bot will automatically re-check your inputs.*"
        )
        update_issue_labels(repo_full_name, issue_number, token, ["needs-revision"], ["pending-approval"])
        upsert_comment(repo_full_name, issue_number, token, comment)
        print("Validation FAILED:\n" + "\n".join(errors), file=sys.stderr)
        sys.exit(1)
    else:
        checks_table = "\n".join(f"| {k} | {v} |" for k, v in checks.items())
        lead = members[0]

        # Build avatar grid table for members
        member_rows = ""
        for m in members:
            avatar = f"![](https://github.com/{m['github']}.png?size=40)"
            role   = "\U0001f451 Admin (Lead)" if m["index"] == 1 else "Collaborator"
            member_rows += (
                f"| {avatar} | `{m['student_no']}` | **{m['name']}** "
                f"| [@{m['github']}](https://github.com/{m['github']}) | {role} |\n"
            )

        comment = (
            "### \U0001f916 SCSSA Request Bot\n\n"
            "**Status:** \u2705 **Validation Passed**\n\n"
            "Your project request has been verified and is ready for administrator approval.\n\n"
            "| Check | Status |\n| :--- | :--- |\n"
            f"{checks_table}\n\n"
            "---\n"
            "**\U0001f465 Team Members**\n\n"
            "| &nbsp; | Student No | Name | GitHub | Role |\n"
            "| :---: | :--- | :--- | :--- | :--- |\n"
            f"{member_rows}\n"
            "---\n"
            "\U0001f469\u200d\U0001f3eb **Administrator Action:** Add the label **`approved`** or comment **`/approved`** to provision this repository immediately."
        )
        update_issue_labels(repo_full_name, issue_number, token, ["pending-approval"], ["needs-revision"])
        upsert_comment(repo_full_name, issue_number, token, comment)
        print("Validation PASSED successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
