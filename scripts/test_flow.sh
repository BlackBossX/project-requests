#!/usr/bin/env bash
# SCSSA Automated Test Script
# Creates a test branch, validates a dummy request, and opens a pull request.

set -e

BRANCH_NAME="test/request-demo-$(date +%s)"
TEST_REPO="e22-co2060-Demo-App"
FILE_PATH="requests/${TEST_REPO}.yml"

echo "🧪 Starting Automated End-to-End Test"
echo "=========================================="

# Ensure we are on main and up to date
git checkout main
git pull origin main

# Create new test branch
echo "🌿 Creating test branch: $BRANCH_NAME"
git checkout -b "$BRANCH_NAME"

# Create dummy request file
cat <<EOF > "$FILE_PATH"
repo: $TEST_REPO
description: Automated test project for verifying SCSSA CI/CD provisioning.
members:
  - kavix
visibility: private
EOF

echo "🔍 Running pre-flight local validation..."
python3 scripts/validate_request.py --file "$FILE_PATH"

echo "📤 Committing and pushing request..."
git add "$FILE_PATH"
git commit -s -m "feat: submit request for $TEST_REPO"
git push -u origin "$BRANCH_NAME"

echo "🚀 Opening Pull Request..."
PR_URL=$(gh pr create \
  --repo SCSSA-UoK/project-requests \
  --title "Request: $TEST_REPO" \
  --body "Automated test request to verify validation and repo generation.")

echo ""
echo "=========================================="
echo "🎉 Pull Request Opened Successfully!"
echo "URL: $PR_URL"
echo ""
echo "Next Steps:"
echo "1. Open the PR link above and watch the 'Validate Request' check run."
echo "2. Once passed, click 'Merge pull request'."
echo "3. The 'Create Project Repository' action will automatically provision $TEST_REPO!"
echo "=========================================="
