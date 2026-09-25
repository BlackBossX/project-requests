 # AI Agent Guidelines & Repository Standards
 ┃
 ┃     This repository powers the automated student project repository provisioning workflow for the Statistics & Computer Science Students' Association (SCSSA), University of Kelaniya (`SCSSA-UoK`). 
 ┃
 ┃     Any AI coding assistant operating in this repository must strictly adhere to the standards, architecture, and safety protocols detailed below.
 ┃
 ┃     ---
 ┃
 ┃     ## 1. Repository Purpose & Architecture
 ┃
 ┃     ### Core Responsibilities
 ┃     - Validate incoming student project requests submitted via GitHub Issue forms.
 ┃     - Manage automated approvals, validation comments, and label state transitions.
 ┃     - Provision clean, configured course repositories in `@SCSSA-UoK` using a GitHub App installation token.
 ┃     - Assign the student lead as repository Administrator and teammates as Collaborators (`push` permission).
 ┃
 ┃     ### Directory Layout
 ┃     - `.github/workflows/`: Automated CI/CD workflows:
 ┃       - `issue-validate.yml`: Triggered on issue `opened` / `edited` to validate request forms.
 ┃       - `issue-provision.yml`: Triggered on label `approved` or authorized admin comment.
 ┃     - `.github/ISSUE_TEMPLATE/`: Form schemas (e.g., `request.yml`) for student project submissions.
 ┃     - `scripts/`: Python orchestration scripts:
 ┃       - `issue_validate.py`: Schema validation, regex parsing, user verification, and bot commentary.
 ┃       - `issue_provision.py`: Idempotent repository provisioning via GitHub REST API.
 ┃     - `.github/CODEOWNERS`: Review requirements and admin routing for repository changes.
 ┃
 ┃     ---
 ┃
 ┃     ## 2. Domain & Naming Conventions
 ┃
 ┃     ### Repository Naming Scheme
 ┃     All student repositories must follow the standardized naming convention:
 ┃     - **Format:** `e<Batch>-<Category>-<Short-Title>`
 ┃     - **Regex:** `^e[0-9]{2}-(co2060|3yp|4yp)-[A-Za-z0-9-]+$`
 ┃     - **Allowed Categories:**
 ┃       - `co2060`: 2nd Year Software Engineering Coursework
 ┃       - `3yp`: 3rd Year Group Project
 ┃       - `4yp`: 4th Year Individual Research / Capstone Project
 ┃     - **Examples:**
 ┃       - `e23-co2060-Attendance-System`
 ┃       - `e22-3yp-Smart-Campus-IoT`
 ┃
 ┃     ### Validation Rules
 ┃     1. **Title Case & Formatting:** Project titles must use hyphen-separated words (`Title-Case` or alphanumeric words).
 ┃     2. **Team Constraints:** Maximum allowed team members per project is defined in validation scripts (default: up to 6 members).
 ┃     3. **Account Existence:** All usernames in team lists must be verified against the GitHub API (`GET /users/{username}`).
 ┃
 ┃     ---
 ---
 ┃     
 ┃     ## 3. Security & Permission Guardrails
 ┃     
 ┃     1. **Authorization Verification:**
 ┃        - Automation workflows that create repositories or grant permissions must verify that the approving actor (`github.event.sender.login`) has `admin` permission in the repository or organization before executing privileged
 ┃   operations.
 ┃     2. **Token & Secret Hygiene:**
 ┃        - Never log, echo, or output tokens (`GITHUB_TOKEN`, `APP_TOKEN`, `APP_PRIVATE_KEY`) in workflow logs or script outputs.
 ┃        - Restrict workflow permissions using GitHub Actions least-privilege tokens (`permissions: issues: write`, `contents: read`).
 ┃     3. **Member vs. Outside Collaborator Distinction:**
 ┃        - Students must **only** be added as repository-level collaborators (`PUT /repos/{org}/{repo}/collaborators/{username}`), never granted organization-wide member or admin status.
 ┃     
 ┃     ---
 ┃     
 ┃     ## 4. Code & Scripting Standards
 ┃     
 ┃     ### Python Guidelines (`scripts/`)
 ┃     - **Runtime:** Python 3.11+.
 ┃     - **Dependencies:** Prefer Python standard library modules (`urllib.request`, `json`, `re`, `os`, `sys`) to keep GitHub Actions execution fast and minimize dependency vulnerabilities.
 ┃     - **Idempotency:** All API operations must be idempotent:
 ┃       - Check whether a repository or collaborator already exists (`status == 200`) before sending `POST` or `PUT` requests.
 ┃       - Update or upsert existing issue comments using a distinct HTML marker (e.g., `<!-- scssa-issue-validator-bot -->`) rather than creating duplicate spam comments.
 ┃     - **Error Handling:** Always catch `urllib.error.HTTPError`, parse the API response body, and log actionable diagnostic messages to `stderr`.
 ┃     
 ┃     ### Workflow Guidelines (`.github/workflows/`)
 ┃     - Pin third-party GitHub Actions to major versions (e.g., `actions/checkout@v4`, `actions/setup-python@v5`).
 ┃     - Ensure environment variables passed into scripts are strictly scoped.
 ┃     
 ┃     ---
 ┃     
 ┃     ## 5. Git Commit & Contribution Rules
 ┃     
 ┃     ### Commit Message Standards
 ┃     Use [Conventional Commits](https://www.conventionalcommits.org/):
 ┃     - `feat:` for new provisioning capabilities or validation rules.
 ┃     - `fix:` for bug fixes in scripts, regexes, or workflows.
 ┃     - `chore:` for dependency updates, workflow tweaks, or documentation.
 ┃     - `docs:` for documentation changes.
 ┃     
 ┃     ### Commit Sign-Off Requirement
 ┃     All commits must include a Developer Certificate of Origin (DCO) sign-off (`git commit -s`):
 ┃     ```text
 ┃     Signed-off-by: <Git User Name> <user.email@domain.com>
 ┃     
 ┃   Note: Do not hardcode fictitious user identities; determine the Git name and email dynamically from the active user's environment or git config.
   ## 6. Pre-Commit Checklist for Agents
 ┃   
 ┃   Before completing any code modifications:
 ┃   
 ┃   [ ] Ensure Python scripts pass syntax checks: python3 -m py_compile scripts/*.py.
 ┃   [ ] Verify regex changes correctly match the university course naming rules.
 ┃   [ ] Confirm no secrets, tokens, or private credentials are included in tracked files.
 ┃   [ ] Ensure commits are signed off and follow conventional commit syntax.
