#!/bin/bash
# Vinyl Emulator — Raspberry Pi setup script
# Run once after cloning the repo on the Pi:
#   chmod +x setup.sh && ./setup.sh
#
# After the script finishes it will prompt you to reboot (required for I2C).
# After rebooting, open http://vinyl-pi.local:5000 in your browser,
# go to Settings, and fill in your speaker IP and sn value.

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
USERNAME="$(whoami)"

echo ""
echo "=== Vinyl Emulator Setup ==="
echo "Repo: $REPO_DIR"
echo "User: $USERNAME"
echo ""

# --- System packages ---
echo "[1/5] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y python3-pip python3-dev python3-venv git libxml2-dev libxslt-dev python3-lxml

# --- Enable I2C and add user to i2c group ---
echo "[2/5] Enabling I2C interface..."
sudo raspi-config nonint do_i2c 0
sudo usermod -a -G i2c "$USERNAME"
echo "      I2C enabled and $USERNAME added to i2c group (takes effect after reboot)"

# --- Stop service before touching the venv ---
sudo systemctl stop vinyl-web 2>/dev/null || true

# --- Python dependencies ---
echo "[3/5] Creating venv and installing Python dependencies..."
python3 -m venv --system-site-packages "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
"$REPO_DIR/.venv/bin/pip" install adafruit-circuitpython-pn532 RPi.GPIO

# --- Config file ---
echo "[4/5] Setting up config..."
if [ ! -f "$REPO_DIR/config.json" ]; then
    cp "$REPO_DIR/config.json.example" "$REPO_DIR/config.json"
    # Set nfc_mode to pn532 since we're on the Pi
    python3 -c "
import json
with open('$REPO_DIR/config.json') as f:
    c = json.load(f)
c['nfc_mode'] = 'pn532'
with open('$REPO_DIR/config.json', 'w') as f:
    json.dump(c, f, indent=2)
"
    echo "      Created config.json with nfc_mode=pn532"
    echo "      Set speaker IP and sn via the web UI after setup"
else
    echo "      config.json already exists, skipping"
fi

# --- systemd services ---
echo "[5/5] Installing systemd services..."

# Substitute actual username and repo path into service file
sed "s|/home/pi/vinyl-emulator|$REPO_DIR|g; s|User=pi|User=$USERNAME|g" \
    "$REPO_DIR/etc/vinyl-web.service" \
    | sudo tee /etc/systemd/system/vinyl-web.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable vinyl-web
sudo systemctl restart vinyl-web
echo "      Service installed, enabled, and restarted"

# Remove obsolete sudoers entry if present
sudo rm -f /etc/sudoers.d/vinyl-emulator

# --- Done ---
echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Reboot the Pi:  sudo reboot"
echo "  2. After reboot, open http://vinyl-pi.local:5000 in your browser"
echo "  3. Go to Settings and enter your Sonos speaker IP and sn value"
echo "  4. Tap an NFC card to play music"
echo ""
read -p "Reboot now? [y/N] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo reboot
fi
