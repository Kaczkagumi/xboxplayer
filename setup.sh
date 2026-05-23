#!/bin/bash
# ╔══════════════════════════════════════════════════╗
# ║   Xbox Music Player – Pi Zero W Setup Script     ║
# ║   Raspbian Lite  |  240×240 SPI display          ║
# ╚══════════════════════════════════════════════════╝

set -e
INSTALL_DIR="$HOME/xboxplayer"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ██╗  ██╗██████╗  ██████╗ ██╗  ██╗"
echo "  ╚██╗██╔╝██╔══██╗██╔═══██╗╚██╗██╔╝"
echo "   ╚███╔╝ ██████╔╝██║   ██║ ╚███╔╝ "
echo "   ██╔██╗ ██╔══██╗██║   ██║ ██╔██╗ "
echo "  ██╔╝ ██╗██████╔╝╚██████╔╝██╔╝ ██╗"
echo "  ╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚═╝  ╚═╝"
echo "       Music Player – Setup"
echo ""

# ── 1. System packages ──────────────────────────────────────────────────────
echo "[1/5] Installing system packages..."
sudo apt-get update -q
sudo apt-get install -y \
    python3-pygame \
    python3-pip \
    python3-rpi.gpio \
    libsdl2-dev \
    libsdl2-mixer-2.0-0 \
    libsdl2-ttf-2.0-0 \
    fonts-dejavu-core \
    alsa-utils \
    mpg123

# ── 2. Python packages ──────────────────────────────────────────────────────
echo "[2/5] Installing Python packages..."
pip3 install mutagen --break-system-packages 2>/dev/null || \
pip3 install mutagen || true   # optional – for ID3 tag reading

# ── 3. Copy player files ─────────────────────────────────────────────────────
echo "[3/5] Installing player..."
mkdir -p "$INSTALL_DIR/music"
mkdir -p "$INSTALL_DIR/playlists"
cp "$SCRIPT_DIR/player.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/player.py"

# ── 4. SPI + framebuffer config ─────────────────────────────────────────────
echo "[4/5] Configuring /boot/config.txt for ST7789 240x240 SPI display..."
CONFIG="/boot/config.txt"

add_if_missing() {
    grep -qF "$1" "$CONFIG" || echo "$1" | sudo tee -a "$CONFIG" > /dev/null
}

# Enable SPI
add_if_missing "dtparam=spi=on"

# ST7789 240x240 overlay  ← ADJUST pins to match your wiring!
# Typical cheap 1.3" 240x240 SPI:
#   VCC→3.3V  GND→GND  SCL→GPIO11(SCLK)  SDA→GPIO10(MOSI)
#   RES→GPIO25  DC→GPIO24  BL→3.3V  CS→GPIO8(CE0)
add_if_missing "dtoverlay=st7789v,speed=40000000,width=240,height=240,rotate=0,dc_pin=24,reset_pin=25"

# Framebuffer console on fb1 (SPI display becomes /dev/fb1)
add_if_missing "dtoverlay=vc4-fkms-v3d"

echo ""
echo "  ⚠  IMPORTANT: Edit /boot/config.txt if your DC/RESET pins differ!"
echo "  DC pin default:    GPIO24  (BCM)"
echo "  RESET pin default: GPIO25  (BCM)"
echo ""

# ── 5. Autostart service ─────────────────────────────────────────────────────
echo "[5/5] Creating systemd service..."
SERVICE="[Unit]
Description=Xbox Music Player
After=sound.target

[Service]
User=$USER
Environment=SDL_VIDEODRIVER=fbcon
Environment=SDL_FBDEV=/dev/fb1
Environment=SDL_AUDIODRIVER=alsa
ExecStart=/usr/bin/python3 $INSTALL_DIR/player.py --music $INSTALL_DIR/music --playlists $INSTALL_DIR/playlists
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target"

echo "$SERVICE" | sudo tee /etc/systemd/system/xboxplayer.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable xboxplayer.service

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo ""
echo "  Drop your music into:  $INSTALL_DIR/music/"
echo "  Playlists go in:       $INSTALL_DIR/playlists/"
echo ""
echo "  Test now (window):     python3 $INSTALL_DIR/player.py"
echo "  Start service:         sudo systemctl start xboxplayer"
echo "  View logs:             journalctl -u xboxplayer -f"
echo ""
echo "  Reboot to apply display overlay changes."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
