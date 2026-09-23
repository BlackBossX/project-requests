#!/usr/bin/env bash
# SCSSA Setup Secrets Helper
# Saves the App ID and Private Key into GitHub Secrets

set -e

REPO="SCSSA-UoK/project-requests"

echo "🔐 Configuring Secrets for $REPO"
echo "=========================================="

read -p "Enter GitHub App ID (numeric): " APP_ID
if [ -z "$APP_ID" ]; then
  echo "❌ App ID cannot be empty."
  exit 1
fi

read -p "Enter path to downloaded private key (.pem file): " KEY_PATH
if [ ! -f "$KEY_PATH" ]; then
  echo "❌ File '$KEY_PATH' does not exist."
  exit 1
fi

echo "Setting APP_ID secret..."
gh secret set APP_ID --repo "$REPO" --body "$APP_ID"

echo "Setting APP_PRIVATE_KEY secret..."
gh secret set APP_PRIVATE_KEY --repo "$REPO" < "$KEY_PATH"

echo "✅ All secrets successfully configured for $REPO!"
gh secret list --repo "$REPO"
