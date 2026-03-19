#!/bin/bash
# One-time dev environment setup for vinyl-tap on macOS.
# Safe to re-run — skips steps already done.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CERTS_DIR="$PROJECT_ROOT/certs"
CERT="$CERTS_DIR/vinyltap-dev.local.crt"
KEY="$CERTS_DIR/vinyltap-dev.local.key"
HOSTNAME="vinyltap-dev.local"

echo "=== Vinyl Tap — Mac Dev Setup ==="
echo ""

# ── 1. /etc/hosts ────────────────────────────────────────────────────────────
if grep -q "$HOSTNAME" /etc/hosts 2>/dev/null; then
  echo "[OK] $HOSTNAME already in /etc/hosts"
else
  echo "[+] Adding $HOSTNAME to /etc/hosts (requires sudo)..."
  echo "127.0.0.1 $HOSTNAME" | sudo tee -a /etc/hosts > /dev/null
  echo "[OK] Added"
fi

# ── 2. Self-signed SSL cert ───────────────────────────────────────────────────
mkdir -p "$CERTS_DIR"
if [ -f "$CERT" ] && [ -f "$KEY" ]; then
  echo "[OK] SSL cert already exists ($CERTS_DIR)"
else
  echo "[+] Generating self-signed SSL cert for $HOSTNAME..."
  openssl req -x509 -newkey rsa:2048 \
    -keyout "$KEY" -out "$CERT" \
    -days 365 -nodes \
    -subj "/CN=$HOSTNAME" \
    -addext "subjectAltName=DNS:$HOSTNAME" \
    2>/dev/null
  echo "[OK] Cert written to $CERTS_DIR"
fi

# ── 3. Trust cert in macOS Keychain (eliminates browser warning) ──────────────
if security find-certificate -c "$HOSTNAME" /Library/Keychains/System.keychain &>/dev/null; then
  echo "[OK] Cert already trusted in Keychain"
else
  echo "[+] Trusting cert in macOS Keychain (requires sudo)..."
  sudo security add-trusted-cert \
    -d -r trustRoot \
    -k /Library/Keychains/System.keychain \
    "$CERT" 2>/dev/null \
    && echo "[OK] Trusted — no browser warning" \
    || echo "[!] Could not add to Keychain — you will see a browser security warning (accept once)"
fi

# ── 4. Python virtual environment ─────────────────────────────────────────────
if [ -d "$PROJECT_ROOT/.venv" ]; then
  echo "[OK] Virtual environment exists"
else
  echo "[+] Creating virtual environment..."
  python3 -m venv "$PROJECT_ROOT/.venv"
  "$PROJECT_ROOT/.venv/bin/pip" install -r "$PROJECT_ROOT/requirements.txt" -q
  echo "[OK] Virtual environment ready"
fi

# ── 5. Data directory (migrate from old in-project location if needed) ────────
DATA_DIR="$HOME/.local/share/vinyltap-dev"
mkdir -p "$DATA_DIR"

if [ -f "$PROJECT_ROOT/config.json" ] && [ ! -f "$DATA_DIR/config.json" ]; then
  cp "$PROJECT_ROOT/config.json" "$DATA_DIR/config.json"
  echo "[+] Migrated config.json to $DATA_DIR"
else
  echo "[OK] Data directory ready ($DATA_DIR)"
fi

if [ ! -f "$DATA_DIR/tags.json" ]; then
  if [ -f "$PROJECT_ROOT/data/tags.json" ]; then
    cp "$PROJECT_ROOT/data/tags.json" "$DATA_DIR/tags.json"
    echo "[+] Migrated tags.json to $DATA_DIR"
  elif [ -f "$PROJECT_ROOT/tags.json" ]; then
    cp "$PROJECT_ROOT/tags.json" "$DATA_DIR/tags.json"
    echo "[+] Migrated tags.json to $DATA_DIR"
  fi
fi

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Run: ./dev-service.sh start"
echo "  2. Open https://$HOSTNAME in your browser"
echo "  3. Go to Settings → Music Services"
echo "  4. Enter your dev key credentials and click Connect Sonos Account"
echo ""
echo "  Dev key (vinyl-tap-dev-key):"
echo "    Key:          48e8d7f6-abee-4375-8f46-f853baa0d615"
echo "    Secret:       0a2dc6fa-37dc-4b06-8dae-46b82c11556b"
echo "    Redirect URI: https://$HOSTNAME/sonos/callback"
