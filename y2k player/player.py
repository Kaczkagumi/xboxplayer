#!/usr/bin/env python3
"""
INNIOASIS-COMPATIBLE MUSIC PLAYER
240x240 SPI display | python3-pygame | Raspberry Pi Zero W

Theme system: themes/<name>/
  config.json       — colours, font, wallpaper name
  desk_bg001.png    — main background (240x240)
  topbar.png        — top bar strip (240x26)
  sel_row.png       — selected row highlight (240x26)
  tab_bar.png       — bottom tab strip (240x22)
  tab_active.png    — active tab pill (48x20)
  btn_play.png      — play/pause button bg (44x44)
  btn_small.png     — small button bg (30x20)
  icon_now.png      — tab icon NOW (20x20)
  icon_lib.png      — tab icon LIB (20x20)
  icon_queue.png    — tab icon QUEUE (20x20)
  icon_lists.png    — tab icon LISTS (20x20)
  icon_opts.png     — tab icon OPT (20x20)
  cover.png         — options/preview bg (240x240)
  progress_bg.png   — progress bar track (220x8)
  progress_fill.png — progress bar fill tile (1x8)

If a PNG is missing, the engine draws it programmatically from the palette.
"""

import pygame, os, sys, json, time, random, math
from pathlib import Path
from enum import Enum, auto

SW, SH = 240, 240
FPS    = 30

BTN_UP    = 17
BTN_DOWN  = 27
BTN_LEFT  = 22
BTN_RIGHT = 23
BTN_OK    = 26

class Screen(Enum):
    NOW_PLAYING   = auto()
    LIBRARY       = auto()
    QUEUE         = auto()
    PLAYLISTS     = auto()
    PLAYLIST_VIEW = auto()
    OPTIONS       = auto()

class Repeat(Enum):
    OFF = auto()
    ALL = auto()
    ONE = auto()

# ══════════════════════════════════════════════════════════════════════════════
#  FALLBACK DRAW HELPERS  (used when PNGs are absent)
# ══════════════════════════════════════════════════════════════════════════════
def _lerp(a, b, t): return a + (b - a) * t
def _lc(a, b, t):   return tuple(int(_lerp(a[i], b[i], t)) for i in range(3))
def _clamp(v, lo, hi): return max(lo, min(hi, v))

def _vgrad(surf, rect, top, bot):
    x, y, w, h = rect
    if w <= 0 or h <= 0: return
    for i in range(h):
        t = i / max(h - 1, 1)
        pygame.draw.line(surf, _lc(top, bot, t), (x, y+i), (x+w-1, y+i))

def _hgrad(surf, rect, l, r):
    x, y, w, h = rect
    if w <= 0 or h <= 0: return
    for i in range(w):
        t = i / max(w - 1, 1)
        pygame.draw.line(surf, _lc(l, r, t), (x+i, y), (x+i, y+h-1))

def _pill(surf, rect, top, bot, border, radius=None):
    x, y, w, h = rect
    r = radius if radius is not None else h // 2
    tmp  = pygame.Surface((w, h), pygame.SRCALPHA)
    _vgrad(tmp, (0, 0, w, h), top, bot)
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255,255,255,255), (0,0,w,h), border_radius=r)
    tmp.blit(mask, (0,0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(tmp, (x, y))
    pygame.draw.rect(surf, border, (x,y,w,h), 1, border_radius=r)
    pygame.draw.line(surf, (200,200,200), (x+r, y+1), (x+w-r, y+1))

def _emboss(surf, rect, fill, radius=6, depth=2):
    x, y, w, h = rect
    pygame.draw.rect(surf, fill, (x,y,w,h), border_radius=radius)
    for i in range(depth):
        f = 1.0 - i/depth
        hi = (int(200*f), int(200*f), int(200*f))
        sh = (15, 15, 15)
        rr = radius // 2
        pygame.draw.line(surf, hi, (x+i+rr,y+i),(x+w-1-i-rr,y+i))
        pygame.draw.line(surf, hi, (x+i,y+i+rr),(x+i,y+h-1-i-rr))
        pygame.draw.line(surf, sh, (x+i+rr,y+h-1-i),(x+w-1-i-rr,y+h-1-i))
        pygame.draw.line(surf, sh, (x+w-1-i,y+i+rr),(x+w-1-i,y+h-1-i-rr))
    pygame.draw.rect(surf, (40,40,50), (x,y,w,h), 1, border_radius=radius)

def _sunken(surf, rect, fill, radius=4):
    x, y, w, h = rect
    pygame.draw.rect(surf, fill, (x,y,w,h), border_radius=radius)
    pygame.draw.line(surf, (15,15,15), (x+1,y+1),(x+w-2,y+1))
    pygame.draw.line(surf, (15,15,15), (x+1,y+1),(x+1,y+h-2))
    pygame.draw.line(surf, (80,80,100),(x+1,y+h-2),(x+w-2,y+h-2))
    pygame.draw.line(surf, (80,80,100),(x+w-2,y+1),(x+w-2,y+h-2))
    pygame.draw.rect(surf, (30,30,40), (x,y,w,h), 1, border_radius=radius)

def _glow_circle(surf, cx, cy, r, col, steps=5):
    for i in range(steps, 0, -1):
        rr = r + i*2
        a  = int(35*(i/steps)**2)
        tmp = pygame.Surface((rr*2+2,rr*2+2), pygame.SRCALPHA)
        pygame.draw.circle(tmp, (col[0],col[1],col[2],a), (rr+1,rr+1), rr)
        surf.blit(tmp,(cx-rr-1,cy-rr-1), special_flags=pygame.BLEND_RGBA_ADD)

def _led(surf, cx, cy, r, col, on=True):
    if on: _glow_circle(surf, cx, cy, r, col, 3)
    c = col if on else tuple(c//6 for c in col)
    pygame.draw.circle(surf, c, (cx,cy), r)
    if on: pygame.draw.circle(surf,(220,240,255),(cx-r//3,cy-r//3),max(1,r//3))

def _rivet(surf, cx, cy):
    pygame.draw.circle(surf,(40,45,55),(cx,cy),3)
    pygame.draw.circle(surf,(90,100,120),(cx,cy),3,1)
    pygame.draw.line(surf,(160,170,190),(cx-1,cy-1),(cx+1,cy+1),1)

# ══════════════════════════════════════════════════════════════════════════════
#  DEFAULT THEME ASSET GENERATOR
#  Builds every PNG in-memory so the player looks great with no files at all.
# ══════════════════════════════════════════════════════════════════════════════
class DefaultAssets:
    """Generates all theme surfaces programmatically in Y2K style."""

    # Y2K palette
    BG1    = (  6,   8,  20)
    BG2    = ( 10,  14,  32)
    PANEL  = ( 14,  20,  42)
    SUNKEN = (  4,   6,  16)
    C1     = (  0, 200, 255)   # cyan accent
    C2     = (180,  20, 220)   # magenta accent
    C_AMBER= (255, 170,  10)   # LCD amber
    C_DIM  = ( 30,  50,  80)
    CHI    = (190, 200, 220)
    CMI    = ( 90, 100, 120)
    CDK    = ( 25,  28,  40)
    WHITE  = (255, 255, 255)
    GREY   = (130, 145, 170)

    @classmethod
    def background(cls):
        surf = pygame.Surface((SW, SH))
        _vgrad(surf, (0,0,SW,SH), cls.BG1, cls.BG2)
        # subtle grid lines
        for x in range(0, SW, 24):
            pygame.draw.line(surf, (12,18,36), (x,0),(x,SH))
        for y in range(0, SH, 24):
            pygame.draw.line(surf, (12,18,36), (0,y),(SW,y))
        # corner glow
        for r in range(30, 0, -6):
            a = int(20*(r/30)**2)
            tmp = pygame.Surface((r*2,r*2), pygame.SRCALPHA)
            pygame.draw.circle(tmp,(cls.C1[0],cls.C1[1],cls.C1[2],a),(r,r),r)
            surf.blit(tmp,(SW//2-r,SH//2-r), special_flags=pygame.BLEND_RGBA_ADD)
        return surf

    @classmethod
    def topbar(cls):
        surf = pygame.Surface((SW, 26), pygame.SRCALPHA)
        _vgrad(surf, (0,0,SW,26),
               _lc(cls.PANEL, cls.C1, 0.18),
               cls.PANEL)
        # bottom accent lines
        pygame.draw.line(surf, cls.C1,   (0,24),(SW,24),1)
        pygame.draw.line(surf, cls.C2,   (0,25),(SW,25),1)
        # left LED strip
        for i,c in enumerate([cls.C1, cls.C2, cls.C_AMBER]):
            _led(surf, 8+i*10, 13, 3, c, on=True)
        # rivets
        _rivet(surf, SW-8, 6)
        _rivet(surf, SW-8, 20)
        return surf

    @classmethod
    def sel_row(cls, h=26):
        surf = pygame.Surface((SW, h), pygame.SRCALPHA)
        # translucent tinted fill
        fill = pygame.Surface((SW, h), pygame.SRCALPHA)
        _vgrad(fill,(0,0,SW,h), (0,60,100,180),(0,30,60,160))
        surf.blit(fill,(0,0))
        # left accent bar
        _vgrad(surf,(0,0,3,h), cls.C1, cls.C2)
        # top + bottom lines
        pygame.draw.line(surf, (cls.C1[0],cls.C1[1],cls.C1[2],200),(0,0),(SW,0),1)
        pygame.draw.line(surf, (cls.C2[0],cls.C2[1],cls.C2[2],120),(0,h-1),(SW,h-1),1)
        return surf

    @classmethod
    def tab_bar(cls):
        surf = pygame.Surface((SW, 22), pygame.SRCALPHA)
        _vgrad(surf,(0,0,SW,22), cls.PANEL, cls.BG1)
        pygame.draw.line(surf, cls.C1, (0,0),(SW,0),1)
        pygame.draw.line(surf, cls.C2, (0,1),(SW,1),1)
        return surf

    @classmethod
    def tab_active(cls, w=46, h=20):
        surf = pygame.Surface((w,h), pygame.SRCALPHA)
        _pill(surf,(0,0,w,h),
              _lc(cls.PANEL,cls.C1,0.35),
              cls.PANEL, cls.C1, radius=h//2)
        # notch on top
        pygame.draw.polygon(surf, cls.C1,
            [(w//2-4,0),(w//2+4,0),(w//2,4)])
        return surf

    @classmethod
    def btn_play(cls, size=44):
        surf = pygame.Surface((size,size), pygame.SRCALPHA)
        r    = size//2
        _glow_circle(surf, r, r, r-4, cls.C1, 4)
        # outer ring gradient
        for i in range(r, r-4, -1):
            t = 1-(i-r+4)/4
            pygame.draw.circle(surf, _lc(cls.CMI,cls.CHI,t),(r,r),i,1)
        # inner fill
        _vgrad_circle(surf, r, r, r-4, _lc(cls.PANEL,cls.C1,0.25), cls.PANEL)
        pygame.draw.circle(surf, cls.C1, (r,r), r-3, 1)
        return surf

    @classmethod
    def btn_small(cls, w=30, h=20):
        surf = pygame.Surface((w,h), pygame.SRCALPHA)
        _pill(surf,(0,0,w,h),
              _lc(cls.CDK,cls.CMI,0.4), cls.CDK,
              cls.CMI, radius=h//2)
        return surf

    @classmethod
    def icon(cls, mode, size=20):
        """Draw a simple icon for each tab mode."""
        surf = pygame.Surface((size,size), pygame.SRCALPHA)
        c    = cls.C1
        cx   = size//2
        if mode=="now":
            # music note
            pygame.draw.rect(surf,c,(cx-2,cx-6,4,10),border_radius=1)
            pygame.draw.rect(surf,c,(cx+3,cx-8,4,8),border_radius=1)
            pygame.draw.line(surf,c,(cx+2,cx-6),(cx+6,cx-8),2)
            pygame.draw.circle(surf,c,(cx-2,cx+4),3)
            pygame.draw.circle(surf,c,(cx+5,cx+2),3)
        elif mode=="lib":
            # stack of lines
            for i in range(4):
                pygame.draw.line(surf,c,(3,6+i*4),(size-3,6+i*4),2)
        elif mode=="queue":
            # numbered list
            for i in range(3):
                pygame.draw.line(surf,c,(7,6+i*5),(size-3,6+i*5),2)
            pygame.draw.circle(surf,c,(4,6),2)
            pygame.draw.circle(surf,c,(4,11),2)
            pygame.draw.circle(surf,c,(4,16),2)
        elif mode=="lists":
            # folder shape
            pygame.draw.rect(surf,c,(2,9,size-4,9),border_radius=2)
            pygame.draw.polygon(surf,c,[(2,9),(2,5),(8,5),(10,9)])
        elif mode=="opts":
            # gear
            for i in range(6):
                a = math.radians(i*60)
                x1=int(cx+5*math.cos(a)); y1=int(cx+5*math.sin(a))
                x2=int(cx+8*math.cos(a)); y2=int(cx+8*math.sin(a))
                pygame.draw.line(surf,c,(x1,y1),(x2,y2),2)
            pygame.draw.circle(surf,c,(cx,cx),4,2)
        return surf

    @classmethod
    def progress_bg(cls, w=220, h=8):
        surf = pygame.Surface((w,h), pygame.SRCALPHA)
        _sunken(surf,(0,0,w,h),(4,8,18),radius=4)
        return surf

    @classmethod
    def progress_fill(cls, h=8):
        surf = pygame.Surface((4,h))
        _vgrad(surf,(0,0,4,h),cls.C2,cls.C1)
        return surf


def _vgrad_circle(surf, cx, cy, r, top, bot):
    """Gradient-fill a circle clipped region."""
    for row in range(-r, r+1):
        half = int(math.sqrt(max(0, r*r - row*row)))
        t    = (row + r) / max(2*r, 1)
        c    = _lc(top, bot, t)
        pygame.draw.line(surf, c, (cx-half, cy+row), (cx+half, cy+row))


# ══════════════════════════════════════════════════════════════════════════════
#  THEME ENGINE  (Innioasis-compatible + extended slots)
# ══════════════════════════════════════════════════════════════════════════════
class Theme:
    def __init__(self, path):
        self.path = Path(path)
        self.cfg  = {
            "name":             self.path.name,
            "desktopWallpaper": "desk_bg001.png",
            "fontFamily":       None,
            "textColor":        "#FFFFFF",
            "selectColor":      "#00CCFF",
            "accentColor":      "#BB14DC",
            "dimColor":         "#445566",
        }
        cfg_file = self.path / "config.json"
        if cfg_file.exists():
            try:
                with open(cfg_file,'r',encoding='utf-8') as f:
                    self.cfg.update(json.load(f))
            except Exception as e:
                print(f"[theme] config.json error: {e}")

        self.txt_col    = self._pc(self.cfg.get("textColor",   "#FFFFFF"))
        self.sel_col    = self._pc(self.cfg.get("selectColor", "#00CCFF"))
        self.acc_col    = self._pc(self.cfg.get("accentColor", "#BB14DC"))
        self.dim_col    = self._pc(self.cfg.get("dimColor",    "#445566"))

        # ── Load or generate every asset ───────────────────────────────────
        bg_name = self.cfg.get("desktopWallpaper","desk_bg001.png")
        self.bg          = self._img(bg_name,        (SW,SH),   DefaultAssets.background)
        self.topbar      = self._img("topbar.png",   (SW,26),   DefaultAssets.topbar)
        self.sel_row     = self._img("sel_row.png",  (SW,26),   DefaultAssets.sel_row)
        self.tab_bar     = self._img("tab_bar.png",  (SW,22),   DefaultAssets.tab_bar)
        self.tab_active  = self._img("tab_active.png",(46,20),  DefaultAssets.tab_active)
        self.btn_play    = self._img("btn_play.png", (44,44),   DefaultAssets.btn_play)
        self.btn_small   = self._img("btn_small.png",(30,20),   DefaultAssets.btn_small)
        self.prog_bg     = self._img("progress_bg.png",(220,8), DefaultAssets.progress_bg)
        self.prog_fill   = self._img("progress_fill.png",(4,8), DefaultAssets.progress_fill)
        self.cover       = self._img("cover.png",    (SW,SH),   DefaultAssets.background)

        # Tab icons
        self.icons = {
            "now":   self._img("icon_now.png",   (20,20), lambda: DefaultAssets.icon("now")),
            "lib":   self._img("icon_lib.png",   (20,20), lambda: DefaultAssets.icon("lib")),
            "queue": self._img("icon_queue.png", (20,20), lambda: DefaultAssets.icon("queue")),
            "lists": self._img("icon_lists.png", (20,20), lambda: DefaultAssets.icon("lists")),
            "opts":  self._img("icon_opts.png",  (20,20), lambda: DefaultAssets.icon("opts")),
        }

        # ── Fonts ──────────────────────────────────────────────────────────
        font_file = self.cfg.get("fontFamily")
        if not font_file or not (self.path/font_file).exists():
            ttfs = list(self.path.glob("*.ttf"))
            font_file = ttfs[0].name if ttfs else None
        fs = int(self.cfg.get("fontSize", 13))
        if font_file:
            try:
                fp = str(self.path/font_file)
                self.fnt_main  = pygame.font.Font(fp, fs)
                self.fnt_sub   = pygame.font.Font(fp, max(10, fs-2))
                self.fnt_small = pygame.font.Font(fp, max(9,  fs-3))
                self.fnt_big   = pygame.font.Font(fp, fs+2)
                self.fnt_mono  = pygame.font.Font(fp, fs)
            except:
                self._sys_fonts(fs)
        else:
            self._sys_fonts(fs)

    def _sys_fonts(self, fs):
        self.fnt_main  = pygame.font.SysFont("dejavusans",     fs)
        self.fnt_sub   = pygame.font.SysFont("dejavusans",     max(10,fs-2))
        self.fnt_small = pygame.font.SysFont("dejavusans",     max(9, fs-3))
        self.fnt_big   = pygame.font.SysFont("dejavusansbold", fs+2, bold=True)
        self.fnt_mono  = pygame.font.SysFont("dejavusansmono", fs)

    def _pc(self, c):
        if isinstance(c,list) and len(c)>=3: return tuple(c[:3])
        if isinstance(c,str):
            c = c.strip().lstrip('#')
            if len(c)==6:
                return tuple(int(c[i:i+2],16) for i in (0,2,4))
        return (255,255,255)

    def _img(self, name, size, fallback_fn):
        p = self.path/name
        if p.exists():
            try:
                return pygame.transform.scale(
                    pygame.image.load(str(p)).convert_alpha(), size)
            except Exception as e:
                print(f"[theme] {name}: {e}")
        return pygame.transform.scale(fallback_fn(), size)


def load_themes(themes_dir="themes"):
    p = Path(themes_dir)
    p.mkdir(exist_ok=True)
    themes = [Theme(d) for d in sorted(p.iterdir()) if d.is_dir()]
    if not themes:
        (p/"Default").mkdir(exist_ok=True)
        themes.append(Theme(p/"Default"))
    return themes


# ══════════════════════════════════════════════════════════════════════════════
#  MUSIC HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def trunc(font, text, max_w):
    if font.size(text)[0] <= max_w: return text
    while text and font.size(text+"…")[0] > max_w: text = text[:-1]
    return text+"…"

def scan_music(base_dir):
    EXTS = {".mp3",".ogg",".flac",".wav",".m4a",".opus"}
    tracks = []
    base = Path(base_dir)
    if not base.exists(): return tracks
    for f in sorted(base.rglob("*")):
        if f.suffix.lower() not in EXTS: continue
        meta = {"path":str(f),"title":f.stem,
                "artist":f.parent.name if f.parent!=base else "Unknown"}
        try:
            from mutagen import File as MF
            mf = MF(str(f))
            if mf and mf.tags:
                def g(keys):
                    for k in keys:
                        if k in mf.tags:
                            v = mf.tags[k]
                            return str(v[0]) if hasattr(v,'__iter__') and not isinstance(v,str) else str(v)
                meta["title"]  = g(["TIT2","title","©nam"]) or meta["title"]
                meta["artist"] = g(["TPE1","artist","©ART"]) or meta["artist"]
        except: pass
        tracks.append(meta)
    return tracks

def load_playlists(pl_dir):
    pls = {}
    p = Path(pl_dir)
    p.mkdir(parents=True, exist_ok=True)
    for f in sorted(p.glob("*.json")):
        try:
            with open(f) as fh: pls[f.stem] = json.load(fh)
        except: pass
    return pls


# ══════════════════════════════════════════════════════════════════════════════
#  PLAYER
# ══════════════════════════════════════════════════════════════════════════════
DEFAULT_OPTIONS = {
    "scanlines": True, "iridescence": True,
    "volume": 80, "eq_preset": 0, "crossfade": False,
}
EQ_PRESETS = ["Flat","Bass Boost","Treble","Vocal","Rock","Electronic"]

class MusicPlayer:
    ROWS_VIS = 7
    ROW_H    = 26

    def __init__(self, music_dir="music", pl_dir="playlists",
                 themes_dir="themes", window_mode=False):
        pygame.init()
        try:
            pygame.mixer.init(frequency=44100,size=-16,channels=2,buffer=2048)
            self._audio_ok = True
        except pygame.error as e:
            print(f"[audio] No device ({e}) — silent mode")
            os.environ["SDL_AUDIODRIVER"] = "dummy"
            try: pygame.mixer.init()
            except: pass
            self._audio_ok = False

        if window_mode:
            os.environ.pop("SDL_VIDEODRIVER",None)
            os.environ.pop("SDL_FBDEV",None)
        else:
            if os.path.exists("/dev/fb0") and "DISPLAY" not in os.environ:
                os.environ.setdefault("SDL_VIDEODRIVER","fbcon")
                os.environ.setdefault("SDL_FBDEV","/dev/fb1")
                os.environ.setdefault("SDL_MOUSEDRV","TSLIB")

        self.surf  = pygame.display.set_mode((SW,SH))
        pygame.display.set_caption("Music Player")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()

        self.themes    = load_themes(themes_dir)
        self.theme_idx = 0
        self.th        = self.themes[self.theme_idx]

        self.library   = scan_music(music_dir)
        self.playlists = load_playlists(pl_dir)
        self.queue     = list(self.library)
        self.queue_idx = 0
        self.shuffle   = False
        self.repeat    = Repeat.OFF
        self.playing   = False
        self.paused    = False
        self.pos_sec   = 0.0
        self.duration  = 0.0
        self._last_t   = time.time()
        self.options   = dict(DEFAULT_OPTIONS)
        self._opt_cur  = 0

        self.screen_id = Screen.NOW_PLAYING
        self.cursor    = 0
        self.scroll    = 0
        self.sel_pl    = None
        self._pl_keys  = []

        self._gpio      = self._init_gpio()
        self._prev_gpio = set()
        self._scroll_x  = 0
        self._scroll_dir= 1
        self.tick       = 0
        self._toast_msg = ""
        self._toast_t   = 0

        # Fake VU bars
        self._vu      = [0.0]*8
        self._vu_peak = [0.0]*8

        # Scanline overlay
        self._scanlines = pygame.Surface((SW,SH),pygame.SRCALPHA)
        for y in range(0,SH,2):
            pygame.draw.line(self._scanlines,(0,0,0,26),(0,y),(SW,y))

        pygame.mixer.music.set_endevent(pygame.USEREVENT+1)
        self.EV_END = pygame.USEREVENT+1
        if self.library: self._load_track(0)

    # ── GPIO ──────────────────────────────────────────────────────────────────
    def _init_gpio(self):
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            for p in (BTN_UP,BTN_DOWN,BTN_LEFT,BTN_RIGHT,BTN_OK):
                GPIO.setup(p,GPIO.IN,pull_up_down=GPIO.PUD_UP)
            return GPIO
        except: return None

    def _read_gpio(self):
        if not self._gpio: return set()
        G=self._gpio; p=set()
        if not G.input(BTN_UP):    p.add("UP")
        if not G.input(BTN_DOWN):  p.add("DOWN")
        if not G.input(BTN_LEFT):  p.add("LEFT")
        if not G.input(BTN_RIGHT): p.add("RIGHT")
        if not G.input(BTN_OK):    p.add("OK")
        return p

    # ── Track ─────────────────────────────────────────────────────────────────
    def _load_track(self, idx, autoplay=False):
        if not self.queue: return
        self.queue_idx = idx % len(self.queue)
        t = self.queue[self.queue_idx]
        try:
            from mutagen import File as MF
            mf = MF(t["path"])
            self.duration = mf.info.length if mf and mf.info else 0.0
        except: self.duration = 0.0
        self.pos_sec  = 0.0
        self._scroll_x= 0
        self._last_t  = time.time()
        if self._audio_ok:
            try: pygame.mixer.music.load(t["path"])
            except Exception as e: print(f"[load] {e}")
        if (autoplay or self.playing) and self._audio_ok:
            try: pygame.mixer.music.play()
            except: pass
        self.playing = autoplay or self.playing
        self.paused  = False

    def play_pause(self):
        if not self.queue: return
        if self.playing and not self.paused:
            if self._audio_ok: pygame.mixer.music.pause()
            self.paused = True
        elif self.paused:
            if self._audio_ok: pygame.mixer.music.unpause()
            self.paused = False
        else: self._load_track(self.queue_idx,autoplay=True)

    def next_track(self):
        if not self.queue: return
        nxt = random.randint(0,len(self.queue)-1) if self.shuffle \
              else (self.queue_idx+1)%len(self.queue)
        self._load_track(nxt,autoplay=True)

    def prev_track(self):
        if not self.queue: return
        if self.pos_sec > 3:
            if self._audio_ok: pygame.mixer.music.rewind()
            self.pos_sec = 0.0
        else: self._load_track((self.queue_idx-1)%len(self.queue),autoplay=True)

    def add_to_queue(self,track):
        self.queue.append(track)
        self._toast(f"+Q  {track['title'][:20]}")

    def _clamp(self, count):
        if count==0: self.cursor=self.scroll=0; return
        self.cursor=_clamp(self.cursor,0,count-1)
        vis=self.ROWS_VIS
        if self.cursor<self.scroll: self.scroll=self.cursor
        elif self.cursor>=self.scroll+vis: self.scroll=self.cursor-vis+1
        self.scroll=_clamp(self.scroll,0,max(0,count-vis))

    def _fmt(self,s):
        s=max(0,int(s)); return f"{s//60}:{s%60:02d}"

    def _toast(self,msg):
        self._toast_msg=msg; self._toast_t=FPS*3

    def _upd_vu(self):
        for i in range(8):
            if self.playing and not self.paused:
                tgt = _clamp(random.gauss(0.55,0.25),0.04,1.0)
                self._vu[i]      = _lerp(self._vu[i],tgt,0.35)
                self._vu_peak[i] = max(self._vu[i],self._vu_peak[i]-0.015)
            else:
                self._vu[i]      = _lerp(self._vu[i],0.0,0.1)
                self._vu_peak[i] = max(0,self._vu_peak[i]-0.02)

    # ══════════════════════════════════════════════════════════════════════════
    #  RENDERING
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_topbar(self, title):
        th = self.th
        self.surf.blit(th.topbar,(0,0))
        # title centred
        ts = th.fnt_sub.render(title, True, th.txt_col)
        self.surf.blit(ts,(SW//2-ts.get_width()//2, 5))
        # status LEDs (redrawn over topbar image so positions are consistent)
        _led(self.surf, SW-22, 13, 3, th.sel_col,
             on=self.playing and not self.paused)
        _led(self.surf, SW-12, 13, 3, (255,100,20),
             on=self.paused)

    def _draw_tabs(self):
        th   = self.th
        tabs = [("NOW",Screen.NOW_PLAYING,"now"),
                ("LIB",Screen.LIBRARY,"lib"),
                ("QUE",Screen.QUEUE,"queue"),
                ("PLS",Screen.PLAYLISTS,"lists"),
                ("OPT",Screen.OPTIONS,"opts")]
        y   = SH-22
        sw  = SW//len(tabs)

        self.surf.blit(th.tab_bar,(0,y))

        for i,(name,sid,icon_key) in enumerate(tabs):
            active = (self.screen_id==sid) or \
                     (self.screen_id==Screen.PLAYLIST_VIEW and sid==Screen.PLAYLISTS)
            x = i*sw

            if active:
                self.surf.blit(
                    pygame.transform.scale(th.tab_active,(sw-2,20)),
                    (x+1,y+1))

            # Icon
            ico = th.icons.get(icon_key)
            if ico:
                ico_x = x+sw//2-ico.get_width()//2
                ico_y = y+1
                self.surf.blit(ico,(ico_x,ico_y))
            else:
                col = th.sel_col if active else th.dim_col
                lbl = th.fnt_small.render(name,True,col)
                self.surf.blit(lbl,(x+sw//2-lbl.get_width()//2,y+4))

            if active:
                pygame.draw.line(self.surf,th.sel_col,(x,y),(x+sw,y),2)

            if i>0:
                pygame.draw.line(self.surf,th.dim_col,(x,y+3),(x,y+19),1)

    # ── NOW PLAYING ───────────────────────────────────────────────────────────
    def _draw_now_playing(self):
        th = self.th
        s  = self.surf
        s.blit(th.bg,(0,0))
        self._draw_topbar("NOW PLAYING")

        if not self.queue:
            msg = th.fnt_main.render("No music in /music/",True,th.dim_col)
            s.blit(msg,(SW//2-msg.get_width()//2,SH//2-8))
            self._draw_tabs(); return

        t = self.queue[self.queue_idx]

        # ── VU meter strip ────────────────────────────────────────────────
        vu_y = 28
        _sunken(s,(8,vu_y,SW-16,28),(4,6,16),radius=4)
        bw = (SW-20)//8
        for i in range(8):
            bx = 10+i*bw
            seg_h = 24
            for j in range(seg_h//3):
                sy  = vu_y+2+(seg_h-3-(j*3))
                t_v = j/(seg_h//3-1) if seg_h//3>1 else 0
                if t_v < 0.6:
                    c = _lc((40,220,100),(200,255,40),t_v/0.6)
                else:
                    c = _lc((200,255,40),(255,50,40),(t_v-0.6)/0.4)
                lit = (j/(seg_h//3)) < self._vu[i]
                a   = 210 if lit else 28
                seg = pygame.Surface((bw-2,2),pygame.SRCALPHA)
                seg.fill((c[0],c[1],c[2],a))
                s.blit(seg,(bx+1,sy))
            # peak
            py_v = vu_y+2+int((1.0-self._vu_peak[i])*seg_h)
            pygame.draw.rect(s,(255,255,120),(bx+1,py_v,bw-2,2))

        # ── Track info panel ──────────────────────────────────────────────
        panel_y = 60
        _emboss(s,(8,panel_y,SW-16,36),DefaultAssets.PANEL,radius=6,depth=2)
        pygame.draw.rect(s,th.sel_col,(8,panel_y,SW-16,36),1,border_radius=6)

        # Marquee title
        t_data = self.queue[self.queue_idx]
        title_s = th.fnt_big.render(t_data["title"],True,th.txt_col)
        max_w   = SW-24
        clip    = pygame.Rect(10,panel_y+3,max_w,18)
        s.set_clip(clip)
        if title_s.get_width() > max_w:
            self._scroll_x += self._scroll_dir*0.8
            if self._scroll_x > title_s.get_width()-max_w+10: self._scroll_dir=-1
            if self._scroll_x < 0: self._scroll_dir=1; self._scroll_x=0
        s.blit(title_s,(10-int(self._scroll_x),panel_y+3))
        s.set_clip(None)

        art_s = th.fnt_sub.render(
            trunc(th.fnt_sub,t_data["artist"],max_w),True,th.dim_col)
        s.blit(art_s,(10,panel_y+22))

        # ── LCD time ──────────────────────────────────────────────────────
        lcd_y = 100
        _sunken(s,(8,lcd_y,SW-16,20),(4,6,16),radius=4)
        pos_s = th.fnt_mono.render(self._fmt(self.pos_sec),True,
                                    DefaultAssets.C_AMBER)
        dur_s = th.fnt_mono.render(self._fmt(self.duration),True,
                                    _lc(DefaultAssets.C_AMBER,DefaultAssets.SUNKEN,0.55))
        sep_s = th.fnt_small.render("/",True,DefaultAssets.C_DIM)
        s.blit(pos_s,(12,lcd_y+2))
        s.blit(sep_s,(SW//2-sep_s.get_width()//2,lcd_y+4))
        s.blit(dur_s,(SW-12-dur_s.get_width(),lcd_y+2))

        # ── Progress bar ──────────────────────────────────────────────────
        pb_y = 124
        s.blit(th.prog_bg,(10,pb_y))
        if self.duration > 0:
            fw = _clamp(int(220*(self.pos_sec/self.duration)),0,220)
            if fw > 0:
                fill_tile = th.prog_fill
                tile_w    = fill_tile.get_width()
                for tx in range(0,fw,tile_w):
                    sw2 = min(tile_w, fw-tx)
                    s.blit(fill_tile,(10+tx,pb_y),pygame.Rect(0,0,sw2,8))
                # leading bright pixel
                s.blit(pygame.Surface((3,8)), (10+fw-1,pb_y))
                pygame.draw.rect(s,(220,240,255),(10+fw-1,pb_y,3,8))

        # ── Controls ──────────────────────────────────────────────────────
        ctrl_y = 136
        _emboss(s,(8,ctrl_y,SW-16,34),DefaultAssets.PANEL,radius=8,depth=2)

        cx = SW//2
        # Shuffle pill
        sh_on = self.shuffle
        s.blit(pygame.transform.scale(th.btn_small,(28,18)),(cx-66,ctrl_y+8))
        sh_s = th.fnt_small.render("SHF",True,th.sel_col if sh_on else th.dim_col)
        s.blit(sh_s,(cx-66+14-sh_s.get_width()//2,ctrl_y+11))
        _led(s,cx-55,ctrl_y+8,3,th.sel_col,on=sh_on)

        # Prev
        s.blit(pygame.transform.scale(th.btn_small,(28,18)),(cx-36,ctrl_y+8))
        prev_s = th.fnt_sub.render("◄◄",True,(200,210,230))
        s.blit(prev_s,(cx-36+14-prev_s.get_width()//2,ctrl_y+11))

        # Play/Pause (big)
        is_playing = self.playing and not self.paused
        btn_play   = pygame.transform.scale(th.btn_play,(36,34))
        s.blit(btn_play,(cx-18,ctrl_y))
        if is_playing:
            # Pause bars
            pygame.draw.rect(s,(220,235,255),(cx-8,ctrl_y+8,6,16))
            pygame.draw.rect(s,(220,235,255),(cx+2,ctrl_y+8,6,16))
        else:
            pts=[(cx-5,ctrl_y+8),(cx-5,ctrl_y+24),(cx+12,ctrl_y+16)]
            pygame.draw.polygon(s,(220,235,255),pts)
        if is_playing:
            _led(s,cx,ctrl_y+2,3,th.sel_col,on=True)

        # Next
        s.blit(pygame.transform.scale(th.btn_small,(28,18)),(cx+10,ctrl_y+8))
        next_s = th.fnt_sub.render("►►",True,(200,210,230))
        s.blit(next_s,(cx+10+14-next_s.get_width()//2,ctrl_y+11))

        # Repeat pill
        rep_on  = self.repeat!=Repeat.OFF
        rep_sym = {"OFF":"RPT","ALL":"ALL","ONE":"1×"}[self.repeat.name]
        s.blit(pygame.transform.scale(th.btn_small,(28,18)),(cx+40,ctrl_y+8))
        rp_s = th.fnt_small.render(rep_sym,True,th.acc_col if rep_on else th.dim_col)
        s.blit(rp_s,(cx+40+14-rp_s.get_width()//2,ctrl_y+11))
        _led(s,cx+51,ctrl_y+8,3,th.acc_col,on=rep_on)

        # ── Info strip ────────────────────────────────────────────────────
        inf_y = 174
        _sunken(s,(8,inf_y,SW-16,14),(4,6,16),radius=4)
        eq   = EQ_PRESETS[self.options["eq_preset"]]
        vol  = self.options["volume"]
        eq_s = th.fnt_small.render(f"EQ:{eq}",True,th.sel_col)
        vl_s = th.fnt_small.render(f"VOL:{vol}%",True,DefaultAssets.C_AMBER)
        qi_s = th.fnt_small.render(
            f"{self.queue_idx+1}/{len(self.queue)}",True,th.dim_col)
        s.blit(eq_s,(11,inf_y+2))
        s.blit(qi_s,(SW//2-qi_s.get_width()//2,inf_y+2))
        s.blit(vl_s,(SW-11-vl_s.get_width(),inf_y+2))

        # ── Volume bar ────────────────────────────────────────────────────
        vb_y = 190
        _sunken(s,(8,vb_y,SW-16,8),(4,6,16),radius=4)
        vfw = int((SW-18)*vol/100)
        _hgrad(s,(9,vb_y+1,vfw,6),th.acc_col,th.sel_col)

        self._draw_tabs()

    # ── LIST SCREEN ───────────────────────────────────────────────────────────
    def _draw_list(self, title, items):
        th = self.th
        s  = self.surf
        s.blit(th.bg,(0,0))
        self._draw_topbar(title)

        y0     = 28
        list_h = SH - 50
        _sunken(s,(8,y0,SW-16,list_h),(4,6,16),radius=5)
        self._clamp(len(items))

        if not items:
            msg = th.fnt_main.render("Nothing here",True,th.dim_col)
            s.blit(msg,(SW//2-msg.get_width()//2,SH//2-6))
            self._draw_tabs(); return

        for i in range(self.ROWS_VIS):
            idx = self.scroll+i
            if idx >= len(items): break
            item= items[idx]
            ry  = y0+2+i*self.ROW_H
            if ry+self.ROW_H > y0+list_h: break
            sel = (idx==self.cursor)

            if sel:
                sel_surf = pygame.transform.scale(th.sel_row,(SW-18,self.ROW_H-2))
                s.blit(sel_surf,(9,ry))

            # playing bars
            is_playing = (idx==self.queue_idx and self.playing and
                         self.screen_id in (Screen.LIBRARY,Screen.QUEUE))
            if is_playing:
                for bi in range(3):
                    bh=3+bi*2
                    pygame.draw.rect(s,th.sel_col,(14+bi*4,ry+self.ROW_H-4-bh,3,bh))
            else:
                num_s = th.fnt_small.render(
                    str(idx+1),True,th.sel_col if sel else th.dim_col)
                s.blit(num_s,(14,ry+7))

            name   = item["title"] if isinstance(item,dict) else str(item)
            artist = item.get("artist","") if isinstance(item,dict) else ""
            tc     = th.txt_col if sel else _lc(th.txt_col,(50,60,80),0.3)
            ts     = th.fnt_main.render(trunc(th.fnt_main,name,SW-46),True,tc)
            s.blit(ts,(26,ry+2))
            if artist:
                ac = th.sel_col if sel else th.dim_col
                as_= th.fnt_small.render(trunc(th.fnt_small,artist,SW-46),True,ac)
                s.blit(as_,(26,ry+14))

            if sel:
                q_s=th.fnt_small.render("+Q",True,th.acc_col)
                s.blit(q_s,(SW-26,ry+7))

        # Scrollbar
        if len(items)>self.ROWS_VIS:
            sbx=SW-14; sby=y0+4; sbh=list_h-8
            pygame.draw.rect(s,DefaultAssets.SUNKEN,(sbx,sby,4,sbh),border_radius=2)
            ratio=self.ROWS_VIS/len(items)
            th_=max(8,int(sbh*ratio))
            ty_=sby+int((self.scroll/len(items))*sbh)
            _vgrad(s,(sbx,ty_,4,th_),th.sel_col,th.acc_col)
            pygame.draw.rect(s,th.sel_col,(sbx,ty_,4,th_),1,border_radius=2)

        self._draw_tabs()

    # ── PLAYLISTS ─────────────────────────────────────────────────────────────
    def _draw_playlists(self):
        th = self.th
        s  = self.surf
        self._pl_keys = sorted(self.playlists.keys())
        s.blit(th.bg,(0,0))
        self._draw_topbar("PLAYLISTS")
        y0=28; list_h=SH-50
        _sunken(s,(8,y0,SW-16,list_h),(4,6,16),radius=5)
        self._clamp(len(self._pl_keys))

        if not self._pl_keys:
            msg=th.fnt_main.render("No playlists",True,th.dim_col)
            s.blit(msg,(SW//2-msg.get_width()//2,SH//2-6))
            hint=th.fnt_small.render("Add .json to /playlists/",True,th.dim_col)
            s.blit(hint,(SW//2-hint.get_width()//2,SH//2+8))
            self._draw_tabs(); return

        ROWS=6; rh=28
        for i in range(ROWS):
            idx=self.scroll+i
            if idx>=len(self._pl_keys): break
            name=self._pl_keys[idx]
            count=len(self.playlists[name])
            ry=y0+2+i*rh
            sel=(idx==self.cursor)
            if sel:
                sel_s=pygame.transform.scale(th.sel_row,(SW-18,rh-2))
                s.blit(sel_s,(9,ry))
            _led(s,20,ry+rh//2,5,th.sel_col if sel else th.dim_col,on=sel)
            nc=th.txt_col if sel else _lc(th.txt_col,(50,60,80),0.3)
            ns=th.fnt_main.render(trunc(th.fnt_main,name,170),True,nc)
            s.blit(ns,(30,ry+4))
            cs=th.fnt_small.render(f"{count} trk",True,th.sel_col if sel else th.dim_col)
            s.blit(cs,(30,ry+16))

        self._draw_tabs()

    # ── OPTIONS ───────────────────────────────────────────────────────────────
    def _draw_options(self):
        th = self.th
        s  = self.surf

        # Use cover if it has real content, else bg
        s.blit(th.cover,(0,0))
        ov=pygame.Surface((SW,SH),pygame.SRCALPHA)
        ov.fill((0,0,0,150))
        s.blit(ov,(0,0))

        self._draw_topbar("OPTIONS")

        OPTS=[
            ("Theme",      "theme",     "list",  [t.cfg.get("name","?") for t in self.themes]),
            ("Shuffle",    "shuffle",   "toggle",None),
            ("Repeat",     "repeat",    "cycle", [r.name for r in Repeat]),
            ("Scanlines",  "scanlines", "toggle",None),
            ("Iridescence","iridescence","toggle",None),
            ("Volume",     "volume",    "range", None),
            ("EQ Preset",  "eq_preset", "list",  EQ_PRESETS),
        ]
        self._clamp_opts(len(OPTS))

        ROW_H=26; y0=30
        vis=min(len(OPTS),(SH-52)//ROW_H)
        sc_=max(0,min(self._opt_cur-vis+1,len(OPTS)-vis))

        for i in range(vis):
            idx=sc_+i
            if idx>=len(OPTS): break
            label,key,kind,extra=OPTS[idx]
            ry=y0+i*ROW_H
            sel=(idx==self._opt_cur)

            if sel:
                sel_s=pygame.transform.scale(th.sel_row,(SW-16,ROW_H-2))
                s.blit(sel_s,(8,ry))

            lc=th.txt_col if sel else th.dim_col
            ls=th.fnt_main.render(label,True,lc)
            s.blit(ls,(14,ry+5))

            # Value
            if kind=="toggle":
                if key=="shuffle":   on=self.shuffle
                elif key=="scanlines":    on=self.options.get("scanlines",True)
                elif key=="iridescence":  on=self.options.get("iridescence",True)
                else:                on=False
                vc=th.sel_col if on else th.dim_col
                pill_s=pygame.transform.scale(th.btn_small,(32,16))
                s.blit(pill_s,(SW-44,ry+5))
                _led(s,SW-36,ry+13,4,th.sel_col,on=on)
                vt=th.fnt_small.render("ON" if on else "OFF",True,vc)
                s.blit(vt,(SW-28,ry+6))

            elif kind=="range":
                val=self.options.get(key,80)
                sbx=SW-68; sbw=56
                _sunken(s,(sbx,ry+6,sbw,10),DefaultAssets.SUNKEN,radius=5)
                _hgrad(s,(sbx+1,ry+7,int((sbw-2)*val/100),8),
                       th.acc_col,th.sel_col)
                pt=th.fnt_small.render(f"{val}%",True,th.sel_col)
                s.blit(pt,(sbx+sbw//2-pt.get_width()//2,ry+6))

            elif kind in ("list","cycle"):
                if key=="theme":    val_i=self.theme_idx; lst=extra
                elif key=="repeat": val_i=list(Repeat).index(self.repeat); lst=extra
                else:               val_i=self.options.get(key,0); lst=extra or []
                if lst:
                    cv=lst[val_i%len(lst)]
                    s.blit(pygame.transform.scale(th.btn_small,(60,16)),(SW-70,ry+5))
                    vt=th.fnt_small.render(trunc(th.fnt_small,cv,56),True,th.sel_col)
                    s.blit(vt,(SW-70+30-vt.get_width()//2,ry+6))
                    if sel:
                        s.blit(th.fnt_small.render("◄",True,th.acc_col),(SW-72,ry+6))
                        s.blit(th.fnt_small.render("►",True,th.acc_col),(SW-10,ry+6))

        hint=th.fnt_small.render("UP/DN: select  L/R: change",True,th.dim_col)
        s.blit(hint,(SW//2-hint.get_width()//2,SH-28))
        self._draw_tabs()

    def _clamp_opts(self,count):
        if count==0: self._opt_cur=0; return
        self._opt_cur=_clamp(self._opt_cur,0,count-1)

    # ── Toast ─────────────────────────────────────────────────────────────────
    def _draw_toast(self):
        if self._toast_t<=0: return
        th=self.th; s=self.surf
        tw=min(SW-16,th.fnt_sub.size(self._toast_msg)[0]+16); th_=18
        tx=SW//2-tw//2; ty=SH-44
        bg=pygame.Surface((tw,th_),pygame.SRCALPHA)
        _vgrad(bg,(0,0,tw,th_),
               _lc(DefaultAssets.PANEL,th.sel_col,0.3),
               DefaultAssets.PANEL)
        bg.set_alpha(min(230,self._toast_t*10))
        pygame.draw.rect(bg,th.sel_col,(0,0,tw,th_),1,border_radius=9)
        s.blit(bg,(tx,ty))
        ms=th.fnt_sub.render(self._toast_msg,True,th.txt_col)
        s.blit(ms,(tx+tw//2-ms.get_width()//2,ty+2))

    # ══════════════════════════════════════════════════════════════════════════
    #  INPUT
    # ══════════════════════════════════════════════════════════════════════════
    def handle_btn(self, btn):
        sid     = self.screen_id
        screens = [Screen.NOW_PLAYING,Screen.LIBRARY,Screen.QUEUE,
                   Screen.PLAYLISTS,Screen.OPTIONS]

        # Options — full control
        if sid==Screen.OPTIONS:
            OPTS=[
                ("theme","list",[t.cfg.get("name","?") for t in self.themes]),
                ("shuffle","toggle",None),
                ("repeat","cycle",[r.name for r in Repeat]),
                ("scanlines","toggle",None),
                ("iridescence","toggle",None),
                ("volume","range",None),
                ("eq_preset","list",EQ_PRESETS),
            ]
            n=len(OPTS)
            if btn=="UP":   self._opt_cur=max(0,self._opt_cur-1)
            elif btn=="DOWN": self._opt_cur=min(n-1,self._opt_cur+1)
            elif btn in ("LEFT","RIGHT","OK"):
                d=1 if btn in ("RIGHT","OK") else -1
                key,kind,extra=OPTS[self._opt_cur]
                if kind=="toggle":
                    if key=="shuffle": self.shuffle=not self.shuffle
                    else: self.options[key]=not self.options.get(key,True)
                elif kind=="range":
                    self.options[key]=_clamp(self.options.get(key,80)+d*5,0,100)
                    if key=="volume" and self._audio_ok:
                        pygame.mixer.music.set_volume(self.options[key]/100)
                elif kind in ("list","cycle"):
                    if key=="theme":
                        self.theme_idx=(self.theme_idx+d)%len(self.themes)
                        self.th=self.themes[self.theme_idx]
                    elif key=="repeat":
                        m=list(Repeat)
                        self.repeat=m[(m.index(self.repeat)+d)%len(m)]
                    else:
                        lst=extra or []
                        self.options[key]=(self.options.get(key,0)+d)%len(lst)
            return

        # Global tab nav
        if btn in ("LEFT","RIGHT"):
            if sid==Screen.PLAYLIST_VIEW:
                self.screen_id=Screen.PLAYLISTS
            else:
                i=screens.index(sid) if sid in screens else 0
                self.screen_id=screens[(i+(1 if btn=="RIGHT" else -1))%len(screens)]
            self.cursor=self.scroll=0; return

        if sid==Screen.NOW_PLAYING:
            if btn=="OK":    self.play_pause()
            elif btn=="UP":  self.prev_track()
            elif btn=="DOWN":self.next_track()

        elif sid in (Screen.LIBRARY,Screen.QUEUE):
            items=self.library if sid==Screen.LIBRARY else self.queue
            if btn=="UP":   self.cursor=max(0,self.cursor-1)
            elif btn=="DOWN": self.cursor=min(len(items)-1,self.cursor+1)
            elif btn=="OK" and items:
                if sid==Screen.LIBRARY:
                    self.queue=list(self.library)
                    self._load_track(self.cursor,autoplay=True)
                else:
                    self._load_track(self.cursor,autoplay=True)
                self.screen_id=Screen.NOW_PLAYING

        elif sid==Screen.PLAYLISTS:
            self._pl_keys=sorted(self.playlists.keys())
            if btn=="UP":   self.cursor=max(0,self.cursor-1)
            elif btn=="DOWN": self.cursor=min(len(self._pl_keys)-1,self.cursor+1)
            elif btn=="OK" and self._pl_keys:
                self.sel_pl=self._pl_keys[self.cursor]
                self.screen_id=Screen.PLAYLIST_VIEW
                self.cursor=self.scroll=0

        elif sid==Screen.PLAYLIST_VIEW:
            pm={t["path"]:t for t in self.library}
            pl_raw=self.playlists.get(self.sel_pl,[])
            items=[pm.get(p if isinstance(p,str) else p.get("path",""),
                   {"title":Path(p if isinstance(p,str) else p.get("path","")).stem,
                    "artist":"","path":p if isinstance(p,str) else p.get("path","")})
                   for p in pl_raw]
            if btn=="UP":   self.cursor=max(0,self.cursor-1)
            elif btn=="DOWN": self.cursor=min(len(items)-1,self.cursor+1)
            elif btn=="OK" and items: self.add_to_queue(items[self.cursor])

    # ══════════════════════════════════════════════════════════════════════════
    #  MAIN LOOP
    # ══════════════════════════════════════════════════════════════════════════
    def run(self):
        while True:
            self.tick+=1
            if self.playing and not self.paused:
                self.pos_sec+=time.time()-self._last_t
            self._last_t=time.time()
            self._upd_vu()
            if self._toast_t>0: self._toast_t-=1

            for ev in pygame.event.get():
                if ev.type==pygame.QUIT: self._quit()
                elif ev.type==self.EV_END:
                    if self.repeat==Repeat.ONE:
                        self._load_track(self.queue_idx,autoplay=True)
                    elif self.repeat==Repeat.ALL or self.queue_idx<len(self.queue)-1:
                        self.next_track()
                    else: self.playing=self.paused=False
                elif ev.type==pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE,pygame.K_q): self._quit()
                    KB={pygame.K_UP:"UP",pygame.K_DOWN:"DOWN",
                        pygame.K_LEFT:"LEFT",pygame.K_RIGHT:"RIGHT",
                        pygame.K_RETURN:"OK",pygame.K_SPACE:"OK",
                        pygame.K_KP_ENTER:"OK"}
                    if ev.key in KB: self.handle_btn(KB[ev.key])
                    elif ev.key==pygame.K_n: self.next_track()
                    elif ev.key==pygame.K_p: self.prev_track()

            cur=self._read_gpio()
            for b in cur-self._prev_gpio: self.handle_btn(b)
            self._prev_gpio=cur

            sid=self.screen_id
            if sid==Screen.NOW_PLAYING:   self._draw_now_playing()
            elif sid==Screen.LIBRARY:     self._draw_list("LIBRARY",self.library)
            elif sid==Screen.QUEUE:       self._draw_list(f"QUEUE",self.queue)
            elif sid==Screen.PLAYLISTS:   self._draw_playlists()
            elif sid==Screen.PLAYLIST_VIEW:
                pm={t["path"]:t for t in self.library}
                pl_raw=self.playlists.get(self.sel_pl,[])
                items=[pm.get(p if isinstance(p,str) else p.get("path",""),
                       {"title":Path(p if isinstance(p,str) else p.get("path","")).stem,
                        "artist":"","path":p if isinstance(p,str) else p.get("path","")})
                       for p in pl_raw]
                self._draw_list(f"▶ {(self.sel_pl or '')[:14]}",items)
            elif sid==Screen.OPTIONS:     self._draw_options()

            if self.options.get("scanlines",True):
                self.surf.blit(self._scanlines,(0,0))
            self._draw_toast()
            pygame.display.flip()
            self.clock.tick(FPS)

    def _quit(self):
        if self._audio_ok: pygame.mixer.music.stop()
        pygame.quit(); sys.exit(0)


if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser(description="Innioasis Music Player")
    ap.add_argument("--music",     default="music")
    ap.add_argument("--playlists", default="playlists")
    ap.add_argument("--themes",    default="themes")
    ap.add_argument("--window",    action="store_true",
                    help="Force window mode (SSH/MobaXterm)")
    args=ap.parse_args()
    MusicPlayer(music_dir=args.music,pl_dir=args.playlists,
                themes_dir=args.themes,window_mode=args.window).run()
