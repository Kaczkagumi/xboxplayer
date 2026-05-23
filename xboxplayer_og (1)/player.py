#!/usr/bin/env python3
"""
ORIGINAL XBOX DASHBOARD - Music Player
240x240 SPI display | python3-pygame | Raspberry Pi Zero W
5 buttons: UP / DOWN / LEFT / RIGHT / OK

Aesthetic: OG Xbox (2001) — deep black, lime-green glows, beveled panels,
thick gradients, orb animations, Y2K maximalism. NO minimalism.
"""

import pygame
import pygame.gfxdraw
import pygame.mixer
import os, sys, json, random, math, time
from pathlib import Path
from enum import Enum, auto

# ── Display ────────────────────────────────────────────────────────────────────
SW, SH = 240, 240
FPS = 30

# ── GPIO (BCM) — change to match your wiring ──────────────────────────────────
BTN_UP    = 17
BTN_DOWN  = 27
BTN_LEFT  = 22
BTN_RIGHT = 23
BTN_OK    = 26   # NOTE: 24 conflicts with typical ST7789 DC pin

# ══════════════════════════════════════════════════════════════════════════════
#  OG XBOX COLOUR PALETTE
#  Deep blacks, lime greens, toxic glows, dark chrome
# ══════════════════════════════════════════════════════════════════════════════
BLACK       = (  0,   0,   0)
BG_DEEP     = (  4,   8,   4)     # almost black with green tint
BG_MID      = (  8,  18,   8)
PANEL_DARK  = (  6,  20,   6)
PANEL_MID   = ( 12,  38,  12)
PANEL_LIT   = ( 16,  52,  16)
CHROME_DARK = ( 18,  18,  18)
CHROME_MID  = ( 36,  36,  36)
CHROME_HI   = ( 72,  72,  72)
CHROME_SPEC = (140, 140, 140)

XBOX_GREEN  = ( 82, 196,  26)   # lime green
XBOX_BRIGHT = (122, 255,  50)   # hot lime
XBOX_GLOW   = ( 60, 160,  10)   # mid glow
XBOX_DIM    = ( 28,  80,   8)   # dark green
XBOX_TOXIC  = (160, 255,  60)   # specular highlight
XBOX_PALE   = ( 40, 100,  20)   # muted

WHITE       = (255, 255, 255)
OFF_WHITE   = (210, 230, 200)
GREY_LT     = (160, 180, 150)
GREY_MID    = ( 90, 110,  80)
GREY_DIM    = ( 48,  60,  44)

SEL_BG      = ( 10,  45,  10)   # selected row bg
SEL_BORDER  = ( 82, 196,  26)

PROGRESS_BG = (  8,  28,   8)
PROGRESS_FG = ( 82, 196,  26)

# ══════════════════════════════════════════════════════════════════════════════
class Screen(Enum):
    NOW_PLAYING   = auto()
    LIBRARY       = auto()
    QUEUE         = auto()
    PLAYLISTS     = auto()
    PLAYLIST_VIEW = auto()

class Repeat(Enum):
    OFF = auto()
    ALL = auto()
    ONE = auto()

# ── Helpers ────────────────────────────────────────────────────────────────────
def trunc(font, text, max_w):
    if font.size(text)[0] <= max_w:
        return text
    while text and font.size(text + "…")[0] > max_w:
        text = text[:-1]
    return text + "…"

def lerp_col(a, b, t):
    return tuple(int(a[i] + (b[i]-a[i])*t) for i in range(3))

MUSIC_EXTS = {".mp3", ".ogg", ".flac", ".wav", ".m4a", ".opus"}

def scan_music(base_dir):
    tracks = []
    base = Path(base_dir)
    if not base.exists():
        return tracks
    for f in sorted(base.rglob("*")):
        if f.suffix.lower() in MUSIC_EXTS:
            meta = {"path": str(f), "title": f.stem,
                    "artist": f.parent.name if f.parent != base else "Unknown",
                    "album":  f.parent.name if f.parent != base else ""}
            try:
                from mutagen import File as MFile
                mf = MFile(str(f))
                if mf and mf.tags:
                    t = mf.tags
                    def g(keys):
                        for k in keys:
                            v = t.get(k)
                            if v:
                                return str(v[0]) if hasattr(v,'__iter__') and not isinstance(v,str) else str(v)
                        return None
                    meta["title"]  = g(["TIT2","title","©nam"]) or meta["title"]
                    meta["artist"] = g(["TPE1","artist","©ART"]) or meta["artist"]
                    meta["album"]  = g(["TALB","album","©alb"])  or meta["album"]
            except Exception:
                pass
            tracks.append(meta)
    return tracks

def load_playlists(pl_dir):
    pls = {}
    p = Path(pl_dir)
    p.mkdir(parents=True, exist_ok=True)
    for f in sorted(p.glob("*.json")):
        try:
            with open(f) as fh:
                pls[f.stem] = json.load(fh)
        except Exception:
            pass
    return pls

# ══════════════════════════════════════════════════════════════════════════════
#  DRAWING PRIMITIVES  — bevel panels, glow circles, gradient fills
# ══════════════════════════════════════════════════════════════════════════════

def draw_vgradient(surf, rect, top_col, bot_col):
    """Vertical gradient fill into a Rect."""
    x, y, w, h = rect
    if h <= 0 or w <= 0:
        return
    for row in range(h):
        t = row / max(h - 1, 1)
        c = lerp_col(top_col, bot_col, t)
        pygame.draw.line(surf, c, (x, y + row), (x + w - 1, y + row))

def draw_hgradient(surf, rect, left_col, right_col):
    x, y, w, h = rect
    for col in range(w):
        t = col / max(w - 1, 1)
        c = lerp_col(left_col, right_col, t)
        pygame.draw.line(surf, c, (x + col, y), (x + col, y + h - 1))

def draw_bevel_rect(surf, rect, fill_top, fill_bot, bevel=2):
    """Gradient fill + bright top-left / dark bottom-right bevel."""
    x, y, w, h = rect
    draw_vgradient(surf, rect, fill_top, fill_bot)
    # bevel highlights
    for i in range(bevel):
        alpha = 1.0 - i / bevel
        hi = tuple(int(c * alpha) for c in CHROME_HI)
        sh = tuple(int(c * (0.3 * alpha)) for c in CHROME_DARK)
        pygame.draw.line(surf, hi, (x+i, y+i), (x+w-1-i, y+i))        # top
        pygame.draw.line(surf, hi, (x+i, y+i), (x+i, y+h-1-i))        # left
        pygame.draw.line(surf, sh, (x+i, y+h-1-i), (x+w-1-i, y+h-1-i))  # bottom
        pygame.draw.line(surf, sh, (x+w-1-i, y+i), (x+w-1-i, y+h-1-i))  # right

def draw_glow_circle(surf, cx, cy, r, col, steps=6):
    """Layered alpha circles faking a glow."""
    for i in range(steps, 0, -1):
        rr   = r + i * 3
        fade = int(40 * (i / steps) ** 2)
        gc   = (col[0], col[1], col[2], fade)
        tmp  = pygame.Surface((rr*2+2, rr*2+2), pygame.SRCALPHA)
        pygame.draw.circle(tmp, gc, (rr+1, rr+1), rr)
        surf.blit(tmp, (cx - rr - 1, cy - rr - 1), special_flags=pygame.BLEND_RGBA_ADD)

def draw_xbox_orb(surf, cx, cy, r, tick):
    """The iconic Xbox orb — layered gradients + spinning swoosh + X."""
    # outer glow
    draw_glow_circle(surf, cx, cy, r, XBOX_GREEN, steps=5)

    # body gradient: dark green → lime green radial-ish via vertical gradient
    body = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
    draw_vgradient(body, (0, 0, r*2, r*2), (20, 80, 10), (60, 180, 20))
    # clip to circle
    mask = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255,255,255,255), (r, r), r)
    body.blit(mask, (0,0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(body, (cx-r, cy-r))

    # specular highlight arc (top-left)
    spec = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
    for i in range(8):
        rr = r - i
        if rr <= 0: break
        a = max(0, 80 - i*12)
        pygame.draw.arc(spec, (200, 255, 160, a),
                        (r - rr, r - rr, rr*2, rr*2),
                        math.radians(100), math.radians(200), 2)
    surf.blit(spec, (cx-r, cy-r))

    # spinning swoosh lines (animated)
    for arm in range(4):
        base_ang = tick * 2.5 + arm * 90
        a1 = math.radians(base_ang)
        a2 = math.radians(base_ang + 40)
        x1 = cx + int((r - 4) * math.cos(a1))
        y1 = cy + int((r - 4) * math.sin(a1))
        x2 = cx + int((r - 4) * math.cos(a2))
        y2 = cy + int((r - 4) * math.sin(a2))
        fade = [XBOX_BRIGHT, XBOX_GREEN, XBOX_DIM, XBOX_PALE][arm]
        pygame.draw.line(surf, fade, (cx, cy), (x1, y1), 2)
        pygame.draw.line(surf, fade, (cx, cy), (x2, y2), 1)

    # X mark
    m = r // 3
    w = max(2, r // 5)
    pygame.draw.line(surf, WHITE, (cx-m, cy-m), (cx+m, cy+m), w)
    pygame.draw.line(surf, WHITE, (cx+m, cy-m), (cx-m, cy+m), w)
    # X specular
    pygame.draw.line(surf, XBOX_TOXIC, (cx-m, cy-m), (cx-m+2, cy-m+2), 1)

    # outer rim
    pygame.draw.circle(surf, XBOX_BRIGHT, (cx, cy), r, 1)
    pygame.draw.circle(surf, XBOX_DIM,    (cx, cy), r+1, 1)

def draw_scanlines(surf, alpha=18):
    """Subtle CRT scanlines over everything."""
    for y in range(0, SH, 2):
        sl = pygame.Surface((SW, 1), pygame.SRCALPHA)
        sl.fill((0, 0, 0, alpha))
        surf.blit(sl, (0, y))

def draw_bg(surf, tick):
    """Animated deep-green background with subtle radial glow pulse."""
    surf.fill(BG_DEEP)
    # pulsing bg glow from centre
    pulse = 0.5 + 0.5 * math.sin(tick * 0.04)
    r_bg = int(60 + pulse * 15)
    glow = pygame.Surface((r_bg*2, r_bg*2), pygame.SRCALPHA)
    for i in range(r_bg, 0, -4):
        a = int(12 * (i / r_bg) * pulse)
        pygame.draw.circle(glow, (30, 100, 10, a), (r_bg, r_bg), i)
    surf.blit(glow, (SW//2 - r_bg, SH//2 - r_bg), special_flags=pygame.BLEND_RGBA_ADD)

def draw_header_bar(surf, title, fnt_title, fnt_tiny, orb_r=9, tick=0):
    """Top bar: gradient panel + orb + title + nav dots."""
    draw_bevel_rect(surf, (0, 0, SW, 24), PANEL_LIT, PANEL_DARK, bevel=1)
    # thin bright line under header
    pygame.draw.line(surf, XBOX_GREEN, (0, 24), (SW, 24), 1)
    pygame.draw.line(surf, XBOX_DIM,   (0, 25), (SW, 25), 1)

    # mini orb
    draw_xbox_orb(surf, 12, 12, orb_r, tick)

    # title text with green shadow
    sh = fnt_title.render(title, True, XBOX_DIM)
    surf.blit(sh, (27, 6))
    ts = fnt_title.render(title, True, XBOX_BRIGHT)
    surf.blit(ts, (26, 5))

def draw_tab_bar(surf, current, fnt_tiny):
    """Bottom 16px — OG Xbox style tab indicators."""
    tabs = [("NOW", Screen.NOW_PLAYING),
            ("MUSIC", Screen.LIBRARY),
            ("QUEUE", Screen.QUEUE),
            ("LISTS", Screen.PLAYLISTS)]
    y = SH - 16
    draw_bevel_rect(surf, (0, y, SW, 16), PANEL_DARK, PANEL_MID, bevel=1)
    pygame.draw.line(surf, XBOX_GREEN, (0, y), (SW, y), 1)

    sw = SW // len(tabs)
    for i, (name, sid) in enumerate(tabs):
        active = (current == sid) or (current == Screen.PLAYLIST_VIEW and sid == Screen.PLAYLISTS)
        x = i * sw
        if active:
            draw_vgradient(surf, (x, y, sw, 16), XBOX_DIM, PANEL_MID)
            pygame.draw.line(surf, XBOX_GREEN, (x, y), (x+sw, y), 2)
            # notch
            pygame.draw.polygon(surf, XBOX_BRIGHT,
                [(x + sw//2 - 4, y), (x + sw//2 + 4, y), (x + sw//2, y + 4)])

        col = XBOX_BRIGHT if active else GREY_MID
        lbl = fnt_tiny.render(name, True, col)
        surf.blit(lbl, (x + sw//2 - lbl.get_width()//2, y + 3))
        # divider
        if i > 0:
            pygame.draw.line(surf, XBOX_DIM, (x, y+2), (x, y+14), 1)

def draw_progress(surf, x, y, w, h, frac, label_font, pos_str, dur_str):
    """Thick chunky Xbox-style progress bar with glow."""
    # track
    draw_bevel_rect(surf, (x, y, w, h), PROGRESS_BG, (0, 10, 0), bevel=1)
    if frac > 0:
        fw = max(h, int(w * min(frac, 1.0)))
        # fill gradient
        draw_hgradient(surf, (x, y, fw, h), XBOX_DIM, XBOX_GREEN)
        # bright leading edge
        pygame.draw.rect(surf, XBOX_BRIGHT, (x + fw - 2, y, 2, h))
        # glow on leading edge
        gx = x + fw
        for gi in range(4):
            ga = 60 - gi*15
            pygame.draw.line(surf, (XBOX_GREEN[0], XBOX_GREEN[1], XBOX_GREEN[2]), (gx+gi, y), (gx+gi, y+h-1))
    # time labels
    ps = label_font.render(pos_str, True, XBOX_BRIGHT)
    ds = label_font.render(dur_str, True, XBOX_PALE)
    surf.blit(ps, (x, y + h + 2))
    surf.blit(ds, (x + w - ds.get_width(), y + h + 2))

def draw_list_row(surf, rect, track, selected, playing, idx, fnt_sub, fnt_tiny):
    """Rich styled row for library/queue/playlist lists."""
    x, y, w, h = rect
    if selected:
        draw_bevel_rect(surf, rect, SEL_BG, (5, 30, 5), bevel=1)
        pygame.draw.line(surf, XBOX_BRIGHT, (x, y), (x, y+h-1), 3)
        # right arrow glyph
        ax = x + w - 10
        ay = y + h//2
        pygame.draw.polygon(surf, XBOX_GREEN, [(ax, ay-4), (ax+6, ay), (ax, ay+4)])
    else:
        if idx % 2 == 0:
            pygame.draw.rect(surf, (8, 22, 8), rect)
        else:
            pygame.draw.rect(surf, PANEL_DARK, rect)

    if playing:
        # animated sound bars icon
        for bi in range(3):
            bh = 3 + (bi * 2)
            pygame.draw.rect(surf, XBOX_GREEN, (x+4+bi*4, y+h-2-bh, 3, bh))

    # title
    tc = XBOX_BRIGHT if selected else OFF_WHITE
    ts = fnt_sub.render(trunc(fnt_sub, track["title"], w - 26), True, tc)
    surf.blit(ts, (x+14, y+2))
    # artist
    ac = XBOX_GREEN if selected else GREY_MID
    as_ = fnt_tiny.render(trunc(fnt_tiny, track["artist"], w - 26), True, ac)
    surf.blit(as_, (x+14, y+13))

def draw_scrollbar(surf, x, y, h, total, vis, scroll):
    if total <= vis:
        return
    draw_vgradient(surf, (x, y, 4, h), CHROME_DARK, PANEL_DARK)
    ratio  = vis / total
    th     = max(8, int(h * ratio))
    ty     = y + int((scroll / total) * h)
    draw_vgradient(surf, (x, ty, 4, th), XBOX_BRIGHT, XBOX_DIM)
    pygame.draw.rect(surf, XBOX_BRIGHT, (x, ty, 4, th), 1)


# ══════════════════════════════════════════════════════════════════════════════
#  PLAYER
# ══════════════════════════════════════════════════════════════════════════════
class MusicPlayer:
    ROWS_VIS = 8
    ROW_H    = 24

    def __init__(self, music_dir="music", pl_dir="playlists", window_mode=False):
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)

        # -- Display driver selection ------------------------------------------
        # window_mode=True  → always open a normal desktop/X11 window (SSH -X, VNC)
        # window_mode=False → auto: use fbcon when no DISPLAY is set (real Pi + SPI display)
        if window_mode:
            # Force SDL to use a real window; unset fbcon overrides if present
            os.environ.pop("SDL_VIDEODRIVER", None)
            os.environ.pop("SDL_FBDEV",       None)
        else:
            # On Pi with no X session available → write directly to framebuffer
            if os.path.exists("/dev/fb0") and "DISPLAY" not in os.environ:
                os.environ.setdefault("SDL_VIDEODRIVER", "fbcon")
                os.environ.setdefault("SDL_FBDEV", "/dev/fb1")
                os.environ.setdefault("SDL_MOUSEDRV", "TSLIB")

        self.surf  = pygame.display.set_mode((SW, SH))
        pygame.display.set_caption("Xbox Music")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()

        # Fonts — DejaVu is pre-installed on Raspbian
        self.fnt_title = pygame.font.SysFont("dejavusansbold",  13, bold=True)
        self.fnt_big   = pygame.font.SysFont("dejavusansbold",  15, bold=True)
        self.fnt_sub   = pygame.font.SysFont("dejavusans",      12)
        self.fnt_small = pygame.font.SysFont("dejavusans",      11)
        self.fnt_tiny  = pygame.font.SysFont("dejavusans",      10)

        # State
        self.library   = scan_music(music_dir)
        self.playlists = load_playlists(pl_dir)
        self.pl_dir    = pl_dir
        self.queue     = list(self.library)
        self.queue_idx = 0
        self.shuffle   = False
        self.repeat    = Repeat.OFF
        self.playing   = False
        self.paused    = False
        self.pos_sec   = 0.0
        self.duration  = 0.0
        self._last_t   = time.time()

        self.screen_id   = Screen.NOW_PLAYING
        self.cursor      = 0
        self.scroll      = 0
        self.sel_pl      = None
        self._pl_keys    = []

        self.tick        = 0
        self._toast_msg  = ""
        self._toast_t    = 0
        self._scroll_x   = 0       # title marquee
        self._scroll_dir = 1

        # GPIO
        self._gpio = self._init_gpio()
        self._prev_gpio = set()

        pygame.mixer.music.set_endevent(pygame.USEREVENT + 1)
        self.EV_END = pygame.USEREVENT + 1

        # Pre-bake scanlines surface
        self._scanlines = pygame.Surface((SW, SH), pygame.SRCALPHA)
        for y in range(0, SH, 2):
            pygame.draw.line(self._scanlines, (0, 0, 0, 22), (0, y), (SW, y))

        if self.library:
            self._load_track(0)

    # ── GPIO ──────────────────────────────────────────────────────────────────
    def _init_gpio(self):
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            for pin in (BTN_UP, BTN_DOWN, BTN_LEFT, BTN_RIGHT, BTN_OK):
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            return GPIO
        except Exception:
            return None

    def _read_gpio(self):
        if not self._gpio:
            return set()
        G = self._gpio
        pressed = set()
        if not G.input(BTN_UP):    pressed.add("UP")
        if not G.input(BTN_DOWN):  pressed.add("DOWN")
        if not G.input(BTN_LEFT):  pressed.add("LEFT")
        if not G.input(BTN_RIGHT): pressed.add("RIGHT")
        if not G.input(BTN_OK):    pressed.add("OK")
        return pressed

    # ── Track management ──────────────────────────────────────────────────────
    def _load_track(self, idx, autoplay=False):
        if not self.queue: return
        self.queue_idx = idx % len(self.queue)
        t = self.queue[self.queue_idx]
        try:
            pygame.mixer.music.load(t["path"])
            self.duration = self._get_dur(t["path"])
            self.pos_sec  = 0.0
            self._last_t  = time.time()
            self._scroll_x = 0
            if autoplay or self.playing:
                pygame.mixer.music.play()
                self.playing = True
                self.paused  = False
        except Exception as e:
            print(f"[load] {e}")

    def _get_dur(self, path):
        try:
            from mutagen import File as MF
            mf = MF(path)
            if mf and mf.info: return mf.info.length
        except Exception: pass
        try:
            snd = pygame.mixer.Sound(path)
            return snd.get_length()
        except Exception: return 0.0

    def play_pause(self):
        if not self.queue: return
        if self.playing and not self.paused:
            pygame.mixer.music.pause(); self.paused = True
        elif self.paused:
            pygame.mixer.music.unpause(); self.paused = False
        else:
            self._load_track(self.queue_idx, autoplay=True)

    def next_track(self):
        if not self.queue: return
        nxt = random.randint(0, len(self.queue)-1) if self.shuffle \
              else (self.queue_idx + 1) % len(self.queue)
        self._load_track(nxt, autoplay=True)

    def prev_track(self):
        if not self.queue: return
        if self.pos_sec > 3:
            pygame.mixer.music.rewind(); self.pos_sec = 0.0
        else:
            self._load_track((self.queue_idx - 1) % len(self.queue), autoplay=True)

    def add_to_queue(self, track):
        self.queue.append(track)
        self._toast(f"+QUEUE: {track['title'][:22]}")

    def _on_end(self):
        if self.repeat == Repeat.ONE:
            self._load_track(self.queue_idx, autoplay=True)
        elif self.repeat == Repeat.ALL or self.queue_idx < len(self.queue)-1:
            self.next_track()
        else:
            self.playing = False; self.paused = False

    def _toast(self, msg):
        self._toast_msg = msg
        self._toast_t   = FPS * 3

    def _update_pos(self):
        now = time.time()
        if self.playing and not self.paused:
            self.pos_sec += now - self._last_t
        self._last_t = now

    def _fmt(self, s):
        s = max(0, int(s))
        return f"{s//60}:{s%60:02d}"

    # ══════════════════════════════════════════════════════════════════════════
    #  SCREEN DRAWS
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_now_playing(self):
        s = self.surf
        draw_bg(s, self.tick)
        draw_header_bar(s, "MUSIC PLAYER", self.fnt_title, self.fnt_tiny,
                        orb_r=9, tick=self.tick)

        if not self.queue:
            msg = self.fnt_sub.render("NO MUSIC — drop files in /music", True, XBOX_PALE)
            s.blit(msg, (SW//2 - msg.get_width()//2, 100))
            draw_tab_bar(s, self.screen_id, self.fnt_tiny)
            return

        t = self.queue[self.queue_idx]

        # ── Big Xbox Orb ──────────────────────────────────────────────────
        orb_r = 30
        orb_cx, orb_cy = SW//2, 68
        draw_xbox_orb(s, orb_cx, orb_cy, orb_r, self.tick if (self.playing and not self.paused) else 0)

        # Pause indicator overlay
        if self.paused:
            for i, bx in enumerate([orb_cx - 6, orb_cx + 2]):
                pygame.draw.rect(s, WHITE, (bx, orb_cy - 8, 4, 16))

        # ── Track info panel ──────────────────────────────────────────────
        panel_y = 104
        draw_bevel_rect(s, (4, panel_y, SW-8, 38), PANEL_DARK, PANEL_MID, bevel=2)
        pygame.draw.rect(s, XBOX_GREEN, (4, panel_y, SW-8, 38), 1)

        # Marquee title
        title_full = t["title"]
        title_surf = self.fnt_big.render(title_full, True, XBOX_BRIGHT)
        max_w = SW - 20
        clip_rect = pygame.Rect(8, panel_y+4, max_w, 18)
        s.set_clip(clip_rect)
        if title_surf.get_width() > max_w:
            self._scroll_x += self._scroll_dir * 0.7
            if self._scroll_x > title_surf.get_width() - max_w + 10:
                self._scroll_dir = -1
            if self._scroll_x < 0:
                self._scroll_dir = 1
                self._scroll_x = 0
        s.blit(title_surf, (8 - int(self._scroll_x), panel_y + 4))
        s.set_clip(None)

        # Artist
        art_s = self.fnt_small.render(trunc(self.fnt_small, t["artist"], SW-20), True, XBOX_GREEN)
        s.blit(art_s, (8, panel_y + 22))

        # ── Progress bar ──────────────────────────────────────────────────
        frac = (self.pos_sec / self.duration) if self.duration > 0 else 0
        draw_progress(s, 8, 148, SW-16, 6, frac,
                      self.fnt_tiny, self._fmt(self.pos_sec), self._fmt(self.duration))

        # ── Controls row ──────────────────────────────────────────────────
        ctrl_y = 168
        draw_bevel_rect(s, (4, ctrl_y, SW-8, 28), PANEL_MID, PANEL_DARK, bevel=1)
        pygame.draw.rect(s, XBOX_DIM, (4, ctrl_y, SW-8, 28), 1)

        cx = SW // 2

        # Shuffle badge
        sh_bg = XBOX_DIM if self.shuffle else (10, 20, 10)
        sh_col = XBOX_BRIGHT if self.shuffle else GREY_DIM
        pygame.draw.rect(s, sh_bg, (cx-56, ctrl_y+4, 20, 18), border_radius=2)
        pygame.draw.rect(s, sh_col, (cx-56, ctrl_y+4, 20, 18), 1, border_radius=2)
        sh_s = self.fnt_tiny.render("SHF", True, sh_col)
        s.blit(sh_s, (cx-56 + 10 - sh_s.get_width()//2, ctrl_y + 8))

        # |<< button
        prev_s = self.fnt_big.render("◄◄", True, OFF_WHITE)
        s.blit(prev_s, (cx-34 - prev_s.get_width()//2, ctrl_y+4))

        # ▶/⏸ centre button (glowing)
        play_col = XBOX_BRIGHT if (self.playing and not self.paused) else CHROME_SPEC
        play_sym = "■" if (self.playing and not self.paused) else "►"
        # glow behind play button
        if self.playing and not self.paused:
            draw_glow_circle(s, cx, ctrl_y+14, 10, XBOX_GREEN, steps=3)
        pygame.draw.circle(s, PANEL_LIT, (cx, ctrl_y+14), 11)
        pygame.draw.circle(s, XBOX_GREEN, (cx, ctrl_y+14), 11, 1)
        play_s = self.fnt_big.render(play_sym, True, play_col)
        s.blit(play_s, (cx - play_s.get_width()//2, ctrl_y + 4))

        # >>| button
        next_s = self.fnt_big.render("►►", True, OFF_WHITE)
        s.blit(next_s, (cx+22 - next_s.get_width()//2, ctrl_y+4))

        # Repeat badge
        rep_names = {Repeat.OFF: "RPT", Repeat.ALL: "ALL", Repeat.ONE: "1× "}
        rp_bg  = XBOX_DIM if self.repeat != Repeat.OFF else (10, 20, 10)
        rp_col = XBOX_BRIGHT if self.repeat != Repeat.OFF else GREY_DIM
        pygame.draw.rect(s, rp_bg,  (cx+36, ctrl_y+4, 20, 18), border_radius=2)
        pygame.draw.rect(s, rp_col, (cx+36, ctrl_y+4, 20, 18), 1, border_radius=2)
        rp_s = self.fnt_tiny.render(rep_names[self.repeat], True, rp_col)
        s.blit(rp_s, (cx+36 + 10 - rp_s.get_width()//2, ctrl_y+8))

        # ── Queue count ───────────────────────────────────────────────────
        qc = self.fnt_tiny.render(f"Queue: {len(self.queue)} tracks", True, XBOX_PALE)
        s.blit(qc, (SW//2 - qc.get_width()//2, 199))

        draw_tab_bar(s, self.screen_id, self.fnt_tiny)

    def _draw_list_screen(self, title, items, extra_label=""):
        s = self.surf
        draw_bg(s, self.tick)
        draw_header_bar(s, title, self.fnt_title, self.fnt_tiny, orb_r=9, tick=0)

        y0 = 26
        row_h = self.ROW_H
        self._clamp(len(items))

        if not items:
            msg = self.fnt_sub.render("Nothing here", True, XBOX_PALE)
            s.blit(msg, (SW//2 - msg.get_width()//2, 110))
            draw_tab_bar(s, self.screen_id, self.fnt_tiny)
            return

        for i in range(self.ROWS_VIS):
            idx = self.scroll + i
            if idx >= len(items): break
            t   = items[idx]
            ry  = y0 + i * row_h
            if ry + row_h > SH - 16: break
            sel  = (idx == self.cursor)
            play = (idx == self.queue_idx and self.playing and
                    self.screen_id in (Screen.LIBRARY, Screen.QUEUE))
            draw_list_row(s, (0, ry, SW-6, row_h), t, sel, play, idx,
                          self.fnt_sub, self.fnt_tiny)

        draw_scrollbar(s, SW-5, y0, SH-16-y0, len(items), self.ROWS_VIS, self.scroll)
        draw_tab_bar(s, self.screen_id, self.fnt_tiny)

    def _draw_playlists_screen(self):
        s = self.surf
        draw_bg(s, self.tick)
        draw_header_bar(s, "PLAYLISTS", self.fnt_title, self.fnt_tiny, orb_r=9, tick=0)
        self._pl_keys = sorted(self.playlists.keys())

        y0    = 26
        row_h = 28
        ROWS  = 6
        self._clamp(len(self._pl_keys))

        if not self._pl_keys:
            msg = self.fnt_sub.render("No playlists found", True, XBOX_PALE)
            s.blit(msg, (SW//2 - msg.get_width()//2, 100))
            hint = self.fnt_tiny.render("Add JSON files to /playlists/", True, XBOX_DIM)
            s.blit(hint, (SW//2 - hint.get_width()//2, 118))
            draw_tab_bar(s, self.screen_id, self.fnt_tiny)
            return

        for i in range(ROWS):
            idx = self.scroll + i
            if idx >= len(self._pl_keys): break
            name  = self._pl_keys[idx]
            count = len(self.playlists[name])
            ry    = y0 + i * row_h
            sel   = (idx == self.cursor)

            if sel:
                draw_bevel_rect(s, (0, ry, SW-6, row_h), SEL_BG, (5,30,5), bevel=1)
                pygame.draw.line(s, XBOX_BRIGHT, (0, ry), (0, ry+row_h-1), 3)
            else:
                bg = (8, 22, 8) if idx%2==0 else PANEL_DARK
                pygame.draw.rect(s, bg, (0, ry, SW-6, row_h))

            # folder orb
            orb_c = XBOX_GREEN if sel else XBOX_DIM
            pygame.draw.circle(s, orb_c, (12, ry+row_h//2), 7)
            pygame.draw.circle(s, XBOX_BRIGHT if sel else XBOX_PALE, (12, ry+row_h//2), 7, 1)
            f_s = self.fnt_tiny.render("▶", True, WHITE)
            s.blit(f_s, (12 - f_s.get_width()//2 + 1, ry + row_h//2 - f_s.get_height()//2))

            nc = XBOX_BRIGHT if sel else OFF_WHITE
            ns = self.fnt_sub.render(trunc(self.fnt_sub, name, 170), True, nc)
            s.blit(ns, (24, ry + 4))
            cs = self.fnt_tiny.render(f"{count} tracks", True, XBOX_GREEN if sel else GREY_MID)
            s.blit(cs, (24, ry + 16))

        draw_scrollbar(s, SW-5, y0, ROWS*row_h, len(self._pl_keys), ROWS, self.scroll)
        draw_tab_bar(s, self.screen_id, self.fnt_tiny)

    # ── Toast overlay ─────────────────────────────────────────────────────────
    def _draw_toast(self):
        if self._toast_t <= 0: return
        s = self.surf
        alpha = min(255, self._toast_t * 15)
        tw = min(SW - 8, self.fnt_small.size(self._toast_msg)[0] + 16)
        th = 20
        tx = SW//2 - tw//2
        ty = SH - 38
        over = pygame.Surface((tw, th), pygame.SRCALPHA)
        draw_vgradient(over, (0, 0, tw, th), (10, 50, 10), (5, 25, 5))
        over.set_alpha(min(230, alpha))
        pygame.draw.rect(over, XBOX_GREEN, (0, 0, tw, th), 1)
        s.blit(over, (tx, ty))
        msg_s = self.fnt_small.render(self._toast_msg, True, XBOX_BRIGHT)
        s.blit(msg_s, (tx + tw//2 - msg_s.get_width()//2, ty + 3))

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _clamp(self, count):
        if count == 0: self.cursor = self.scroll = 0; return
        self.cursor = max(0, min(self.cursor, count-1))
        vis = self.ROWS_VIS
        if self.cursor < self.scroll: self.scroll = self.cursor
        elif self.cursor >= self.scroll + vis: self.scroll = self.cursor - vis + 1
        self.scroll = max(0, min(self.scroll, max(0, count - vis)))

    # ══════════════════════════════════════════════════════════════════════════
    #  INPUT
    # ══════════════════════════════════════════════════════════════════════════
    _KB = {
        pygame.K_UP: "UP", pygame.K_DOWN: "DOWN",
        pygame.K_LEFT: "LEFT", pygame.K_RIGHT: "RIGHT",
        pygame.K_RETURN: "OK", pygame.K_SPACE: "OK",
        pygame.K_KP_ENTER: "OK",
    }
    _KB_DEV = {pygame.K_n: "NEXT", pygame.K_p: "PREV"}

    def handle_btn(self, btn):
        sid = self.screen_id
        screens = [Screen.NOW_PLAYING, Screen.LIBRARY, Screen.QUEUE, Screen.PLAYLISTS]

        if btn == "LEFT":
            if sid == Screen.PLAYLIST_VIEW:
                self.screen_id = Screen.PLAYLISTS
                self.cursor = self._pl_keys.index(self.sel_pl) if self.sel_pl in self._pl_keys else 0
            else:
                i = screens.index(sid) if sid in screens else 0
                self.screen_id = screens[(i-1) % len(screens)]
                self.cursor = self.scroll = 0
            return

        if btn == "RIGHT":
            if sid == Screen.PLAYLIST_VIEW:
                self.screen_id = Screen.PLAYLISTS
                self.cursor = self._pl_keys.index(self.sel_pl) if self.sel_pl in self._pl_keys else 0
            else:
                i = screens.index(sid) if sid in screens else 0
                self.screen_id = screens[(i+1) % len(screens)]
                self.cursor = self.scroll = 0
            return

        if sid == Screen.NOW_PLAYING:
            if btn == "OK":
                self.play_pause()
            elif btn == "UP":
                self.shuffle = not self.shuffle
                self._toast("SHUFFLE " + ("ON" if self.shuffle else "OFF"))
            elif btn == "DOWN":
                modes = list(Repeat)
                self.repeat = modes[(modes.index(self.repeat)+1) % len(modes)]
                self._toast(f"REPEAT: {self.repeat.name}")

        elif sid in (Screen.LIBRARY, Screen.QUEUE):
            items = self.library if sid == Screen.LIBRARY else self.queue
            if btn == "UP":   self.cursor = max(0, self.cursor-1)
            elif btn == "DOWN": self.cursor = min(len(items)-1, self.cursor+1)
            elif btn == "OK":
                if not items: return
                if sid == Screen.LIBRARY:
                    self.queue = list(self.library)
                    self._load_track(self.cursor, autoplay=True)
                    self.screen_id = Screen.NOW_PLAYING
                else:
                    self._load_track(self.cursor, autoplay=True)
                    self.screen_id = Screen.NOW_PLAYING

        elif sid == Screen.PLAYLISTS:
            self._pl_keys = sorted(self.playlists.keys())
            if btn == "UP":   self.cursor = max(0, self.cursor-1)
            elif btn == "DOWN": self.cursor = min(len(self._pl_keys)-1, self.cursor+1)
            elif btn == "OK" and self._pl_keys:
                self.sel_pl = self._pl_keys[self.cursor]
                self.screen_id = Screen.PLAYLIST_VIEW
                self.cursor = self.scroll = 0

        elif sid == Screen.PLAYLIST_VIEW:
            pm = {t["path"]: t for t in self.library}
            pl_raw = self.playlists.get(self.sel_pl, [])
            items  = []
            for item in pl_raw:
                p = item if isinstance(item, str) else item.get("path","")
                items.append(pm.get(p, {"title": Path(p).stem, "artist":"", "path": p}))
            if btn == "UP":   self.cursor = max(0, self.cursor-1)
            elif btn == "DOWN": self.cursor = min(len(items)-1, self.cursor+1)
            elif btn == "OK" and items:
                self.add_to_queue(items[self.cursor])

    # ══════════════════════════════════════════════════════════════════════════
    #  MAIN LOOP
    # ══════════════════════════════════════════════════════════════════════════
    def run(self):
        while True:
            self.tick += 1
            self._update_pos()
            if self._toast_t > 0: self._toast_t -= 1

            # ── Events
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT: self._quit()
                elif ev.type == self.EV_END: self._on_end()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_q): self._quit()
                    elif ev.key in self._KB: self.handle_btn(self._KB[ev.key])
                    elif ev.key in self._KB_DEV:
                        act = self._KB_DEV[ev.key]
                        if act == "NEXT": self.next_track()
                        elif act == "PREV": self.prev_track()

            # ── GPIO
            cur = self._read_gpio()
            for btn in cur - self._prev_gpio:
                self.handle_btn(btn)
            self._prev_gpio = cur

            # ── Draw
            if self.screen_id == Screen.NOW_PLAYING:
                self._draw_now_playing()
            elif self.screen_id == Screen.LIBRARY:
                items = self.library
                self._draw_list_screen("MUSIC LIBRARY", items)
            elif self.screen_id == Screen.QUEUE:
                self._draw_list_screen(f"QUEUE  [{len(self.queue)}]", self.queue)
            elif self.screen_id == Screen.PLAYLISTS:
                self._draw_playlists_screen()
            elif self.screen_id == Screen.PLAYLIST_VIEW:
                pm = {t["path"]: t for t in self.library}
                pl_raw = self.playlists.get(self.sel_pl, [])
                items = []
                for item in pl_raw:
                    p = item if isinstance(item, str) else item.get("path","")
                    items.append(pm.get(p, {"title": Path(p).stem, "artist":"", "path":p}))
                self._draw_list_screen(f"▶ {(self.sel_pl or '')[:12]}", items)

            self.surf.blit(self._scanlines, (0, 0))
            self._draw_toast()
            pygame.display.flip()
            self.clock.tick(FPS)

    def _quit(self):
        pygame.mixer.music.stop()
        pygame.quit()
        sys.exit(0)


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="OG Xbox Music Player")
    ap.add_argument("--music",     default="music",      help="Music directory")
    ap.add_argument("--playlists", default="playlists",  help="Playlists directory")
    ap.add_argument("--window",    action="store_true",
                    help="Force a desktop window (use this for SSH -X / VNC testing)")
    args = ap.parse_args()
    MusicPlayer(music_dir=args.music, pl_dir=args.playlists, window_mode=args.window).run()
