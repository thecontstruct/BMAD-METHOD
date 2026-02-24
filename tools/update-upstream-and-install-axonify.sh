#!/bin/bash
#
# Update upstream and install BMAD to axonify workspace
#
# This script:
# 1. Fetches upstream changes and merges them into main
# 2. Updates the current branch with main
# 3. Installs BMAD modules to the axonify workspace
#
# Usage: ./tools/update-upstream-and-install-axonify.sh

set -euo pipefail

# Get current branch
CURRENT_BRANCH=$(git branch --show-current)

# Update upstream
echo "🔄 Updating from upstream..."
git fetch upstream
git checkout main
git merge upstream/main
git push origin main

# Return to original branch and merge main
echo "🔄 Updating current branch with main..."
git checkout "$CURRENT_BRANCH"
git merge main --no-edit
git push

# Install BMAD to axonify workspace
echo "📦 Installing BMAD to axonify workspace..."
node tools/cli/bmad-cli.js install \
  --directory /Users/pmahncke/workspace/axonify-bmad \
  --modules bmm,bmb,cis,tea \
  --tools claude-code \
  --yes

echo "✅ Complete!"
