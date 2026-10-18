#!/usr/bin/env python3
"""
CAT'S PY PORT SPACE INVADERS — Famicom / NES 60 FPS Edition
===========================================================
Single-file retro arcade clone with 2C02 PPU-style pixel rendering and
real-time 2A03-inspired synthesized audio ("beeps n boops = true") in RAM.

Flags:
  60 fps        = True
  speed         = "nes" / "famicom"
  main menu     = True (PLAY, HELP, ABOUT, EXIT)
  beeps n boops = True
  files         = OFF (100% self-contained in RAM)
"""

from __future__ import annotations

import math
import random
import sys
from array import array
from dataclasses import dataclass

try:
    import pygame
except ImportError:
    sys.stderr.write(
        "cat's py port space invaders requires pygame or pygame-ce.\n"
        "Install with: python3 -m pip install pygame-ce\n"
    )
    raise SystemExit(1)

# =============================================================================
# ENGINE CONFIGURATION & FLAGS
# =============================================================================
FPS_60 = True
FPS = 60
SPEED = "NES"                  # Famicom / NES hardware speed profile
FAMICOM_SPEED = True
MAIN_MENU = True
BEEPS_N_BOOPS = True
FILES_OFF = True               # Zero external files; all assets built in RAM

# Native Famicom / NES 2C02 Resolution (256x240) scaled 3x (768x720)
NES_W, NES_H = 256, 240
SCALE = 3
WINDOW_W, WINDOW_H = NES_W * SCALE, NES_H * SCALE

# Fort Command / 2C02 Blue-Hue Palette
PALETTE = {
    "bg_void": (6, 10, 22),          # Deep Famicom space navy
    "bg_panel": (16, 26, 48),        # UI panel dark blue
    "btn_black": (0, 0, 0),          # Black button background
    "btn_hover": (14, 30, 58),       # Active button fill
    "border_blue": (45, 110, 205),   # Border highlight
    "text_blue": (126, 182, 255),    # #7eb6ff signature blue text
    "text_bright": (225, 242, 255),  # Crisp white-blue highlight
    "cyan": (0, 228, 255),           # Squid row / accents
    "green": (82, 242, 110),         # Shield / Octopus row / Earth line
    "magenta": (248, 104, 255),      # Crab row
    "red": (255, 72, 92),            # Mystery UFO / warnings
    "gold": (255, 216, 84),          # Hi-Score / trophies
}

MENU_ITEMS = ("PLAY", "HELP", "ABOUT", "EXIT")


# =============================================================================
# 2A03 FAMICOM / NES SYNTHESIZER ("beeps n boops = true")
# =============================================================================
class NesBeepsBoopsSynth:
    """Generates 16-bit mono PCM sound effects in RAM with zero external files."""

    RATE = 22050

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.ready = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=self.RATE, size=-16, channels=1, buffer=512)
            pygame.mixer.set_num_channels(8)
            self._build_sound_bank()
            self.ready = True
        except Exception:
            self.ready = False
            self.sounds.clear()

    @staticmethod
    def _osc(phase: float, wave: str) -> float:
        p = phase % 1.0
        if wave == "square":
            return 1.0 if p < 0.5 else -1.0
        if wave == "pulse25":
            return 1.0 if p < 0.25 else -1.0
        if wave == " pulse12":
            return 1.0 if p < 0.125 else -1.0
        if wave == "triangle":
            return 1.0 - 4.0 * abs(p - 0.5)
        return math.sin(p * math.tau)

    def _synth_tone(
        self,
        f_start: float,
        f_end: float,
        duration: float,
        wave: str = "square",
        vol: float = 0.35,
        vibrato_hz: float = 0.0,
        vibrato_depth: float = 0.0,
    ) -> bytes:
        n_samples = max(1, int(self.RATE * duration))
        buf = array("h")
        phase = 0.0
        for i in range(n_samples):
            t = i / n_samples
            freq = f_start + (f_end - f_start) * t
            if vibrato_hz > 0.0:
                freq += math.sin((i / self.RATE) * math.tau * vibrato_hz) * vibrato_depth
            phase += max(20.0, freq) / self.RATE
            # Fast attack, smooth NES envelope decay
            env = min(1.0, i / max(1, int(0.004 * self.RATE))) * (1.0 - 0.65 * t)
            sample = int(32767 * vol * env * self._osc(phase, wave))
            buf.append(max(-32768, min(32767, sample)))
        if sys.byteorder != "little":
            buf.byteswap()
        return buf.tobytes()

    def _synth_noise(
        self,
        duration: float,
        vol: float = 0.35,
        hold_steps: int = 4,
        pitch_sweep: float = 0.0,
    ) -> bytes:
        n_samples = max(1, int(self.RATE * duration))
        buf = array("h")
        rng = random.Random(0x2A03)
        current = 0.0
        phase = 0.0
        for i in range(n_samples):
            t = i / n_samples
            step = max(1, int(hold_steps + t * 10))
            if i % step == 0:
                current = rng.uniform(-1.0, 1.0)
            tone_mix = 0.0
            if pitch_sweep > 0.0:
                phase += (pitch_sweep * (1.0 - 0.7 * t)) / self.RATE
                tone_mix = 0.45 * self._osc(phase, "square")
            env = (1.0 - t) ** 1.35
            val = (0.65 * current + tone_mix) * vol * env
            buf.append(max(-32768, min(32767, int(32767 * val))))
        if sys.byteorder != "little":
            buf.byteswap()
        return buf.tobytes()

    def _concat(self, *ByteChunks: bytes) -> bytes:
        out = bytearray()
        for b in ByteChunks:
            out.extend(b)
        return bytes(out)

    def _build_sound_bank(self) -> None:
        # 4-Note Famicom Invader March (A1 -> G1 -> F1 -> E1 with triangle + pulse punch)
        march_freqs = (110.0, 98.0, 87.31, 82.41)
        for idx, freq in enumerate(march_freqs):
            raw = self._synth_tone(freq * 1.5, freq, 0.075, "pulse25", 0.32)
            self.sounds[f"march_{idx}"] = pygame.mixer.Sound(buffer=raw)

        # UI Beeps & Boops
        self.sounds["beep"] = pygame.mixer.Sound(
            buffer=self._synth_tone(660.0, 720.0, 0.045, "square", 0.25)
        )
        self.sounds["boop"] = pygame.mixer.Sound(
            buffer=self._synth_tone(520.0, 340.0, 0.06, "triangle", 0.28)
        )
        self.sounds["select"] = pygame.mixer.Sound(
            buffer=self._concat(
                self._synth_tone(587.33, 587.33, 0.055, "square", 0.28),
                self._synth_tone(880.0, 987.77, 0.095, "pulse25", 0.30),
            )
        )

        # Gameplay SFX
        self.sounds["shoot"] = pygame.mixer.Sound(
            buffer=self._synth_tone(1350.0, 260.0, 0.11, "pulse25", 0.30)
        )
        self.sounds["invader_hit"] = pygame.mixer.Sound(
            buffer=self._synth_noise(0.14, vol=0.32, hold_steps=2, pitch_sweep=520.0)
        )
        self.sounds["player_die"] = pygame.mixer.Sound(
            buffer=self._synth_noise(0.45, vol=0.42, hold_steps=5, pitch_sweep=160.0)
        )
        self.sounds["ufo"] = pygame.mixer.Sound(
            buffer=self._synth_tone(
                620.0, 620.0, 0.16, "square", 0.20, vibrato_hz=14.0, vibrato_depth=140.0
            )
        )
        self.sounds["ufo_hit"] = pygame.mixer.Sound(
            buffer=self._concat(
                self._synth_tone(960.0, 420.0, 0.12, "square", 0.34),
                self._synth_tone(740.0, 220.0, 0.18, "pulse25", 0.34),
            )
        )
        self.sounds["wave_clear"] = pygame.mixer.Sound(
            buffer=self._concat(
                self._synth_tone(523.25, 523.25, 0.08, "square", 0.28),
                self._synth_tone(659.25, 659.25, 0.08, "square", 0.28),
                self._synth_tone(783.99, 783.99, 0.08, "square", 0.28),
                self._synth_tone(1046.50, 1046.50, 0.18, "pulse25", 0.32),
            )
        )

    def play(self, name: str) -> None:
        if self.enabled and self.ready and name in self.sounds:
            self.sounds[name].play()


# =============================================================================
# 2C02 PPU SPRITE BITMAPS (100% IN RAM)
# =============================================================================
SPRITE_PATTERNS: dict[str, tuple[str, ...]] = {
    # Top row Squid (30 PTS) - 2 animation frames (8x8)
    "squid_0": (
        "...11...",
        "..1111..",
        ".111111.",
        "11.11.11",
        "11111111",
        "..1..1..",
        ".1.11.1.",
        "1.1..1.1",
    ),
    "squid_1": (
        "...11...",
        "..1111..",
        ".111111.",
        "11.11.11",
        "11111111",
        ".1.11.1.",
        "1......1",
        ".1....1.",
    ),
    # Middle rows Crab (20 PTS) - 2 animation frames (11x8)
    "crab_0": (
        "..1.....1..",
        "...1...1...",
        "..1111111..",
        ".11.111.11.",
        "11111111111",
        "1.1111111.1",
        "1.1.....1.1",
        "...11.11...",
    ),
    "crab_1": (
        "..1.....1..",
        "1..1...1..1",
        "1.1111111.1",
        "111.111.111",
        "11111111111",
        ".111111111.",
        "..1.....1..",
        ".1.......1.",
    ),
    # Bottom rows Octopus (10 PTS) - 2 animation frames (12x8)
    "octopus_0": (
        "....1111....",
        ".1111111111.",
        "111111111111",
        "111..11..111",
        "111111111111",
        "...11..11...",
        "..11.11.11..",
        "11........11",
    ),
    "octopus_1": (
        "....1111....",
        ".1111111111.",
        "111111111111",
        "111..11..111",
        "111111111111",
        "..111..111..",
        ".11..11..11.",
        "..11....11..",
    ),
    # Mystery UFO Saucer (16x7)
    "ufo": (
        ".....111111.....",
        "...1111111111...",
        "..111111111111..",
        ".11.11.11.11.11.",
        "1111111111111111",
        "..111..11..111..",
        "...1........1...",
    ),
    # Player Laser Cannon (13x8)
    "player": (
        "......1......",
        ".....111.....",
        ".....111.....",
        ".11111111111.",
        "1111111111111",
        "1111111111111",
        "1111111111111",
        "1111111111111",
    ),
    # Alien Explosion Burst (12x8)
    "boom": (
        ".1...1...1..",
        "..1..1..1...",
        "...1...1....",
        "11.........1",
        "....1...1...",
        "..1..1...1..",
        ".1...1....1.",
        "1.........1.",
    ),
}

SHIELD_BITMAP = (
    "....11111111111111....",
    "...1111111111111111...",
    "..111111111111111111..",
    ".11111111111111111111.",
    "1111111111111111111111",
    "1111111111111111111111",
    "1111111111111111111111",
    "1111111111111111111111",
    "1111111111111111111111",
    "1111111111111111111111",
    "1111111111111111111111",
    "1111111111111111111111",
    "1111111........1111111",
    "111111..........111111",
    "11111............11111",
    "11111............11111",
)


def make_sprite_surface(pattern: tuple[str, ...], color: tuple[int, int, int]) -> pygame.Surface:
    h = len(pattern)
    w = len(pattern[0])
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for y, row in enumerate(pattern):
        for x, ch in enumerate(row):
            if ch == "1":
                surf.set_at((x, y), color)
    return surf


# =============================================================================
# GAME ENTITIES
# =============================================================================
@dataclass
class Invader:
    row: int
    col: int
    x: float
    y: float
    kind: str
    points: int
    alive: bool = True

    @property
    def width(self) -> int:
        return 8 if self.kind == "squid" else (11 if self.kind == "crab" else 12)

    @property
    def height(self) -> int:
        return 8

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)


@dataclass
class Bullet:
    x: float
    y: float
    vy: float
    from_player: bool
    color: tuple[int, int, int]

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), 2, 5)


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: int
    color: tuple[int, int, int]


@dataclass
class PopEffect:
    x: int
    y: int
    timer: int
    text: str = ""
    color: tuple[int, int, int] = PALETTE["text_bright"]


# =============================================================================
# SPACE INVADERS NES / FAMICOM ENGINE
# =============================================================================
class CatsSpaceInvadersEngine:
    def __init__(self) -> None:
        pygame.mixer.pre_init(NesBeepsBoopsSynth.RATE, -16, 1, 512)
        pygame.init()
        pygame.font.init()

        self.window = pygame.display.set_mode(
            (WINDOW_W, WINDOW_H), pygame.RESIZABLE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption(
            "cat's py port space invaders — 60 FPS [SPEED = NES / FAMICOM]"
        )

        self.canvas = pygame.Surface((NES_W, NES_H)).convert()
        self.clock = pygame.time.Clock()
        self.synth = NesBeepsBoopsSynth(enabled=BEEPS_N_BOOPS)

        self.font_sm = self._load_font(10, bold=True)
        self.font_md = self._load_font(12, bold=True)
        self.font_lg = self._load_font(16, bold=True)

        self.sprites = self._build_sprites()
        self.stars = [
            [random.randrange(NES_W), random.randrange(24, NES_H - 16), random.choice((1, 2))]
            for _ in range(38)
        ]

        # Engine State Machine
        self.state = "menu" if MAIN_MENU else "play"  # 'menu' | 'play' | 'help' | 'about' | 'gameover'
        self.menu_idx = 0
        self.menu_rects: list[pygame.Rect] = []
        self.back_rect = pygame.Rect(88, 206, 80, 18)

        # Arcade Telemetry
        self.score = 0
        self.high_score = 1500
        self.lives = 3
        self.wave = 1
        self.paused = False
        self.running = True
        self.tick_count = 0

        # Gameplay Objects
        self.player_x = NES_W // 2 - 6
        self.player_y = 212
        self.player_cooldown = 0
        self.respawn_timer = 0

        self.invaders: list[Invader] = []
        self.fleet_dir = 1
        self.fleet_frame = 0
        self.fleet_step_timer = 0
        self.march_note = 0

        self.bullets: list[Bullet] = []
        self.shields: list[tuple[int, int, pygame.Surface]] = []
        self.particles: list[Particle] = []
        self.pops: list[PopEffect] = []

        # Mystery UFO
        self.ufo_active = False
        self.ufo_x = 0.0
        self.ufo_y = 26
        self.ufo_dir = 1
        self.ufo_spawn_timer = 420
        self.ufo_hum_timer = 0

        self._init_new_game()

    @staticmethod
    def _load_font(size: int, bold: bool = False) -> pygame.font.Font:
        for name in ("consolas", "menlo", "couriernew", "dejavusansmono", "monospace"):
            matched = pygame.font.match_font(name, bold=bold)
            if matched:
                try:
                    return pygame.font.Font(matched, size)
                except Exception:
                    pass
        return pygame.font.Font(None, size + 4)

    def _build_sprites(self) -> dict[str, pygame.Surface]:
        return {
            "squid_0": make_sprite_surface(SPRITE_PATTERNS["squid_0"], PALETTE["cyan"]),
            "squid_1": make_sprite_surface(SPRITE_PATTERNS["squid_1"], PALETTE["cyan"]),
            "crab_0": make_sprite_surface(SPRITE_PATTERNS["crab_0"], PALETTE["magenta"]),
            "crab_1": make_sprite_surface(SPRITE_PATTERNS["crab_1"], PALETTE["magenta"]),
            "octopus_0": make_sprite_surface(SPRITE_PATTERNS["octopus_0"], PALETTE["green"]),
            "octopus_1": make_sprite_surface(SPRITE_PATTERNS["octopus_1"], PALETTE["green"]),
            "ufo": make_sprite_surface(SPRITE_PATTERNS["ufo"], PALETTE["red"]),
            "player": make_sprite_surface(SPRITE_PATTERNS["player"], PALETTE["cyan"]),
            "boom": make_sprite_surface(SPRITE_PATTERNS["boom"], PALETTE["gold"]),
        }

    # =========================================================================
    # WAVE & SHIELD INITIALIZATION
    # =========================================================================
    def _init_new_game(self) -> None:
        self.score = 0
        self.lives = 3
        self.wave = 1
        self.paused = False
        self.player_x = NES_W // 2 - 6
        self.respawn_timer = 0
        self._build_shields()
        self._spawn_wave()

    def _build_shields(self) -> None:
        self.shields.clear()
        spacing = 54
        start_x = 28
        for i in range(4):
            sx = start_x + i * spacing
            sy = 184
            surf = make_sprite_surface(SHIELD_BITMAP, PALETTE["green"])
            self.shields.append((sx, sy, surf))

    def _spawn_wave(self) -> None:
        self.invaders.clear()
        self.bullets.clear()
        self.fleet_dir = 1
        self.fleet_frame = 0
        self.fleet_step_timer = 0
        self.march_note = 0
        self.ufo_active = False
        self.ufo_spawn_timer = random.randint(360, 620)

        # Classic 5 rows x 11 columns formation, steps lower each wave (NES style)
        top_offset = min(78, 42 + (self.wave - 1) * 5)
        row_specs = (
            ("squid", 30),
            ("crab", 20),
            ("crab", 20),
            ("octopus", 10),
            ("octopus", 10),
        )
        for r, (kind, pts) in enumerate(row_specs):
            for c in range(11):
                ix = 24 + c * 18
                iy = top_offset + r * 14
                self.invaders.append(Invader(r, c, float(ix), float(iy), kind, pts, True))

    # =========================================================================
    # NES / FAMICOM SPEED & LOGIC UPDATE (LOCKED 60 FPS)
    # =========================================================================
    def _alive_invaders(self) -> list[Invader]:
        return [inv for inv in self.invaders if inv.alive]

    def _famicom_step_delay(self, alive_count: int) -> int:
        """
        Authentic Famicom/NES Space Invaders speed curve:
        Starts around 34 frames per march step at 55 aliens and accelerates
        exponentially down to 1 frame (60Hz blitz) for the final alien!
        """
        if alive_count <= 1:
            return 1
        if alive_count <= 3:
            return 2
        if alive_count <= 6:
            return 4
        if alive_count <= 12:
            return 7
        if alive_count <= 22:
            return 12
        if alive_count <= 35:
            return 18
        return max(10, int(24 + (alive_count - 35) * 0.5) - (self.wave - 1) * 2)

    def _spawn_particles(
        self, x: float, y: float, color: tuple[int, int, int], count: int = 12
    ) -> None:
        for _ in range(count):
            ang = random.uniform(0.0, math.tau)
            spd = random.uniform(0.5, 2.4)
            self.particles.append(
                Particle(
                    x,
                    y,
                    math.cos(ang) * spd,
                    math.sin(ang) * spd,
                    random.randint(10, 22),
                    color,
                )
            )

    def _damage_shield(self, surf: pygame.Surface, lx: int, ly: int, radius: int = 3) -> None:
        w, h = surf.get_size()
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= radius * radius + 1:
                    px, py = lx + dx, ly + dy
                    if 0 <= px < w and 0 <= py < h:
                        surf.set_at((px, py), (0, 0, 0, 0))

    def _check_shield_hit(self, b: Bullet) -> bool:
        brect = b.rect
        for sx, sy, surf in self.shields:
            srect = pygame.Rect(sx, sy, surf.get_width(), surf.get_height())
            if not brect.colliderect(srect):
                continue
            # Check pixel-level collision inside bunker bitmap
            for py in range(max(brect.top, srect.top), min(brect.bottom, srect.bottom)):
                for px in range(max(brect.left, srect.left), min(brect.right, srect.right)):
                    lx, ly = px - sx, py - sy
                    if surf.get_at((lx, ly)).a > 0:
                        self._damage_shield(surf, lx, ly, radius=3)
                        self._spawn_particles(px, py, PALETTE["green"], count=5)
                        return True
        return False

    def update_play(self, keys: pygame.key.ScancodeWrapper) -> None:
        if self.paused:
            return

        # Update particles & popups
        for p in self.particles[:]:
            p.x += p.vx
            p.y += p.vy
            p.life -= 1
            if p.life <= 0:
                self.particles.remove(p)

        for pop in self.pops[:]:
            pop.timer -= 1
            if pop.timer <= 0:
                self.pops.remove(pop)

        # Handle player respawn pause
        if self.respawn_timer > 0:
            self.respawn_timer -= 1
            return

        # 1. Player Movement (Famicom 60Hz crisp 2px/frame response)
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player_x = max(10.0, self.player_x - 2.0)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player_x = min(float(NES_W - 23), self.player_x + 2.0)

        if self.player_cooldown > 0:
            self.player_cooldown -= 1

        player_bullets = [b for b in self.bullets if b.from_player]
        if (keys[pygame.K_SPACE] or keys[pygame.K_z] or keys[pygame.K_UP]) and (
            len(player_bullets) == 0 and self.player_cooldown == 0
        ):
            self.bullets.append(
                Bullet(self.player_x + 6, self.player_y - 4, -3.8, True, PALETTE["cyan"])
            )
            self.player_cooldown = 12
            self.synth.play("shoot")

        # 2. Mystery UFO Logic
        if not self.ufo_active:
            self.ufo_spawn_timer -= 1
            if self.ufo_spawn_timer <= 0:
                self.ufo_active = True
                self.ufo_dir = random.choice((-1, 1))
                self.ufo_x = -16.0 if self.ufo_dir == 1 else float(NES_W)
                self.ufo_hum_timer = 0
        else:
            self.ufo_x += self.ufo_dir * 1.15
            self.ufo_hum_timer -= 1
            if self.ufo_hum_timer <= 0:
                self.synth.play("ufo")
                self.ufo_hum_timer = 14
            if self.ufo_x < -20 or self.ufo_x > NES_W + 20:
                self.ufo_active = False
                self.ufo_spawn_timer = random.randint(480, 780)

        # 3. Invader Fleet March (NES Speed Profile)
        alive = self._alive_invaders()
        if not alive:
            self.wave += 1
            self.synth.play("wave_clear")
            self._spawn_wave()
            return

        step_delay = self._famicom_step_delay(len(alive))
        self.fleet_step_timer += 1
        if self.fleet_step_timer >= step_delay:
            self.fleet_step_timer = 0
            self.fleet_frame ^= 1
            self.synth.play(f"march_{self.march_note}")
            self.march_note = (self.march_note + 1) & 3

            step_px = 3.0 if len(alive) == 1 else 2.0
            hit_edge = any(
                (inv.x + self.fleet_dir * step_px < 10)
                or (inv.x + inv.width + self.fleet_dir * step_px > NES_W - 10)
                for inv in alive
            )
            if hit_edge:
                self.fleet_dir *= -1
                for inv in alive:
                    inv.y += 6.0
            else:
                for inv in alive:
                    inv.x += self.fleet_dir * step_px

            # Check if invaders reached bunkers or defense line
            for inv in alive:
                if inv.y + inv.height >= self.player_y:
                    self.lives = 0
                    self.synth.play("player_die")
                    self.state = "gameover"
                    return

        # 4. Enemy Laser Firing
        enemy_bullets = [b for b in self.bullets if not b.from_player]
        max_enemy_shots = min(4, 1 + self.wave // 2 + (1 if len(alive) < 15 else 0))
        fire_chance = 0.022 + (55 - len(alive)) * 0.0006
        if len(enemy_bullets) < max_enemy_shots and random.random() < fire_chance:
            # Pick lowest alive invader in a random column
            cols: dict[int, Invader] = {}
            for inv in alive:
                if inv.col not in cols or inv.y > cols[inv.col].y:
                    cols[inv.col] = inv
            shooter = random.choice(list(cols.values()))
            self.bullets.append(
                Bullet(
                    shooter.x + shooter.width / 2,
                    shooter.y + shooter.height,
                    2.1 + min(1.2, self.wave * 0.15),
                    False,
                    PALETTE["red"],
                )
            )

        # 5. Bullet Movement & Collisions
        player_rect = pygame.Rect(int(self.player_x), self.player_y, 13, 8)
        ufo_rect = pygame.Rect(int(self.ufo_x), self.ufo_y, 16, 7)

        for b in self.bullets[:]:
            b.y += b.vy
            if b.y < 20 or b.y > NES_H - 18:
                self.bullets.remove(b)
                continue

            if self._check_shield_hit(b):
                self.bullets.remove(b)
                continue

            if b.from_player:
                # Check UFO hit
                if self.ufo_active and b.rect.colliderect(ufo_rect):
                    bonus = random.choice((50, 100, 150, 300))
                    self.score += bonus
                    self.high_score = max(self.high_score, self.score)
                    self.ufo_active = False
                    self.ufo_spawn_timer = random.randint(480, 780)
                    self.synth.play("ufo_hit")
                    self._spawn_particles(self.ufo_x + 8, self.ufo_y + 3, PALETTE["red"], 18)
                    self.pops.append(
                        PopEffect(int(self.ufo_x), self.ufo_y, 35, f"{bonus}", PALETTE["gold"])
                    )
                    self.bullets.remove(b)
                    continue

                # Check Invader hit
                hit_inv = None
                for inv in alive:
                    if b.rect.colliderect(inv.rect):
                        hit_inv = inv
                        break
                if hit_inv is not None:
                    hit_inv.alive = False
                    self.score += hit_inv.points
                    self.high_score = max(self.high_score, self.score)
                    self.synth.play("invader_hit")
                    self._spawn_particles(
                        hit_inv.x + hit_inv.width / 2,
                        hit_inv.y + 4,
                        PALETTE["cyan"] if hit_inv.row == 0 else PALETTE["magenta"],
                        12,
                    )
                    self.pops.append(PopEffect(int(hit_inv.x), int(hit_inv.y), 10))
                    self.bullets.remove(b)
                    continue
            else:
                # Enemy bullet hits player
                if b.rect.colliderect(player_rect):
                    self.bullets.remove(b)
                    self.lives -= 1
                    self.synth.play("player_die")
                    self._spawn_particles(self.player_x + 6, self.player_y + 4, PALETTE["cyan"], 24)
                    if self.lives <= 0:
                        self.state = "gameover"
                    else:
                        self.respawn_timer = 55
                        self.bullets.clear()
                    return

    # =========================================================================
    # RENDERING (256x240 PPU CANVAS -> INTEGER WINDOW SCALE)
    # =========================================================================
    def _draw_text(
        self,
        text: str,
        x: int,
        y: int,
        color: tuple[int, int, int] = PALETTE["text_blue"],
        font: pygame.font.Font | None = None,
        center: bool = False,
    ) -> pygame.Rect:
        use_font = font or self.font_sm
        shadow = use_font.render(text, False, (0, 0, 0))
        surf = use_font.render(text, False, color)
        rect = surf.get_rect()
        if center:
            rect.centerx = x
            rect.top = y
        else:
            rect.topleft = (x, y)
        self.canvas.blit(shadow, (rect.x + 1, rect.y + 1))
        self.canvas.blit(surf, rect)
        return rect

    def _draw_starfield(self) -> None:
        self.canvas.fill(PALETTE["bg_void"])
        for star in self.stars:
            sx, sy, layer = star
            if self.tick_count % (4 if layer == 1 else 2) == 0:
                star[1] = 24 + ((sy - 23) % (NES_H - 42))
            c = (45, 78, 130) if layer == 1 else (90, 145, 220)
            self.canvas.set_at((sx, star[1]), c)

    def _draw_top_hud(self) -> None:
        pygame.draw.rect(self.canvas, PALETTE["bg_panel"], (0, 0, NES_W, 20))
        pygame.draw.line(self.canvas, PALETTE["border_blue"], (0, 20), (NES_W, 20), 1)
        self._draw_text(f"SCORE {self.score:05d}", 6, 4, PALETTE["text_bright"])
        self._draw_text(
            f"HI {self.high_score:05d}", NES_W // 2, 4, PALETTE["gold"], center=True
        )
        self._draw_text(f"W-{self.wave:02d}", NES_W - 38, 4, PALETTE["cyan"])

    def _draw_bottom_hud(self) -> None:
        pygame.draw.line(self.canvas, PALETTE["green"], (8, 224), (NES_W - 8, 224), 1)
        self._draw_text(f"LIVES {self.lives}", 8, 227, PALETTE["text_blue"])
        for i in range(max(0, self.lives - 1)):
            self.canvas.blit(self.sprites["player"], (58 + i * 16, 228))
        self._draw_text(
            "60FPS · SPEED=NES/FAMICOM", NES_W - 148, 227, PALETTE["text_blue"]
        )

    def _draw_menu(self) -> None:
        self._draw_starfield()
        self._draw_top_hud()

        # Hero Logo Card (Blue-Hue Frame + Black Interior)
        card = pygame.Rect(14, 26, NES_W - 28, 82)
        pygame.draw.rect(self.canvas, (4, 8, 18), card)
        pygame.draw.rect(self.canvas, PALETTE["border_blue"], card, 2)
        pygame.draw.rect(self.canvas, PALETTE["cyan"], card.inflate(-4, -4), 1)

        # Required Logo: "cat's py port space invaders"
        self._draw_text(
            "CAT'S PY PORT",
            NES_W // 2,
            34,
            PALETTE["cyan"],
            self.font_md,
            center=True,
        )
        self._draw_text(
            "SPACE INVADERS",
            NES_W // 2,
            50,
            PALETTE["gold"],
            self.font_lg,
            center=True,
        )
        self._draw_text(
            "60 FPS = TRUE  ·  SPEED = NES / FAMICOM",
            NES_W // 2,
            72,
            PALETTE["text_blue"],
            self.font_sm,
            center=True,
        )

        # Animated Invader Parade inside Logo Card
        frame = (self.tick_count // 20) & 1
        self.canvas.blit(self.sprites[f"squid_{frame}"], (52, 90))
        self._draw_text("=30", 63, 89, PALETTE["cyan"])
        self.canvas.blit(self.sprites[f"crab_{frame}"], (98, 90))
        self._draw_text("=20", 112, 89, PALETTE["magenta"])
        self.canvas.blit(self.sprites[f"octopus_{frame}"], (146, 90))
        self._draw_text("=10", 161, 89, PALETTE["green"])
        self.canvas.blit(self.sprites["ufo"], (192, 91))

        # Black Buttons with #7eb6ff Blue Text
        self.menu_rects.clear()
        for i, label in enumerate(MENU_ITEMS):
            selected = i == self.menu_idx
            btn_rect = pygame.Rect(58, 116 + i * 24, 140, 20)
            self.menu_rects.append(btn_rect)

            bg_col = PALETTE["btn_hover"] if selected else PALETTE["btn_black"]
            border_col = PALETTE["cyan"] if selected else PALETTE["border_blue"]
            text_col = PALETTE["text_bright"] if selected else PALETTE["text_blue"]

            pygame.draw.rect(self.canvas, bg_col, btn_rect)
            pygame.draw.rect(self.canvas, border_col, btn_rect, 1)
            prefix = "> " if selected else "  "
            self._draw_text(
                f"{prefix}{label}",
                btn_rect.centerx,
                btn_rect.y + 4,
                text_col,
                self.font_md,
                center=True,
            )

        self._draw_text(
            "ARROWS/MOUSE SELECT · ENTER/CLICK OK · B BEEP",
            NES_W // 2,
            216,
            PALETTE["text_blue"],
            self.font_sm,
            center=True,
        )
        self._draw_bottom_hud()

    def _draw_info_modal(self, heading: str, lines: tuple[str, ...]) -> None:
        self._draw_starfield()
        self._draw_top_hud()

        box = pygame.Rect(14, 28, NES_W - 28, 190)
        pygame.draw.rect(self.canvas, (4, 8, 18), box)
        pygame.draw.rect(self.canvas, PALETTE["border_blue"], box, 2)

        self._draw_text(heading, NES_W // 2, 38, PALETTE["gold"], self.font_md, center=True)
        pygame.draw.line(self.canvas, PALETTE["border_blue"], (28, 54), (NES_W - 28, 54), 1)

        for idx, line in enumerate(lines):
            self._draw_text(
                line,
                NES_W // 2,
                64 + idx * 16,
                PALETTE["text_blue"] if idx % 2 == 0 else PALETTE["text_bright"],
                self.font_sm,
                center=True,
            )

        # Back button (Black background + Blue text)
        pygame.draw.rect(self.canvas, PALETTE["btn_black"], self.back_rect)
        pygame.draw.rect(self.canvas, PALETTE["cyan"], self.back_rect, 1)
        self._draw_text(
            "< BACK (ESC)",
            self.back_rect.centerx,
            self.back_rect.y + 4,
            PALETTE["text_blue"],
            self.font_sm,
            center=True,
        )
        self._draw_bottom_hud()

    def _draw_play(self) -> None:
        self._draw_starfield()
        self._draw_top_hud()

        # Mystery UFO
        if self.ufo_active:
            self.canvas.blit(self.sprites["ufo"], (int(self.ufo_x), self.ufo_y))

        # Destructible Shields
        for sx, sy, surf in self.shields:
            self.canvas.blit(surf, (sx, sy))

        # Invaders
        for inv in self.invaders:
            if not inv.alive:
                continue
            spr = self.sprites[f"{inv.kind}_{self.fleet_frame}"]
            self.canvas.blit(spr, (int(inv.x), int(inv.y)))

        # Pop / Explosion Effects
        for pop in self.pops:
            if pop.text:
                self._draw_text(pop.text, pop.x, pop.y, pop.color, self.font_sm)
            else:
                self.canvas.blit(self.sprites["boom"], (pop.x, pop.y))

        # Bullets
        for b in self.bullets:
            pygame.draw.rect(self.canvas, b.color, b.rect)

        # Player Cannon
        if self.respawn_timer == 0 or (self.respawn_timer // 4) % 2 == 0:
            self.canvas.blit(self.sprites["player"], (int(self.player_x), self.player_y))

        # Particles
        for p in self.particles:
            if 0 <= int(p.x) < NES_W and 0 <= int(p.y) < NES_H:
                self.canvas.set_at((int(p.x), int(p.y)), p.color)

        self._draw_bottom_hud()

        if self.paused:
            overlay = pygame.Rect(48, 92, NES_W - 96, 56)
            pygame.draw.rect(self.canvas, PALETTE["btn_black"], overlay)
            pygame.draw.rect(self.canvas, PALETTE["cyan"], overlay, 2)
            self._draw_text("PAUSED", NES_W // 2, 102, PALETTE["gold"], self.font_md, center=True)
            self._draw_text(
                "P RESUME  ·  ESC MAIN MENU",
                NES_W // 2,
                124,
                PALETTE["text_blue"],
                self.font_sm,
                center=True,
            )

        if self.state == "gameover":
            overlay = pygame.Rect(38, 80, NES_W - 76, 78)
            pygame.draw.rect(self.canvas, PALETTE["btn_black"], overlay)
            pygame.draw.rect(self.canvas, PALETTE["red"], overlay, 2)
            self._draw_text(
                "GAME OVER", NES_W // 2, 90, PALETTE["red"], self.font_lg, center=True
            )
            self._draw_text(
                f"FINAL SCORE: {self.score:05d}",
                NES_W // 2,
                114,
                PALETTE["text_bright"],
                self.font_sm,
                center=True,
            )
            self._draw_text(
                "ENTER/R RETRY  ·  ESC MENU",
                NES_W // 2,
                134,
                PALETTE["text_blue"],
                self.font_sm,
                center=True,
            )

    def present(self) -> None:
        ww, wh = self.window.get_size()
        scale = max(1, min(ww // NES_W, wh // NES_H))
        sw, sh = NES_W * scale, NES_H * scale
        ox, oy = (ww - sw) // 2, (wh - sh) // 2
        self.window.fill((0, 0, 0))
        scaled = pygame.transform.scale(self.canvas, (sw, sh))
        self.window.blit(scaled, (ox, oy))
        pygame.display.flip()

    def _window_to_nes(self, pos: tuple[int, int]) -> tuple[int, int]:
        ww, wh = self.window.get_size()
        scale = max(1, min(ww // NES_W, wh // NES_H))
        sw, sh = NES_W * scale, NES_H * scale
        ox, oy = (ww - sw) // 2, (wh - sh) // 2
        nx = (pos[0] - ox) // scale
        ny = (pos[1] - oy) // scale
        return nx, ny

    # =========================================================================
    # INPUT & MENU DISPATCH
    # =========================================================================
    def _activate_menu_choice(self, choice: str) -> None:
        self.synth.play("select")
        if choice == "PLAY":
            self._init_new_game()
            self.state = "play"
        elif choice == "HELP":
            self.state = "help"
        elif choice == "ABOUT":
            self.state = "about"
        elif choice == "EXIT":
            self.running = False

    def handle_events(self) -> None:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
                return

            if ev.type == pygame.MOUSEMOTION and self.state == "menu":
                nx, ny = self._window_to_nes(ev.pos)
                for idx, r in enumerate(self.menu_rects):
                    if r.collidepoint(nx, ny) and self.menu_idx != idx:
                        self.menu_idx = idx
                        self.synth.play("beep")

            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                nx, ny = self._window_to_nes(ev.pos)
                if self.state == "menu":
                    for idx, r in enumerate(self.menu_rects):
                        if r.collidepoint(nx, ny):
                            self.menu_idx = idx
                            self._activate_menu_choice(MENU_ITEMS[idx])
                            break
                elif self.state in ("help", "about"):
                    if self.back_rect.collidepoint(nx, ny):
                        self.synth.play("boop")
                        self.state = "menu"

            if ev.type == pygame.KEYDOWN:
                key = ev.key
                if key == pygame.K_b:
                    self.synth.play("select")
                    continue

                if self.state == "menu":
                    if key in (pygame.K_UP, pygame.K_w):
                        self.menu_idx = (self.menu_idx - 1) % len(MENU_ITEMS)
                        self.synth.play("beep")
                    elif key in (pygame.K_DOWN, pygame.K_s):
                        self.menu_idx = (self.menu_idx + 1) % len(MENU_ITEMS)
                        self.synth.play("beep")
                    elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z):
                        self._activate_menu_choice(MENU_ITEMS[self.menu_idx])
                    elif key == pygame.K_ESCAPE:
                        self.running = False

                elif self.state in ("help", "about"):
                    if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE, pygame.K_BACKSPACE):
                        self.synth.play("boop")
                        self.state = "menu"

                elif self.state == "play":
                    if key == pygame.K_ESCAPE:
                        self.synth.play("boop")
                        self.state = "menu"
                    elif key == pygame.K_p:
                        self.paused = not self.paused
                        self.synth.play("beep")
                    elif key == pygame.K_r:
                        self.synth.play("select")
                        self._init_new_game()

                elif self.state == "gameover":
                    if key in (pygame.K_RETURN, pygame.K_r, pygame.K_SPACE):
                        self.synth.play("select")
                        self._init_new_game()
                        self.state = "play"
                    elif key == pygame.K_ESCAPE:
                        self.synth.play("boop")
                        self.state = "menu"

    # =========================================================================
    # MASTER 60 FPS LOOP
    # =========================================================================
    def run(self) -> int:
        while self.running:
            self.tick_count += 1
            self.handle_events()
            if not self.running:
                break

            keys = pygame.key.get_pressed()
            if self.state == "play":
                self.update_play(keys)

            if self.state == "menu":
                self._draw_menu()
            elif self.state == "help":
                self._draw_info_modal(
                    "HELP — FAMICOM CONTROLS",
                    (
                        "LEFT / RIGHT OR A / D : MOVE CANNON",
                        "SPACE / Z / UP : FIRE LASER",
                        "P : PAUSE / RESUME  ·  R : RESTART",
                        "B : TEST 2A03 BEEP N BOOP SYNTH",
                        "ESC : RETURN TO MAIN MENU",
                        "DESTROY FLEET BEFORE LANDING!",
                    ),
                )
            elif self.state == "about":
                self._draw_info_modal(
                    "ABOUT CAT'S PY PORT",
                    (
                        "CAT'S PY PORT SPACE INVADERS",
                        "60 FPS = TRUE  ·  SPEED = NES / FAMICOM",
                        "MAIN MENU = TRUE  ·  BEEPS N BOOPS = TRUE",
                        "2C02 PPU 256x240 PIXEL ENGINE",
                        "2A03 RAM AUDIO SYNTH (FILES = OFF)",
                        "AC KONDO / FORT COMMAND (1999-2026)",
                    ),
                )
            else:
                self._draw_play()

            self.present()
            self.clock.tick(FPS)

        pygame.quit()
        return 0


def main() -> int:
    engine = CatsSpaceInvadersEngine()
    return engine.run()


if __name__ == "__main__":
    raise SystemExit(main())
