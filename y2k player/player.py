#!/usr/bin/env python3
"""
Y2K WINAMP-STYLE MUSIC PLAYER (FULL PRODUCTION MERGE)
240x240 SPI display | python3-pygame | Raspberry Pi Zero W
5 buttons: UP / DOWN / LEFT / RIGHT / OK
"""

import pygame
import pygame.mixer
import os, sys, json, random, math, time
from pathlib import Path
from enum import Enum, auto

# ── Display ────────────────────────────────────────────────────────────────────
SW, SH = 240, 240
FPS = 30

# ── GPIO (BCM) ─────────────────────────────────────────────────────────────────
BTN_UP    = 17
BTN_DOWN  = 27
BTN_LEFT  = 22
BTN_RIGHT = 23
BTN_OK    = 26

# ── Themes (Y2K Aesthetic) ─────────────────────────────────────────────────────
THEMES = {
    "CYBER_CYAN": {
        "name": "Cyber Cyan",
        "bg0": (8,10,18), "bg1": (18,10,30),
        "panel": (25, 30, 45),
        "accent": (0,255,220), "accent2": (255,0,180),
        "text": (220,230,255), "text_dim": (100, 120, 150),
        "sel": (0, 100, 120)
    },
    "MAGENTA_CORE": {
        "name": "Magenta Core",
        "bg0": (18,8,18), "bg1": (30,10,25),
        "panel": (40, 20, 35),
        "accent": (255,0,180), "accent2": (0,255,220),
        "text": (240,220,255), "text_dim": (150, 100, 150),
        "sel": (120, 0, 100)
    },
    "ICE_BLUE": {
        "name": "Ice Blue",
        "bg0": (10,14,22), "bg1": (20,28,40),
        "panel": (35, 45, 60),
        "accent": (120,220,255), "accent2": (0,180,255),
        "text": (220,245,255), "text_dim": (120, 140, 170),
        "sel": (0, 80, 150)
    },
    "AMBER_LCD": {
        "name": "Amber LCD",
        "bg0": (20,14,6), "bg1": (30,20,10),
        "panel": (45, 30, 15),
        "accent": (255,180,60), "accent2": (255,120,0),
        "text": (255,220,180), "text_dim": (160, 120, 80),
        "sel": (150, 80, 0)
    }
}
THEME_KEYS = list(THEMES.keys())

# ── Enums ──────────────────────────────────────────────────────────────────────
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

# ── Helpers ────────────────────────────────────────────────────────────────────
def trunc(font, text, max_w):
    if font.size(text)[0] <= max_w: return text
    while text and font.size(text + "…")[0] > max_w:
        text = text[:-1]
    return text + "…"

def lerp(a, b, t): return int(a + (b - a) * t)

MUSIC_EXTS = {".mp3", ".ogg", ".flac", ".wav", ".m4a", ".opus"}

def scan_music(base_dir):
    tracks = []
    base = Path(base_dir)
    if not base.exists(): return tracks
    for f in sorted(base.rglob("*")):
        if f.suffix.lower() in MUSIC_EXTS:
            meta = {"path": str(f), "title": f.stem,
                    "artist": f.parent.name if f.parent != base else "Unknown",
                    "album":  ""}
            try:
                from mutagen import File as MFile
                mf = MFile(str(f))
                if mf and mf.tags:
                    t = mf.tags
                    def g(keys):
                        for k in keys:
                            v = t.get(k)
                            if v: return str(v[0]) if hasattr(v,'__iter__') and not isinstance(v,str) else str(v)
                        return None
                    meta["title"]  = g(["TIT2","title","©nam"]) or meta["title"]
                    meta["artist"] = g(["TPE1","artist","©ART"]) or meta["artist"]
            except Exception: pass
            tracks.append(meta)
    return tracks

def load_playlists(pl_dir):
    pls = {}
    p = Path(pl_dir)
    p.mkdir(parents=True, exist_ok=True)
    for f in sorted(p.glob("*.json")):
        try:
            with open(f) as fh: pls[f.stem] = json.load(fh)
        except Exception: pass
    return pls

# ── Y2K Drawing Primitives ─────────────────────────────────────────────────────
def draw_grad_rect(surf, rect, c1, c2):
    x, y, w, h = rect
    for i in range(h):
        t = i / max(h - 1, 1)
        c = (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))
        pygame.draw.line(surf, c, (x, y + i), (x + w - 1, y + i))

def draw_chrome_box(surf, rect, theme, pressed=False):
    x, y, w, h = rect
    hi = (220, 220, 240)
    lo = (40, 40, 60)
    if pressed: hi, lo = lo, hi
    pygame.draw.rect(surf, theme["panel"], rect, border_radius=6)
    pygame.draw.line(surf, hi, (x+3, y), (x+w-4, y))
    pygame.draw.line(surf, hi, (x, y+3), (x, y+h-4))
    pygame.draw.line(surf, lo, (x+3, y+h-1), (x+w-4, y+h-1))
    pygame.draw.line(surf, lo, (x+w-1, y+3), (x+w-1, y+h-4))

def draw_glow_bar(surf, x, y, w, h, frac, theme):
    bg = (20, 20, 40)
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=3)
    if frac > 0:
        fw = max(h, int(w * min(frac, 1.0)))
        draw_grad_rect(surf, (x, y, fw, h), theme["accent2"], theme["accent"])
        pygame.draw.rect(surf, theme["accent"], (x, y, fw, h), 1, border_radius=3)

def draw_vu_meter(surf, x, y, theme, active):
    for i in range(12):
        if active:
            h = random.randint(2, 16)
        else:
            h = 2
        col = theme["accent"] if h > 10 else theme["accent2"]
        pygame.draw.rect(surf, col, (x + i * 5, y + 16 - h, 3, h))

def draw_lcd_time(surf, x, y, font, sec_total, theme):
    s = max(0, int(sec_total))
    txt = f"{s//60:02d}:{s%60:02d}"
    
    # Fake LCD backdrop
    bg_txt = "88:88"
    bg_surf = font.render(bg_txt, True, theme["bg1"])
    surf.blit(bg_surf, (x, y))
    
    fg_surf = font.render(txt, True, theme["accent"])
    surf.blit(fg_surf, (x, y))

# ── Player Core ────────────────────────────────────────────────────────────────
class MusicPlayer:
    ROWS_VIS = 7
    ROW_H    = 26

    def __init__(self, music_dir="music", pl_dir="playlists", window_mode=False):
        pygame.init()
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            self._audio_ok = True
        except pygame.error as e:
            print(f"[audio] {e} — silent mode.")
            os.environ["SDL_AUDIODRIVER"] = "dummy"
            try: pygame.mixer.init()
            except Exception: pass
            self._audio_ok = False

        if window_mode:
            os.environ.pop("SDL_VIDEODRIVER", None)
            os.environ.pop("SDL_FBDEV", None)
        else:
            if os.path.exists("/dev/fb0") and "DISPLAY" not in os.environ:
                os.environ.setdefault("SDL_VIDEODRIVER", "fbcon")
                os.environ.setdefault("SDL_FBDEV", "/dev/fb1")

        self.surf = pygame.display.set_mode((SW, SH))
        pygame.display.set_caption("Y2K Player")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()

        # Fonts
        self.fnt_title = pygame.font.SysFont("dejavusansbold", 14, bold=True)
        self.fnt_lcd   = pygame.font.SysFont("dejavusansmono", 18, bold=True)
        self.fnt_sub   = pygame.font.SysFont("dejavusans",     13)
        self.fnt_small = pygame.font.SysFont("dejavusans",     11)

        # State
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

        self.screen_id = Screen.NOW_PLAYING
        self.cursor    = 0
        self.scroll    = 0
        self.sel_pl    = None
        self._pl_keys  = []

        self.tick        = 0
        self._scroll_x   = 0
        self._scroll_dir = 1
        
        self.theme_idx = 0
        self.theme = THEMES[THEME_KEYS[self.theme_idx]]

        self._gpio = self._init_gpio()
        self._prev_gpio = set()

        pygame.mixer.music.set_endevent(pygame.USEREVENT + 1)
        self.EV_END = pygame.USEREVENT + 1

        if self.library:
            self._load_track(0)

    def _init_gpio(self):
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            for pin in (BTN_UP, BTN_DOWN, BTN_LEFT, BTN_RIGHT, BTN_OK):
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            return GPIO
        except Exception: return None

    def _read_gpio(self):
        if not self._gpio: return set()
        G = self._gpio
        p = set()
        if not G.input(BTN_UP):    p.add("UP")
        if not G.input(BTN_DOWN):  p.add("DOWN")
        if not G.input(BTN_LEFT):  p.add("LEFT")
        if not G.input(BTN_RIGHT): p.add("RIGHT")
        if not G.input(BTN_OK):    p.add("OK")
        return p

    def _load_track(self, idx, autoplay=False):
        if not self.queue: return
        self.queue_idx = idx % len(self.queue)
        t = self.queue[self.queue_idx]
        try:
            self.duration = self._get_dur(t["path"])
            self.pos_sec  = 0.0
            self._last_t  = time.time()
            self._scroll_x = 0
            if self._audio_ok: pygame.mixer.music.load(t["path"])
            if (autoplay or self.playing) and self._audio_ok:
                pygame.mixer.music.play()
            self.playing = autoplay or self.playing
            self.paused  = False
        except Exception as e: print(f"[load] {e}")

    def _get_dur(self, path):
        try:
            from mutagen import File as MF
            mf = MF(path)
            if mf and mf.info: return mf.info.length
        except Exception: pass
        return 0.0

    def play_pause(self):
        if not self.queue: return
        if self.playing and not self.paused:
            if self._audio_ok: pygame.mixer.music.pause()
            self.paused = True
        elif self.paused:
            if self._audio_ok: pygame.mixer.music.unpause()
            self.paused = False
        else:
            self._load_track(self.queue_idx, autoplay=True)

    def next_track(self):
        if not self.queue: return
        nxt = random.randint(0, len(self.queue)-1) if self.shuffle else (self.queue_idx + 1) % len(self.queue)
        self._load_track(nxt, autoplay=True)

    def prev_track(self):
        if not self.queue: return
        if self.pos_sec > 3:
            if self._audio_ok: pygame.mixer.music.rewind()
            self.pos_sec = 0.0
        else:
            self._load_track((self.queue_idx - 1) % len(self.queue), autoplay=True)

    def _on_end(self):
        if self.repeat == Repeat.ONE: self._load_track(self.queue_idx, autoplay=True)
        elif self.repeat == Repeat.ALL or self.queue_idx < len(self.queue)-1: self.next_track()
        else: self.playing = False; self.paused = False

    def _update_pos(self):
        now = time.time()
        if self.playing and not self.paused:
            self.pos_sec += now - self._last_t
        self._last_t = now

    def _clamp(self, count):
        if count == 0: self.cursor = self.scroll = 0; return
        self.cursor = max(0, min(self.cursor, count-1))
        vis = self.ROWS_VIS
        if self.cursor < self.scroll: self.scroll = self.cursor
        elif self.cursor >= self.scroll + vis: self.scroll = self.cursor - vis + 1
        self.scroll = max(0, min(self.scroll, max(0, count - vis)))

    # ── UI Draws ──────────────────────────────────────────────────────────────────
    def _draw_bg(self):
        draw_grad_rect(self.surf, (0, 0, SW, SH), self.theme["bg0"], self.theme["bg1"])

    def _draw_tabs(self):
        tabs = [("NOW", Screen.NOW_PLAYING), ("LIB", Screen.LIBRARY), 
                ("Q", Screen.QUEUE), ("PLS", Screen.PLAYLISTS), ("OPT", Screen.OPTIONS)]
        y = SH - 20
        sw = SW // len(tabs)
        
        draw_chrome_box(self.surf, (0, y, SW, 20), self.theme)
        
        for i, (name, sid) in enumerate(tabs):
            x = i * sw
            active = (self.screen_id == sid) or (self.screen_id == Screen.PLAYLIST_VIEW and sid == Screen.PLAYLISTS)
            col = self.theme["accent"] if active else self.theme["text_dim"]
            lbl = self.fnt_small.render(name, True, col)
            self.surf.blit(lbl, (x + sw//2 - lbl.get_width()//2, y + 4))
            if active:
                pygame.draw.line(self.surf, self.theme["accent"], (x+4, y+18), (x+sw-4, y+18), 2)

    def _draw_now_playing(self):
        self._draw_bg()
        s = self.surf
        th = self.theme

        # Top Marquee Display
        draw_chrome_box(s, (10, 10, SW-20, 50), th)
        if self.queue:
            t = self.queue[self.queue_idx]
            title = t["title"]
            ts = self.fnt_title.render(title, True, th["accent"])
            max_w = SW - 36
            
            clip_r = pygame.Rect(18, 16, max_w, 20)
            s.set_clip(clip_r)
            if ts.get_width() > max_w:
                self._scroll_x += self._scroll_dir * 1.0
                if self._scroll_x > ts.get_width() - max_w + 10: self._scroll_dir = -1
                if self._scroll_x < 0: self._scroll_dir = 1; self._scroll_x = 0
            s.blit(ts, (18 - int(self._scroll_x), 16))
            s.set_clip(None)
            
            art = self.fnt_small.render(trunc(self.fnt_small, t["artist"], max_w), True, th["text"])
            s.blit(art, (18, 38))

        # Middle Dashboard
        draw_chrome_box(s, (10, 70, SW-20, 70), th)
        
        # LCD Time
        draw_lcd_time(s, 20, 80, self.fnt_lcd, self.pos_sec, th)
        draw_lcd_time(s, SW-70, 80, self.fnt_lcd, self.duration, th)
        
        # VU Meter
        is_active = self.playing and not self.paused
        draw_vu_meter(s, SW//2 - 28, 82, th, is_active)
        
        # Progress Bar
        frac = (self.pos_sec / self.duration) if self.duration > 0 else 0
        draw_glow_bar(s, 20, 115, SW-40, 10, frac, th)

        # Controls Info
        modes = self.fnt_small.render(
            f"SHF: {'ON' if self.shuffle else 'OFF'} | RPT: {self.repeat.name}", True, th["text_dim"])
        s.blit(modes, (SW//2 - modes.get_width()//2, 150))
        
        # Play status
        stat = "PLAYING" if is_active else "PAUSED" if self.paused else "STOPPED"
        st = self.fnt_sub.render(stat, True, th["accent2"])
        s.blit(st, (SW//2 - st.get_width()//2, 170))

        self._draw_tabs()

    def _draw_list(self, title, items):
        self._draw_bg()
        s = self.surf
        th = self.theme
        
        lbl = self.fnt_title.render(title, True, th["accent"])
        s.blit(lbl, (10, 10))
        
        y0 = 30
        self._clamp(len(items))

        for i in range(self.ROWS_VIS):
            idx = self.scroll + i
            if idx >= len(items): break
            t = items[idx]
            ry = y0 + i * self.ROW_H
            sel = (idx == self.cursor)
            
            if sel: draw_grad_rect(s, (5, ry, SW-10, self.ROW_H-2), th["sel"], th["bg0"])
            
            # Text
            name = t["title"] if isinstance(t, dict) else t
            col = th["text"] if sel else th["text_dim"]
            ts = self.fnt_sub.render(trunc(self.fnt_sub, name, SW-30), True, col)
            s.blit(ts, (15, ry + 4))

        # Scrollbar
        if len(items) > self.ROWS_VIS:
            sh = self.ROWS_VIS * self.ROW_H
            rat = self.ROWS_VIS / len(items)
            bh = max(10, int(sh * rat))
            by = y0 + int((self.scroll / len(items)) * sh)
            pygame.draw.rect(s, th["panel"], (SW-8, y0, 6, sh))
            pygame.draw.rect(s, th["accent"], (SW-8, by, 6, bh))

        self._draw_tabs()

    def _draw_options(self):
        self._draw_bg()
        s = self.surf
        th = self.theme
        
        lbl = self.fnt_title.render("SYSTEM OPTIONS", True, th["accent"])
        s.blit(lbl, (10, 10))

        opts = [
            ("Theme", th["name"]),
            ("Shuffle", "ON" if self.shuffle else "OFF"),
            ("Repeat", self.repeat.name)
        ]
        
        self._clamp(len(opts))
        y0 = 40
        
        for i, (k, v) in enumerate(opts):
            ry = y0 + i * 40
            sel = (i == self.cursor)
            
            if sel:
                draw_chrome_box(s, (10, ry, SW-20, 34), th)
                pygame.draw.rect(s, th["accent"], (10, ry, SW-20, 34), 1, border_radius=6)
            else:
                draw_chrome_box(s, (10, ry, SW-20, 34), th, pressed=True)
            
            ks = self.fnt_sub.render(k, True, th["text_dim"] if not sel else th["text"])
            vs = self.fnt_title.render(v, True, th["accent2"] if sel else th["accent"])
            
            s.blit(ks, (20, ry + 10))
            s.blit(vs, (SW - 20 - vs.get_width(), ry + 10))
            
            if sel:
                # Little arrows indicating left/right interaction
                arr = self.fnt_small.render("<   >", True, th["accent"])
                s.blit(arr, (SW - 30 - vs.get_width() - arr.get_width(), ry+11))

        self._draw_tabs()

    # ── Input Loop ────────────────────────────────────────────────────────────────
    _KB = {
        pygame.K_UP: "UP", pygame.K_DOWN: "DOWN",
        pygame.K_LEFT: "LEFT", pygame.K_RIGHT: "RIGHT",
        pygame.K_RETURN: "OK", pygame.K_SPACE: "OK"
    }

    def handle_btn(self, btn):
        screens = [Screen.NOW_PLAYING, Screen.LIBRARY, Screen.QUEUE, Screen.PLAYLISTS, Screen.OPTIONS]
        sid = self.screen_id

        # Global Tab Navigation (Left/Right overrides in non-option menus)
        if btn in ("LEFT", "RIGHT") and sid != Screen.OPTIONS:
            if sid == Screen.PLAYLIST_VIEW:
                self.screen_id = Screen.PLAYLISTS
                self.cursor = self._pl_keys.index(self.sel_pl) if self.sel_pl in self._pl_keys else 0
                return
            idx = screens.index(sid)
            nxt = (idx + (1 if btn == "RIGHT" else -1)) % len(screens)
            self.screen_id = screens[nxt]
            self.cursor = self.scroll = 0
            return

        if sid == Screen.NOW_PLAYING:
            if btn == "OK": self.play_pause()
            elif btn == "UP": self.prev_track()
            elif btn == "DOWN": self.next_track()

        elif sid in (Screen.LIBRARY, Screen.QUEUE):
            items = self.library if sid == Screen.LIBRARY else self.queue
            if btn == "UP":   self.cursor -= 1
            elif btn == "DOWN": self.cursor += 1
            elif btn == "OK" and items:
                if sid == Screen.LIBRARY: self.queue = list(self.library)
                self._load_track(self.cursor, autoplay=True)
                self.screen_id = Screen.NOW_PLAYING

        elif sid == Screen.PLAYLISTS:
            self._pl_keys = sorted(self.playlists.keys())
            if btn == "UP":   self.cursor -= 1
            elif btn == "DOWN": self.cursor += 1
            elif btn == "OK" and self._pl_keys:
                self.sel_pl = self._pl_keys[self.cursor]
                self.screen_id = Screen.PLAYLIST_VIEW
                self.cursor = self.scroll = 0

        elif sid == Screen.PLAYLIST_VIEW:
            pl_raw = self.playlists.get(self.sel_pl, [])
            if btn == "UP":   self.cursor -= 1
            elif btn == "DOWN": self.cursor += 1
            elif btn == "OK" and pl_raw:
                pm = {t["path"]: t for t in self.library}
                p = pl_raw[self.cursor]
                p_str = p if isinstance(p, str) else p.get("path","")
                track = pm.get(p_str, {"title": Path(p_str).stem, "artist":"", "path": p_str})
                self.queue.append(track)

        elif sid == Screen.OPTIONS:
            if btn == "UP": self.cursor -= 1
            elif btn == "DOWN": self.cursor += 1
            elif btn in ("LEFT", "RIGHT", "OK"):
                dir_val = 1 if btn in ("RIGHT", "OK") else -1
                if self.cursor == 0: # Theme
                    self.theme_idx = (self.theme_idx + dir_val) % len(THEME_KEYS)
                    self.theme = THEMES[THEME_KEYS[self.theme_idx]]
                elif self.cursor == 1: # Shuffle
                    self.shuffle = not self.shuffle
                elif self.cursor == 2: # Repeat
                    modes = list(Repeat)
                    self.repeat = modes[(modes.index(self.repeat) + dir_val) % len(modes)]

    def run(self):
        while True:
            self.tick += 1
            self._update_pos()
            
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT: self._quit()
                elif ev.type == self.EV_END: self._on_end()
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_q): self._quit()
                    elif ev.key in self._KB: self.handle_btn(self._KB[ev.key])

            cur = self._read_gpio()
            for btn in cur - self._prev_gpio: self.handle_btn(btn)
            self._prev_gpio = cur

            if self.screen_id == Screen.NOW_PLAYING: self._draw_now_playing()
            elif self.screen_id == Screen.LIBRARY: self._draw_list("LIBRARY", self.library)
            elif self.screen_id == Screen.QUEUE: self._draw_list(f"QUEUE [{len(self.queue)}]", self.queue)
            elif self.screen_id == Screen.PLAYLISTS: 
                self._pl_keys = sorted(self.playlists.keys())
                self._draw_list("PLAYLISTS", self._pl_keys)
            elif self.screen_id == Screen.PLAYLIST_VIEW:
                items = self.playlists.get(self.sel_pl, [])
                self._draw_list(f"PL: {self.sel_pl[:10]}", [i if isinstance(i,str) else i.get("title","") for i in items])
            elif self.screen_id == Screen.OPTIONS: self._draw_options()

            pygame.display.flip()
            self.clock.tick(FPS)

    def _quit(self):
        if self._audio_ok: pygame.mixer.music.stop()
        pygame.quit()
        sys.exit(0)

if __name__ == "__main__":
    MusicPlayer(window_mode=True).run() # Zmień na window_mode=False dla Raspberry Pi