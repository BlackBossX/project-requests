#!/usr/bin/env python3
"""
SCSSA Project Request Validator
Validates pull requests submitted by students to request new course repositories.
Supports both GitHub Actions automated execution and local testing mode.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

try:
    import yaml
except ImportError:
    yaml = None

REPO_REGEX = re.compile(r"^e[0-9]{2}-(co2060|3yp|4yp)-[A-Za-z0-9-]+$")
GITHUB_USER_REGEX = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$")
MAX_MEMBERS = 6


def api_request(method: str, endpoint: str, token: str = "", data: dict = None):
    """Makes a lightweight HTTP request to the GitHub REST API."""
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "scssa-request-validator",
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


def parse_yaml_file(file_path: str) -> dict:
    """Parses YAML using PyYAML if installed, or fallback lightweight parser."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if yaml is not None:
        return yaml.safe_load(content)

    # Minimal fallback parser for standard key-value and list structures
    data = {}
    current_key = None
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line and not line.startswith("-"):
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip().split("#")[0].strip()
            if val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                data[key] = items
            elif val:
                data[key] = val.strip("'\"")
            else:
                data[key] = []
                current_key = key
        elif line.startswith("-") and current_key:
            item = line[1:].strip().strip("'\"")
            if isinstance(data.get(current_key), list):
                data[current_key].append(item)
    return data


def upsert_pr_comment(repo_full_name: str, pr_number: str, token: str, comment_text: str):
    """Creates or updates a single sticky validation comment on the PR."""
    if not repo_full_name or not pr_number or not token:
        return

    bot_marker = "<!-- scssa-uok-request-bot -->"
    full_comment = f"{bot_marker}\n{comment_text}"

    status, comments = api_request("GET", f"/repos/{repo_full_name}/issues/{pr_number}/comments", token)
    if status == 200 and isinstance(comments, list):
        for c in comments:
            if bot_marker in c.get("body", ""):
                comment_id = c["id"]
                api_request("PATCH", f"/repos/{repo_full_name}/issues/comments/{comment_id}", token, {"body": full_comment})
                return

    api_request("POST", f"/repos/{repo_full_name}/issues/{pr_number}/comments", token, {"body": full_comment})


def write_summary(text: str):
    """Outputs markdown to GitHub Actions workflow summary."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file and os.path.exists(summary_file):
        try:
            with open(summary_file, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass


def validate_file(file_path: str, org_name: str, token: str = "", pr_author: str = "") -> tuple:
    """Runs all semantic and security checks on a single request file."""
    errors = []
    checks = {}

    if not os.path.exists(file_path):
        return [f"File `{file_path}` does not exist."], checks

    try:
        data = parse_yaml_file(file_path)
    except Exception as e:
        return [f"YAML syntax error: `{e}`"], checks

    if not isinstance(data, dict):
        return ["File root must be a YAML dictionary mapping."], checks

    repo = data.get("repo")
    description = data.get("description")
    members = data.get("members", [])
    visibility = str(data.get("visibility", "private")).lower()

    # 1. Structure checks
    if not repo or not isinstance(repo, str):
        errors.append("Missing required field `repo` (must be a valid string).")
    if not description or not isinstance(description, str):
        errors.append("Missing required field `description` (brief summary of project).")
    if not isinstance(members, list):
        errors.append("Field `members` must be a list of GitHub usernames.")
    if visibility not in ("private", "public"):
        errors.append(f"Invalid `visibility: {visibility}` (must be `private` or `public`).")

    # 2. Filename match check
    filename = os.path.basename(file_path)
    expected_names = [f"{repo}.yml", f"{repo}.yaml"] if repo else []
    if repo and filename not in expected_names:
        errors.append(f"File is named `{filename}`, but `repo:` is `{repo}`. File must be named `requests/{repo}.yml`.")
    else:
        checks["Filename Matching"] = "✅ Correct"

    # 3. Regex naming rule check
    if repo:
        if REPO_REGEX.match(repo):
            checks["Naming Convention"] = f"✅ Valid (`{repo}`)"
        else:
            errors.append(
                f"Repository name `{repo}` does not match pattern `^e[0-9]{{2}}-(co2060|3yp|4yp)-[A-Za-z0-9-]+$`.\n"
                f"  - Allowed categories: `co2060`, `3yp`, `4yp`\n"
                f"  - Example: `e22-co2060-Attendance-App`"
            )

    # 4. Members count & validity check
    if isinstance(members, list):
        if len(members) == 0:
            errors.append("List `members` must contain at least 1 GitHub username.")
        elif len(members) > MAX_MEMBERS:
            errors.append(f"Maximum of {MAX_MEMBERS} members allowed (found {len(members)}).")
        else:
            checks["Team Size"] = f"✅ {len(members)} member(s)"

        users_to_verify = set(members)
        if pr_author:
            users_to_verify.add(pr_author)

        verified_users = []
        for u in users_to_verify:
            if not isinstance(u, str) or not GITHUB_USER_REGEX.match(u):
                errors.append(f"Invalid GitHub username syntax: `{u}`.")
                continue

            status, _ = api_request("GET", f"/users/{u}", token)
            if status == 404:
                errors.append(f"GitHub user `@{u}` does not exist on GitHub.")
            elif status == 200:
                verified_users.append(u)

        if not errors:
            checks["GitHub Accounts"] = f"✅ All verified ({', '.join(f'@{u}' for u in users_to_verify)})"

    # 5. Check if repo already exists in organization
    if repo and org_name:
        status, _ = api_request("GET", f"/repos/{org_name}/{repo}", token)
        if status == 200:
            errors.append(f"Repository `https://github.com/{org_name}/{repo}` already exists in `{org_name}`.")
        elif status == 404:
            checks["Org Availability"] = f"✅ Name available in `{org_name}`"

    details = {
        "repo": repo,
        "org": org_name,
        "description": description,
        "visibility": visibility,
        "members": members if isinstance(members, list) else [],
        "pr_author": pr_author,
        "checks": checks,
    }
    return errors, details


def main():
    parser = argparse.ArgumentParser(description="Validate repository requests.")
    parser.add_argument("--file", help="Path to a single request file to validate locally.")
    parser.add_argument("--org", default=os.environ.get("ORG_NAME", "SCSSA-UoK"), help="Target GitHub organization.")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    base_ref = os.environ.get("BASE_REF", "main")
    repo_full_name = os.environ.get("REPO_FULL_NAME", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    pr_author = os.environ.get("PR_AUTHOR", "")
    org_name = args.org or (repo_full_name.split("/")[0] if "/" in repo_full_name else "SCSSA-UoK")

    # Local CLI inspection mode
    if args.file:
        print(f"🔍 Validating local request file: {args.file} against organization '{org_name}'...")
        errors, details = validate_file(args.file, org_name, token, pr_author)
        if errors:
            print("\n❌ Validation Failed:")
            for e in errors:
                print(f"  • {e}")
            sys.exit(1)
        else:
            print("\n✅ Validation Passed!")
            for k, v in details.get("checks", {}).items():
                print(f"  • {k}: {v}")
            sys.exit(0)

    # GitHub Actions pull_request mode
    errors = []
    target_file = None

    try:
        diff_cmd = ["git", "diff", "--name-status", f"origin/{base_ref}...HEAD"]
        diff_output = subprocess.check_output(diff_cmd, text=True).strip()
    except subprocess.CalledProcessError as e:
        errors.append(f"Could not compute git diff against `origin/{base_ref}`: {e}")
        diff_output = ""

    diff_lines = [line.strip() for line in diff_output.splitlines() if line.strip()]

    if not diff_lines:
        errors.append("No changes detected in this pull request.")
    else:
        if len(diff_lines) > 1:
            errors.append(
                f"Expected exactly **1** new file, but found **{len(diff_lines)}** modified files:\n"
                + "\n".join(f"- `{line}`" for line in diff_lines)
            )

        for line in diff_lines:
            parts = line.split(maxsplit=1)
            status, path = parts[0], parts[1] if len(parts) > 1 else ""
            if not (path.startswith("requests/") and (path.endswith(".yml") or path.endswith(".yaml"))):
                errors.append(f"Unauthorized file modified: `{path}`. Only new files in `requests/` are permitted.")
            elif status != "A":
                errors.append(f"File `{path}` has status `{status}`. Only new additions (`A`) are allowed.")
            else:
                target_file = path

    details = {}
    if target_file and not errors:
        file_errors, details = validate_file(target_file, org_name, token, pr_author)
        errors.extend(file_errors)

    # Format result comment
    if errors:
        comment = (
            "### 🤖 SCSSA Repository Request Bot\n\n"
            "**Status:** ❌ **Action Required**\n\n"
            "Your pull request could not be validated due to the following issue(s):\n\n"
            + "\n".join(f"- {err}" for err in errors)
            + "\n\n---\n"
            "*Please update your request file and push a new commit to this branch. The bot will automatically re-evaluate.*"
        )
        print("Validation FAILED:\n" + "\n".join(errors), file=sys.stderr)
        write_summary(comment)
        upsert_pr_comment(repo_full_name, pr_number, token, comment)
        sys.exit(1)
    else:
        members_list = ", ".join(f"`@{m}`" for m in details.get("members", []))
        checks_table = "\n".join(f"| {k} | {v} |" for k, v in details.get("checks", {}).items())
        comment = (
            "### 🤖 SCSSA Repository Request Bot\n\n"
            "**Status:** ✅ **Validation Passed**\n\n"
            "Your request is valid and ready for faculty / admin review!\n\n"
            "| Requirement | Status |\n"
            "| :--- | :--- |\n"
            f"{checks_table}\n"
            f"| **Target Repository** | `{org_name}/{details.get('repo')}` |\n"
            f"| **Project Admin** | `@{details.get('pr_author') or 'PR Author'}` |\n"
            f"| **Collaborators** | {members_list} |\n"
            f"| **Visibility** | `{details.get('visibility')}` |\n\n"
            "--- \n"
            "📌 **Next Step:** An organization administrator will review and merge this request. "
            "Once merged, the repository will be provisioned automatically."
        )
        print("Validation PASSED successfully.")
        write_summary(comment)
        upsert_pr_comment(repo_full_name, pr_number, token, comment)
        sys.exit(0)


if __name__ == "__main__":
    main()
