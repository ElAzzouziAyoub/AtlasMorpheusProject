#!/usr/bin/env bash
# rollback.sh — Revert the last import by re-importing from the previous Git commit.
#
# Usage:
#   ./scripts/rollback.sh --env test
#   ./scripts/rollback.sh --env prod
#
# How it works:
#   1. Creates a temporary worktree at the previous commit (HEAD~1)
#   2. Runs the importer from that snapshot
#   3. Cleans up the temporary worktree
#
# Prerequisites: MORPHEUS_URL and MORPHEUS_TOKEN must be set in .env or the shell.

set -euo pipefail

ENV=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env) ENV="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

if [[ -z "$ENV" ]]; then
    echo "Usage: $0 --env <dev|test|prod>"
    exit 1
fi

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
PREV_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD~1)"
WORKTREE_DIR="$(mktemp -d)"

echo "Rolling back $ENV to commit $PREV_COMMIT ..."
git -C "$REPO_ROOT" worktree add --detach "$WORKTREE_DIR" "$PREV_COMMIT"

cleanup() {
    git -C "$REPO_ROOT" worktree remove --force "$WORKTREE_DIR" 2>/dev/null || true
    rm -rf "$WORKTREE_DIR"
}
trap cleanup EXIT

cd "$WORKTREE_DIR"
pip install -q -r requirements.txt

echo "--- Dry-run from previous state ---"
python scripts/importer.py --env "$ENV" --dry-run

echo "--- Applying rollback ---"
python scripts/importer.py --env "$ENV"

echo "Rollback to $PREV_COMMIT complete."
echo "Remember to revert the bad commit in Git:"
echo "  git revert HEAD && git push"
