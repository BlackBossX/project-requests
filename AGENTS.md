# Repository Guidelines

- **Git Identity:** You MUST NOT hardcode a specific user for commits. You must dynamically determine the Git user name and email of the user making the request (e.g., from their prompt, previous commits, or global `git config user.name`/`user.email`).
- **Commit Sign-Off:** All commits to this repository must be signed off using the user's dynamically determined details:
  `Signed-off-by: <Determined User Name> <determined.email@example.com>`
