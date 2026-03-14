#!/bin/bash
# Vinyl Emulator — fresh install on Raspberry Pi OS
#
# Run:
#   curl -sSL https://raw.githubusercontent.com/markwmccall/vinyl-emulator/main/scripts/install.sh | bash
#
# This script downloads the latest release and runs setup.sh.
# Requires: curl, python3, git

set -e

REPO="markwmccall/vinyl-emulator"
INSTALL_DIR="${HOME}/vinyl-emulator"

echo ""
echo "=== Vinyl Emulator Installer ==="
echo ""

# Fetch the latest release tag from GitHub
echo "Checking latest release..."
LATEST=$(curl -sf "https://api.github.com/repos/${REPO}/releases/latest" \
    | python3 -c "import sys, json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null)

if [ -z "$LATEST" ]; then
    echo "Error: could not determine latest release. Check your internet connection."
    exit 1
fi

echo "Latest release: $LATEST"
echo "Install directory: $INSTALL_DIR"
echo ""

if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR already exists."
    read -p "Remove and reinstall? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    rm -rf "$INSTALL_DIR"
fi

# Download and extract the release tarball
echo "Downloading $LATEST..."
TARBALL_URL="https://github.com/${REPO}/archive/refs/tags/${LATEST}.tar.gz"
mkdir -p "$INSTALL_DIR"
curl -sSL "$TARBALL_URL" | tar -xz --strip-components=1 -C "$INSTALL_DIR"

echo "Extracted to $INSTALL_DIR"
echo ""

# Run setup
cd "$INSTALL_DIR"
chmod +x scripts/setup.sh
./scripts/setup.sh
