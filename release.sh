#!/bin/bash
# Usage: ./release.sh <version>
#   e.g. ./release.sh 1.2.0
#
# Updates VERSION, commits, pushes, tags, and pushes the tag.
# GitHub Actions then runs tests and creates the GitHub Release.

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <version>"
  echo "  e.g. $0 1.2.0"
  exit 1
fi

VERSION="$1"
TAG="v${VERSION}"

# Validate SemVer format
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "Error: version must be in X.Y.Z format (got '$VERSION')"
  exit 1
fi

# Must be on main with a clean working tree
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
  echo "Error: must be on main branch (currently on '$BRANCH')"
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Error: working tree has uncommitted changes"
  exit 1
fi

# Pull latest before releasing
git pull --ff-only

echo "Releasing $TAG..."

# Update VERSION file
echo "$VERSION" > VERSION
git add VERSION
git commit -m "Release $TAG"
git push

# Create and push tag — triggers GitHub Actions release workflow
git tag "$TAG"
git push origin "$TAG"

echo ""
echo "Done. GitHub Actions will run tests and publish the release."
echo "https://github.com/markwmccall/vinyl-emulator/actions"
