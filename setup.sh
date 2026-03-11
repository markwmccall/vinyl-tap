#!/bin/bash
# Vinyl Emulator - Raspberry Pi setup script
# Run once after cloning the repo on the Pi:
#   chmod +x setup.sh && ./setup.sh
#
# After the script finishes it will prompt you to reboot (required for SPI).
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
sudo apt-get install -y python3-pip python3-dev python3-venv git libxml2-dev libxslt-dev python3-lxml authbind

# --- Enable SPI and add user to spi group ---
echo "[2/5] Enabling SPI interface..."
sudo raspi-config nonint do_spi 0
sudo usermod -a -G spi "$USERNAME"
echo "      SPI enabled and $USERNAME added to spi group (takes effect after reboot)"

# The Waveshare PN532 HAT routes NSS (chip select) to GPIO4 (D4), not CE0.
# Use spi0-0cs so the kernel does not claim any CE pins, leaving GPIO4 free
# for Blinka to manage as a plain DigitalInOut chip select.
if ! grep -qs "dtoverlay=spi0-0cs" /boot/firmware/config.txt 2>/dev/null; then
    # Remove any old spi0-1cs overlay if present
    sudo sed -i '/dtoverlay=spi0-1cs/d' /boot/firmware/config.txt
    echo "dtoverlay=spi0-0cs" | sudo tee -a /boot/firmware/config.txt > /dev/null
    echo "      SPI overlay configured (spi0-0cs, CE pins free for Blinka)"
fi

# --- authbind: allow the service user to bind port 80 ---
echo "[1b/5] Configuring authbind for port 80..."
sudo touch /etc/authbind/byport/80
sudo chown "$USERNAME" /etc/authbind/byport/80
sudo chmod 500 /etc/authbind/byport/80

# --- Stop service before touching the venv ---
sudo systemctl stop vinyl-web 2>/dev/null || true

# --- Python dependencies ---
echo "[3/5] Creating venv and installing Python dependencies..."
python3 -m venv --system-site-packages "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
"$REPO_DIR/.venv/bin/pip" install adafruit-circuitpython-pn532 RPi.GPIO spidev

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

# Sudoers: allow the service user to restart vinyl-web (needed by updater)
echo "$USERNAME ALL=(ALL) NOPASSWD: /bin/systemctl restart vinyl-web" \
    | sudo tee /etc/sudoers.d/vinyl-emulator-update > /dev/null
sudo chmod 440 /etc/sudoers.d/vinyl-emulator-update

# Remove obsolete sudoers entry if present
sudo rm -f /etc/sudoers.d/vinyl-emulator

# --- Optional: disable WiFi power management ---
echo ""
read -p "Disable WiFi power management? Prevents Pi from dropping off the network overnight. [Y/n] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    sudo tee /etc/systemd/system/wifi-pm-off.service > /dev/null <<'EOF'
[Unit]
Description=Disable WiFi power management
After=network.target

[Service]
Type=oneshot
ExecStart=/sbin/iwconfig wlan0 power off
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable wifi-pm-off
    sudo systemctl start wifi-pm-off
    echo "      WiFi power management disabled"
fi

# --- Optional: persistent system logs ---
echo ""
read -p "Enable persistent logs? Helps diagnose unexpected reboots/freezes. [Y/n] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    sudo mkdir -p /var/log/journal
    sudo systemd-tmpfiles --create --prefix /var/log/journal
    sudo systemctl restart systemd-journald
    echo "      Persistent logging enabled"
fi

# --- Done ---
echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Reboot the Pi:  sudo reboot"
echo "  2. After reboot, open http://vinyl-pi.local in your browser"
echo "  3. Go to Settings and enter your Sonos speaker IP and sn value"
echo "  4. Tap an NFC card to play music"
echo ""
read -p "Reboot now? [y/N] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo reboot
fi
