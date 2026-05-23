#!/usr/bin/env python3
"""
INNIOASIS THEME COMPATIBLE MUSIC PLAYER
240x240 SPI display | python3-pygame | Raspberry Pi Zero W
Parses native Innioasis Y1 themes (config.json, desk_bg001.png, 1.png, etc.)
"""

import pygame
import pygame.mixer
import os, sys, json, time, random
from pathlib import Path
from enum import Enum, auto

# ── Display & GPIO ─────────────────────────────────────────────────────────────
SW, SH = 240, 240
FPS = 30

BTN_UP    = 17
BTN_DOWN  = 27
BTN_LEFT  = 22
BTN_RIGHT = 23
BTN_OK    = 26

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

# ── Innioasis Theme Engine ─────────────────────────────────────────────────────
class Theme:
    def __init__(self, path):
        self.path = Path(path)
        
        # Domyślny fallback, jeśli brakuje config.json
        self.cfg = {
            "name": self.path.name,
            "desktopWallpaper": "desk_bg001.png",
            "fontFamily": None,
            "textColor": "#FFFFFF",
            "selectColor": "#00FF00"
        }
        
        # 1. Wczytywanie natywnego pliku Innioasis: config.json
        cfg_file = self.path / "config.json"
        if cfg_file.exists():
            try:
                with open(cfg_file, 'r', encoding='utf-8') as f:
                    self.cfg.update(json.load(f))
            except Exception as e:
                print(f"Błąd ładowania config.json z {self.path.name}: {e}")
                
        # 2. Parsowanie kolorów (Innioasis używa HEX lub tablic [R,G,B])
        self.txt_col = self._parse_color(self.cfg.get("textColor", "#FFFFFF"))
        self.sel_col = self._parse_color(self.cfg.get("selectColor", "#00FF00"))
        
        # 3. Ładowanie grafik w standardzie Innioasis
        bg_name = self.cfg.get("desktopWallpaper", "desk_bg001.png")
        self.bg = self._load_img(bg_name, (SW, SH))          # Tło zdefiniowane w JSON
        self.sel = self._load_img("1.png", (SW, 26))         # Innioasis highlight belka
        self.cover = self._load_img("cover.png", (SW, SH))   # Podgląd motywu do zakładki OPTIONS
        self.topbar = self._load_img("topbar.png", (SW, 20)) # Opcjonalnie
        
        # 4. Ładowanie czcionki .ttf
        font_file = self.cfg.get("fontFamily")
        if not font_file or not (self.path / font_file).exists():
            # Fallback: znajdź jakikolwiek plik ttf w folderze motywu
            ttfs = list(self.path.glob("*.ttf"))
            font_file = ttfs[0].name if ttfs else None
            
        fs = 14 # Domyślny rozmiar
        if font_file:
            try:
                self.fnt_main = pygame.font.Font(str(self.path / font_file), fs)
                self.fnt_sub = pygame.font.Font(str(self.path / font_file), max(10, fs - 2))
            except:
                self._fallback_fonts(fs)
        else:
            self._fallback_fonts(fs)

    def _fallback_fonts(self, fs):
        self.fnt_main = pygame.font.SysFont("dejavusans", fs)
        self.fnt_sub = pygame.font.SysFont("dejavusans", max(10, fs - 2))

    def _parse_color(self, c):
        if isinstance(c, list) and len(c) >= 3:
            return tuple(c[:3])
        if isinstance(c, str):
            c = c.strip().lstrip('#')
            if len(c) == 6:
                return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
        return (255, 255, 255)

    def _load_img(self, name, size):
        p = self.path / name
        if p.exists():
            try: return pygame.transform.scale(pygame.image.load(str(p)).convert_alpha(), size)
            except: pass
        # Jeśli grafiki brakuje, stwórz przezroczystą płachtę
        return pygame.Surface(size, pygame.SRCALPHA)

def load_themes(themes_dir="themes"):
    p = Path(themes_dir)
    p.mkdir(exist_ok=True)
    themes = [Theme(d) for d in p.iterdir() if d.is_dir()]
    if not themes:
        (p / "Default").mkdir(exist_ok=True)
        themes.append(Theme(p / "Default"))
    return sorted(themes, key=lambda x: x.cfg.get("name", ""))

# ── Helpers ────────────────────────────────────────────────────────────────────
def trunc(font, text, max_w):
    if font.size(text)[0] <= max_w: return text
    while text and font.size(text + "…")[0] > max_w: text = text[:-1]
    return text + "…"

def scan_music(base_dir):
    MUSIC_EXTS = {".mp3", ".ogg", ".flac", ".wav", ".m4a"}
    tracks = []
    base = Path(base_dir)
    if not base.exists(): return tracks
    for f in sorted(base.rglob("*")):
        if f.suffix.lower() in MUSIC_EXTS:
            meta = {"path": str(f), "title": f.stem, "artist": f.parent.name if f.parent != base else "Unknown"}
            try:
                from mutagen import File as MFile
                mf = MFile(str(f))
                if mf and mf.tags:
                    t = mf.tags
                    def g(keys):
                        for k in keys:
                            if k in t: return str(t[k][0]) if hasattr(t[k], '__iter__') and not isinstance(t[k], str) else str(t[k])
                        return None
                    meta["title"] = g(["TIT2","title","©nam"]) or meta["title"]
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

# ── Player Core ────────────────────────────────────────────────────────────────
class MusicPlayer:
    ROWS_VIS = 7
    ROW_H    = 26

    def __init__(self, music_dir="music", pl_dir="playlists", window_mode=False):
        pygame.init()
        try:
            pygame.mixer.init()
            self._audio_ok = True
        except:
            os.environ["SDL_AUDIODRIVER"] = "dummy"
            try: pygame.mixer.init()
            except: pass
            self._audio_ok = False

        if window_mode:
            os.environ.pop("SDL_VIDEODRIVER", None)
            os.environ.pop("SDL_FBDEV", None)
        else:
            if os.path.exists("/dev/fb0") and "DISPLAY" not in os.environ:
                os.environ.setdefault("SDL_VIDEODRIVER", "fbcon")
                os.environ.setdefault("SDL_FBDEV", "/dev/fb1")

        self.surf = pygame.display.set_mode((SW, SH))
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()

        self.themes = load_themes()
        self.theme_idx = 0
        self.th = self.themes[self.theme_idx]

        self.library = scan_music(music_dir)
        self.playlists = load_playlists(pl_dir)
        self.queue = list(self.library)
        self.queue_idx = 0
        
        self.shuffle = False
        self.repeat = Repeat.OFF
        self.playing = False
        self.paused = False
        self.pos_sec = 0.0
        self.duration = 0.0
        self._last_t = time.time()

        self.screen_id = Screen.NOW_PLAYING
        self.cursor = 0
        self.scroll = 0
        self.sel_pl = None

        self._gpio = self._init_gpio()
        self._prev_gpio = set()
        
        self._scroll_x = 0
        self._scroll_dir = 1

        pygame.mixer.music.set_endevent(pygame.USEREVENT + 1)
        self.EV_END = pygame.USEREVENT + 1
        if self.library: self._load_track(0)

    def _init_gpio(self):
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            for pin in (BTN_UP, BTN_DOWN, BTN_LEFT, BTN_RIGHT, BTN_OK): GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            return GPIO
        except: return None

    def _read_gpio(self):
        if not self._gpio: return set()
        G = self._gpio
        p = set()
        if not G.input(BTN_UP): p.add("UP")
        if not G.input(BTN_DOWN): p.add("DOWN")
        if not G.input(BTN_LEFT): p.add("LEFT")
        if not G.input(BTN_RIGHT): p.add("RIGHT")
        if not G.input(BTN_OK): p.add("OK")
        return p

    def _load_track(self, idx, autoplay=False):
        if not self.queue: return
        self.queue_idx = idx % len(self.queue)
        t = self.queue[self.queue_idx]
        try:
            from mutagen import File as MF
            mf = MF(t["path"])
            self.duration = mf.info.length if mf and mf.info else 0.0
        except: self.duration = 0.0
        
        self.pos_sec = 0.0
        self._scroll_x = 0
        self._last_t = time.time()
        
        if self._audio_ok: pygame.mixer.music.load(t["path"])
        if (autoplay or self.playing) and self._audio_ok: pygame.mixer.music.play()
        self.playing = autoplay or self.playing
        self.paused = False

    def play_pause(self):
        if not self.queue: return
        if self.playing and not self.paused:
            if self._audio_ok: pygame.mixer.music.pause()
            self.paused = True
        elif self.paused:
            if self._audio_ok: pygame.mixer.music.unpause()
            self.paused = False
        else: self._load_track(self.queue_idx, autoplay=True)

    def next_track(self):
        if not self.queue: return
        nxt = random.randint(0, len(self.queue)-1) if self.shuffle else (self.queue_idx + 1) % len(self.queue)
        self._load_track(nxt, autoplay=True)

    def prev_track(self):
        if not self.queue: return
        if self.pos_sec > 3:
            if self._audio_ok: pygame.mixer.music.rewind()
            self.pos_sec = 0.0
        else: self._load_track((self.queue_idx - 1) % len(self.queue), autoplay=True)

    def _clamp(self, count):
        if count == 0: self.cursor = self.scroll = 0; return
        self.cursor = max(0, min(self.cursor, count-1))
        vis = self.ROWS_VIS
        if self.cursor < self.scroll: self.scroll = self.cursor
        elif self.cursor >= self.scroll + vis: self.scroll = self.cursor - vis + 1
        self.scroll = max(0, min(self.scroll, max(0, count - vis)))

    # ── Rendering ──────────────────────────────────────────────────────────────────
    def _draw_topbar(self, title):
        # Rysuje górny pasek. Jeśli motyw go nie ma, użyje pustej przestrzeni.
        self.surf.blit(self.th.topbar, (0, 0))
        ts = self.th.fnt_sub.render(title, True, self.th.txt_col)
        self.surf.blit(ts, (10, 2))

    def _draw_tabs(self):
        tabs = [("NOW", Screen.NOW_PLAYING), ("LIB", Screen.LIBRARY), 
                ("QUE", Screen.QUEUE), ("PLS", Screen.PLAYLISTS), ("OPT", Screen.OPTIONS)]
        y = SH - 20
        sw = SW // len(tabs)
        
        # Prosty overlay dla czytelności zakładek, żeby tło z motywu nie zlewało się z tekstem
        pygame.draw.rect(self.surf, (0, 0, 0, 180), (0, y, SW, 20))
        
        for i, (name, sid) in enumerate(tabs):
            x = i * sw
            active = (self.screen_id == sid) or (self.screen_id == Screen.PLAYLIST_VIEW and sid == Screen.PLAYLISTS)
            
            # Subtelne podkreślenie aktualnej zakładki kolorem motywu
            if active:
                pygame.draw.rect(self.surf, self.th.sel_col, (x, y+18, sw, 2))
                
            lbl = self.th.fnt_sub.render(name, True, self.th.txt_col)
            self.surf.blit(lbl, (x + sw//2 - lbl.get_width()//2, y + 2))

    def _draw_now_playing(self):
        self.surf.blit(self.th.bg, (0, 0))
        self._draw_topbar("NOW PLAYING")
        
        if self.queue:
            t = self.queue[self.queue_idx]
            
            # Title Marquee
            max_w = SW - 20
            ts = self.th.fnt_main.render(t["title"], True, self.th.txt_col)
            clip_r = pygame.Rect(10, 80, max_w, 30)
            self.surf.set_clip(clip_r)
            if ts.get_width() > max_w:
                self._scroll_x += self._scroll_dir * 1.0
                if self._scroll_x > ts.get_width() - max_w + 10: self._scroll_dir = -1
                if self._scroll_x < 0: self._scroll_dir = 1; self._scroll_x = 0
            self.surf.blit(ts, (10 - int(self._scroll_x), 80))
            self.surf.set_clip(None)
            
            # Artist
            art = self.th.fnt_sub.render(trunc(self.th.fnt_sub, t["artist"], max_w), True, self.th.txt_col)
            self.surf.blit(art, (10, 110))
            
            # Progress Bar (Używa sel_col jako dominującego akcentu)
            py = 140
            pygame.draw.rect(self.surf, (40, 40, 40), (10, py, SW-20, 4), border_radius=2)
            if self.duration > 0:
                fw = int((SW-20) * (self.pos_sec / self.duration))
                pygame.draw.rect(self.surf, self.th.sel_col, (10, py, fw, 4), border_radius=2)
            
            s = int(self.pos_sec); d = int(self.duration)
            tm_str = f"{s//60}:{s%60:02d} / {d//60}:{d%60:02d}"
            tm_s = self.th.fnt_sub.render(tm_str, True, self.th.txt_col)
            self.surf.blit(tm_s, (SW//2 - tm_s.get_width()//2, 150))
            
            stat = "▶" if (self.playing and not self.paused) else "⏸" if self.paused else "■"
            modes = f"SHF: {'ON' if self.shuffle else 'OFF'} | RPT: {self.repeat.name}"
            st = self.th.fnt_sub.render(f"{stat}  {modes}", True, self.th.txt_col)
            self.surf.blit(st, (SW//2 - st.get_width()//2, 175))

        self._draw_tabs()

    def _draw_list(self, title, items):
        self.surf.blit(self.th.bg, (0, 0))
        self._draw_topbar(title)
        
        y0 = 24
        self._clamp(len(items))

        for i in range(self.ROWS_VIS):
            idx = self.scroll + i
            if idx >= len(items): break
            t = items[idx]
            ry = y0 + i * self.ROW_H
            sel = (idx == self.cursor)
            
            # Natywny znacznik wyboru Innioasis (1.png)
            if sel: self.surf.blit(self.th.sel, (0, ry))
            
            name = t["title"] if isinstance(t, dict) else t
            ts = self.th.fnt_main.render(trunc(self.th.fnt_main, name, SW-10), True, self.th.txt_col)
            self.surf.blit(ts, (10, ry + 4))

        self._draw_tabs()

    def _draw_options(self):
        # Jeśli motyw ma plik cover.png (podgląd), pokaż go jako tło opcji. Jak nie, użyj zwykłego bg.
        bg_surface = self.th.cover if self.th.cover.get_alpha() is not None else self.th.bg
        self.surf.blit(bg_surface, (0, 0))
        
        # Półprzezroczysty overlay by opcje były czytelne
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.surf.blit(overlay, (0, 0))
        
        self._draw_topbar("OPTIONS")
        
        opts = [
            ("Theme", self.th.cfg.get("name", "Unknown")),
            ("Shuffle", "ON" if self.shuffle else "OFF"),
            ("Repeat", self.repeat.name)
        ]
        
        self._clamp(len(opts))
        y0 = 40
        
        for i, (k, v) in enumerate(opts):
            ry = y0 + i * 40
            sel = (i == self.cursor)
            
            if sel: self.surf.blit(self.th.sel, (0, ry))
            
            ks = self.th.fnt_sub.render(k, True, self.th.txt_col)
            vs = self.th.fnt_main.render(v, True, self.th.txt_col)
            self.surf.blit(ks, (10, ry + 8))
            self.surf.blit(vs, (SW - 10 - vs.get_width(), ry + 4))

        self._draw_tabs()

    def handle_btn(self, btn):
        sid = self.screen_id
        screens = [Screen.NOW_PLAYING, Screen.LIBRARY, Screen.QUEUE, Screen.PLAYLISTS, Screen.OPTIONS]

        if btn in ("LEFT", "RIGHT") and sid != Screen.OPTIONS:
            if sid == Screen.PLAYLIST_VIEW: self.screen_id = Screen.PLAYLISTS
            else:
                nxt = (screens.index(sid) + (1 if btn == "RIGHT" else -1)) % len(screens)
                self.screen_id = screens[nxt]
            self.cursor = self.scroll = 0
            return

        if sid == Screen.NOW_PLAYING:
            if btn == "OK": self.play_pause()
            elif btn == "UP": self.prev_track()
            elif btn == "DOWN": self.next_track()

        elif sid in (Screen.LIBRARY, Screen.QUEUE, Screen.PLAYLISTS, Screen.PLAYLIST_VIEW):
            items = self.library if sid == Screen.LIBRARY else self.queue
            if sid == Screen.PLAYLISTS: items = sorted(self.playlists.keys())
            elif sid == Screen.PLAYLIST_VIEW: items = self.playlists.get(self.sel_pl, [])
            
            if btn == "UP": self.cursor -= 1
            elif btn == "DOWN": self.cursor += 1
            elif btn == "OK" and items:
                if sid == Screen.LIBRARY:
                    self.queue = list(self.library)
                    self._load_track(self.cursor, autoplay=True)
                    self.screen_id = Screen.NOW_PLAYING
                elif sid == Screen.QUEUE:
                    self._load_track(self.cursor, autoplay=True)
                    self.screen_id = Screen.NOW_PLAYING
                elif sid == Screen.PLAYLISTS:
                    self.sel_pl = items[self.cursor]
                    self.screen_id = Screen.PLAYLIST_VIEW
                    self.cursor = self.scroll = 0

        elif sid == Screen.OPTIONS:
            if btn == "UP": self.cursor -= 1
            elif btn == "DOWN": self.cursor += 1
            elif btn in ("LEFT", "RIGHT", "OK"):
                dir_val = 1 if btn in ("RIGHT", "OK") else -1
                if self.cursor == 0:
                    self.theme_idx = (self.theme_idx + dir_val) % len(self.themes)
                    self.th = self.themes[self.theme_idx]
                elif self.cursor == 1: self.shuffle = not self.shuffle
                elif self.cursor == 2:
                    m = list(Repeat)
                    self.repeat = m[(m.index(self.repeat) + dir_val) % len(m)]

    def run(self):
        while True:
            if self.playing and not self.paused: self.pos_sec += time.time() - self._last_t
            self._last_t = time.time()
            
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT: sys.exit(0)
                elif ev.type == self.EV_END:
                    if self.repeat == Repeat.ONE: self._load_track(self.queue_idx, autoplay=True)
                    elif self.repeat == Repeat.ALL or self.queue_idx < len(self.queue)-1: self.next_track()
                    else: self.playing = self.paused = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_UP: self.handle_btn("UP")
                    elif ev.key == pygame.K_DOWN: self.handle_btn("DOWN")
                    elif ev.key == pygame.K_LEFT: self.handle_btn("LEFT")
                    elif ev.key == pygame.K_RIGHT: self.handle_btn("RIGHT")
                    elif ev.key in (pygame.K_RETURN, pygame.K_SPACE): self.handle_btn("OK")

            cur = self._read_gpio()
            for btn in cur - self._prev_gpio: self.handle_btn(btn)
            self._prev_gpio = cur

            if self.screen_id == Screen.NOW_PLAYING: self._draw_now_playing()
            elif self.screen_id == Screen.LIBRARY: self._draw_list("LIBRARY", self.library)
            elif self.screen_id == Screen.QUEUE: self._draw_list(f"QUEUE", self.queue)
            elif self.screen_id == Screen.PLAYLISTS: self._draw_list("PLAYLISTS", sorted(self.playlists.keys()))
            elif self.screen_id == Screen.OPTIONS: self._draw_options()
            
            pygame.display.flip()
            self.clock.tick(FPS)

if __name__ == "__main__":
    MusicPlayer(window_mode=True).run() # Ustaw window_mode=False dla Pi
