# Xbox Music Player 🎮
**240×240 SPI display · Raspberry Pi Zero W · python3-pygame**

---

## Controls (5 buttons)

| Button | NOW PLAYING | LIBRARY / QUEUE / PLAYLIST |
|--------|-------------|----------------------------|
| **LEFT / RIGHT** | Switch screen tab | Switch screen tab |
| **UP** | Toggle Shuffle | Move cursor up |
| **DOWN** | Cycle Repeat (OFF→ALL→ONE) | Move cursor down |
| **OK** | Play / Pause | Play track / Add to queue |

> In LIBRARY: OK plays the selected track immediately and sets the full library as the queue.  
> In QUEUE: OK jumps to that track.  
> In PLAYLIST VIEW: OK adds the selected track to the end of the queue.

---

## Screens

```
◄ NOW  |  LIB  |  QUEUE  |  LISTS ►
```

- **NOW PLAYING** – animated Xbox ring, title/artist, progress bar, controls, shuffle/repeat state
- **LIBRARY** – scrollable list of all scanned tracks; OK to play
- **QUEUE** – current play queue; OK to jump to track
- **PLAYLISTS** – list playlists from `/playlists/*.json`; open to browse & add tracks

---

## Directory layout

```
xboxplayer/
├── player.py          ← main app
├── setup.sh           ← one-shot install script
├── music/             ← drop .mp3 / .ogg / .flac / .wav here
│   ├── ArtistA/
│   │   └── song.mp3
│   └── song2.ogg
└── playlists/         ← JSON playlists
    └── Chill.json
```

### Playlist format (`playlists/MyList.json`)
```json
[
  "/home/pi/xboxplayer/music/ArtistA/song.mp3",
  "/home/pi/xboxplayer/music/ArtistB/other.ogg"
]
```

---

## GPIO wiring (BCM pin numbers)

| Button | Default GPIO | Change in `player.py` |
|--------|-------------|----------------------|
| UP     | GPIO 17     | `BTN_UP    = 17`     |
| DOWN   | GPIO 27     | `BTN_DOWN  = 27`     |
| LEFT   | GPIO 22     | `BTN_LEFT  = 22`     |
| RIGHT  | GPIO 23     | `BTN_RIGHT = 23`     |
| OK     | GPIO 24     | `BTN_OK    = 24`     |

Wire each button between its GPIO pin and **GND** (internal pull-ups enabled).

---

## SPI Display (ST7789 240×240)

Typical 1.3" cheap module pinout:

| Display | Pi Zero W |
|---------|-----------|
| VCC     | 3.3V      |
| GND     | GND       |
| SCL/SCK | GPIO 11 (SPI0 SCLK) |
| SDA/MOSI| GPIO 10 (SPI0 MOSI) |
| RES     | GPIO 25   |
| DC      | GPIO 24 ← **conflicts with OK button by default!** |
| CS      | GPIO 8  (SPI0 CE0) |
| BL      | 3.3V or GPIO PWM for brightness |

> **Pin conflict:** The default DC pin (24) clashes with the OK button.  
> Either rewire DC to another free GPIO and update the `dtoverlay` line in `/boot/config.txt`,  
> or use GPIO 26 for OK and update `BTN_OK = 26` in `player.py`.

The display uses framebuffer `/dev/fb1` via the `st7789v` device tree overlay.  
pygame writes to that framebuffer using `SDL_VIDEODRIVER=fbcon` + `SDL_FBDEV=/dev/fb1`.

---

## Quick start

```bash
# 1. Clone / copy files
git clone ... xboxplayer && cd xboxplayer

# 2. Run setup (installs deps, configures boot, creates systemd service)
chmod +x setup.sh && ./setup.sh

# 3. Put music in ~/xboxplayer/music/

# 4. Test in a desktop window (SSH with X forwarding or local desktop)
python3 player.py

# 5. Reboot Pi → display shows player automatically
sudo reboot
```

---

## Optional: better audio on Pi Zero W

The Zero W has no audio jack. Options:
- **USB DAC** – plug a cheap USB audio adapter
- **I2S DAC** (MAX98357A) – best quality, uses GPIO pins
- **Bluetooth speaker** – set `SDL_AUDIODRIVER=pulse` and pair via `bluetoothctl`

```bash
# ALSA default card (USB DAC example)
echo "defaults.pcm.card 1\ndefaults.ctl.card 1" | sudo tee /etc/asound.conf
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `python3-pygame` | display + audio |
| `python3-rpi.gpio` | button GPIO |
| `mutagen` (pip, optional) | ID3 / Vorbis tag reading |
| `fonts-dejavu-core` | UI font |
| `st7789v` dtoverlay | SPI framebuffer driver |
