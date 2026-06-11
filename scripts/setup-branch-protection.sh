#!/usr/bin/env bash
# Apply branch protection to main on the current GitHub repo.
# Requires: token with admin:repo_hook + repo scope.
# Usage: GH_TOKEN=ghp_*** ./scripts/setup-branch-protection.sh <owner> <repo>

set -euo pipefail

OWNER="${1:-SausageMan99}"
REPO="${2:-Whub-web}"
BRANCH="${3:-main}"

if [ -z "${GH_TOKEN:-}" ] && [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "ERROR: set GH_TOKEN (or GITHUB_TOKEN) to a token with admin:repo_hook + repo scope."
  exit 1
fi

TOKEN="${GH_TOKEN:-$GITHUB_TOKEN}"
API="https://api.github.com"

curl -sS -X PUT "$API/repos/$OWNER/$REPO/branches/$BRANCH/protection" \
  -H "Authorization: token $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -d '{
    "required_status_checks": {
      "strict": true,
      "contexts": ["verify-build", "verify-quality", "verify-worker-clean"]
    },
    "enforce_admins": true,
    "required_pull_request_reviews": {
      "dismissal_restrictions": {},
      "dismiss_stale_reviews": true,
      "require_code_owner_reviews": false,
      "required_approving_review_count": 1,
      "require_last_push_approval": false
    },
    "restrictions": null,
    "required_linear_history": true,
    "allow_force_pushes": false,
    "allow_deletions": false,
    "block_creations": false,
    "required_conversation_resolution": true,
    "lock_branch": false,
    "allow_fork_syncing": false
  }' | python3 -c "import sys, json; d=json.load(sys.stdin); print('Protection applied.' if 'url' in d else 'Failed: ' + json.dumps(d))"
