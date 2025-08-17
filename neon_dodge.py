"""
Neon Dodge — Pygame (single file)
AUTO-SHOOT • POWER-UPS • COINS • SHOP • BOSSES • KILL COUNT

How to run:
1) Install Python 3.10+ and Pygame:    pip install pygame
2) Save this file as neon_dodge.py
3) Run:                                python neon_dodge.py

Controls:
- Move: Arrow Keys or WASD
- Pause: P     Restart: R     Quit: ESC
- From Title: SPACE to start
- **Shop:** B to open/close (paused). Press 1–6 to buy upgrades.

Goal: Collect orbs, avoid enemies, auto-blast threats, earn **coins** from kills to buy **upgrades**. Bosses appear periodically.

Scoring & Currency:
- +10 per orb, +5 per normal kill, +50 per boss kill
- +1–3 coins per normal kill, +15–25 coins per boss kill

Upgrades in Shop (costs rise as you buy):
1) Damage +1  •  2) Fire Rate -10%  •  3) Move Speed +10%
4) Spread +1 (max 2)  •  5) Pierce +1 (max 3)  •  6) Shield +5s

This file is structured for easy modding:
- GameState finite-state machine (TITLE, PLAYING, GAME_OVER)
- Player / Enemy / Orb / Bullet / PowerUp classes + simple Boss flag
- Auto-shooting, power-ups, upgrades shop, coins, bosses, kill count
- Delta-time movement; difficulty ramp; screen shake; simple persistence (high score)
"""

from __future__ import annotations
import json
import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import List, Tuple, Optional

import pygame
from pygame import Surface
from pygame.math import Vector2 as V2

# ---------------------------- Config & Constants ---------------------------- #
WIDTH, HEIGHT = 900, 600
FPS = 120
TITLE = "Neon Dodge"
SAVE_PATH = Path("neon_dodge_save.json")

# Colors (RGB)
BLACK = (10, 10, 18)
WHITE = (240, 240, 255)
NEON_CYAN = (0, 255, 200)
NEON_PINK = (255, 80, 200)
NEON_YELLOW = (255, 230, 120)
NEON_GREEN = (120, 255, 170)
RED = (255, 80, 80)
GREY = (120, 130, 140)
BLUE = (120, 180, 255)
ORANGE = (255, 150, 80)

# Gameplay
PLAYER_BASE_SPEED = 320.0
# make player easier to see
PLAYER_RADIUS = 20
PLAYER_IFRAMES = 1.0
PLAYER_FRICTION = 10.0

ENEMY_BASE_SPEED = 120.0
ENEMY_RADIUS = 16
ENEMY_SPAWN_COOLDOWN = 0.4
ENEMY_MAX = 50

ORB_RADIUS = 8
ORB_SCORE = 10
KILL_SCORE = 5
BOSS_KILL_SCORE = 50

BULLET_RADIUS = 4
BULLET_SPEED = 520.0
BULLET_LIFETIME = 2.0
BULLET_BASE_DMG = 1
FIRE_COOLDOWN = 0.35
ENEMY_BULLET_SPEED = 300.0

POWERUP_RADIUS = 12
POWERUP_SPAWN_MIN = 10.0
POWERUP_SPAWN_MAX = 16.0
POWERUP_DURATION = 10.0
SHIELD_RECHARGE_RATE = 1.0  # seconds of charge regained per second

LIVES_START = 3
BAR_WIDTH = 180
BAR_HEIGHT = 16

# Difficulty settings
DIFFICULTIES = ["Easy", "Normal", "Hard"]
DIFF_SPAWN_MULT = [1.5, 1.0, 0.7]

# Coins
COINS_NORMAL_MIN, COINS_NORMAL_MAX = 1, 3
COINS_BOSS_MIN, COINS_BOSS_MAX = 15, 25

# Experience
XP_KILL = 20
XP_BOSS_KILL = 100
XP_ORB = 5

random.seed()

# sprite helper
def load_sprite(path: str, diameter: int, color: Tuple[int, int, int]) -> Surface:
    try:
        # Scale any loaded image down to the requested diameter so oversized
        # assets don't appear huge in game.  The function previously returned
        # the raw image which ignored the desired size.
        image = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(image, (diameter, diameter))
    except Exception:
        # If the image can't be loaded, fall back to a simple colored circle
        surf = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        pygame.draw.circle(surf, color, (diameter // 2, diameter // 2), diameter // 2)
        return surf

# ---------------------------- Utility Helpers ------------------------------ #

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def circle_collision(a_pos: V2, a_r: float, b_pos: V2, b_r: float) -> bool:
    return a_pos.distance_squared_to(b_pos) <= (a_r + b_r) ** 2


# ------------------------------ Entities ----------------------------------- #
@dataclass
class Player:
    pos: V2
    vel: V2 = field(default_factory=lambda: V2(0, 0))
    radius: int = PLAYER_RADIUS
    base_speed: float = PLAYER_BASE_SPEED
    speed_mult: float = 1.0
    iframes: float = 0.0
    fire_timer: float = 0.0

    # combat stats
    fire_cooldown: float = FIRE_COOLDOWN
    spread_level: int = 0       # 0 = single, 1 = +2 side bullets, 2 = +4
    pierce: int = 0             # bullets pass through N enemies
    damage: int = BULLET_BASE_DMG
    shield_time: float = 0.0  # current shield charge (0-POWERUP_DURATION)
    has_shield: bool = False
    level: int = 1
    xp: int = 0

    def speed(self) -> float:
        return self.base_speed * self.speed_mult

    def update(self, dt: float, keys: pygame.key.ScancodeWrapper) -> None:
        dir_x = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        dir_y = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])
        move = V2(float(dir_x), float(dir_y))
        if move.length_squared() > 0:
            move = move.normalize() * self.speed()
        self.vel += (move - self.vel) * clamp(PLAYER_FRICTION * dt, 0.0, 1.0)
        self.pos += self.vel * dt
        self.pos.x = clamp(self.pos.x, self.radius, WIDTH - self.radius)
        self.pos.y = clamp(self.pos.y, self.radius, HEIGHT - self.radius)

        if self.iframes > 0:
            self.iframes = max(0.0, self.iframes - dt)
        if self.has_shield and self.shield_time < POWERUP_DURATION:
            self.shield_time = min(POWERUP_DURATION, self.shield_time + SHIELD_RECHARGE_RATE * dt)
        self.fire_timer = max(0.0, self.fire_timer - dt)

    def xp_to_next(self) -> int:
        return 100 * self.level

    def gain_xp(self, amount: int) -> None:
        self.xp += amount
        while self.xp >= self.xp_to_next():
            self.xp -= self.xp_to_next()
            self.level += 1

    def draw(self, surf: Surface, t: float, img: Surface) -> None:
        rect = img.get_rect(center=self.pos)
        surf.blit(img, rect)
        color = NEON_CYAN if int(t * 30) % 2 == 0 or self.iframes <= 0 else NEON_YELLOW
        pygame.draw.circle(surf, color, self.pos, self.radius, width=2)
        if self.shield_time >= POWERUP_DURATION:
            r = self.radius + 6 + 2 * math.sin(t * 8)
            pygame.draw.circle(surf, BLUE, self.pos, int(r), width=2)


class EnemyType(Enum):
    NORMAL = auto()
    ZIGZAG = auto()
    HOMING = auto()
    BOSS = auto()
    MEGA_BOSS = auto()


@dataclass
class Enemy:
    pos: V2
    vel: V2
    speed: float
    type: EnemyType = EnemyType.NORMAL
    radius: int = ENEMY_RADIUS
    hp: int = 1
    is_boss: bool = False
    tier: int = 0
    dash_cd: float = 0.0
    shoot_cd: float = 0.0
    boss_kind: int = 0
    zigzag_phase: float = 0.0

    def update(self, dt: float, player_pos: V2) -> None:
        to_player = (player_pos - self.pos)
        desired = to_player.normalize() * self.speed if to_player.length_squared() > 1e-4 else V2(0, 0)
        jitter = V2(random.uniform(-1, 1), random.uniform(-1, 1)) * (self.speed * (0.15 if self.is_boss else 0.25))
        steer = desired + jitter
        self.vel += (steer - self.vel) * clamp((2.0 if self.is_boss else 4.0) * dt, 0.0, 1.0)
        self.pos += self.vel * dt
        if (self.pos.x < self.radius and self.vel.x < 0) or (self.pos.x > WIDTH - self.radius and self.vel.x > 0):
            self.vel.x *= -1
        if (self.pos.y < self.radius and self.vel.y < 0) or (self.pos.y > HEIGHT - self.radius and self.vel.y > 0):
            self.vel.y *= -1
        self.pos.x = clamp(self.pos.x, self.radius, WIDTH - self.radius)
        self.pos.y = clamp(self.pos.y, self.radius, HEIGHT - self.radius)
        if self.tier >= 1:
            self.dash_cd -= dt
            if self.dash_cd <= 0:
                if to_player.length_squared() > 0:
                    self.vel += to_player.normalize() * self.speed * (1.5 + 0.5 * self.tier)
                self.dash_cd = random.uniform(1.5, 3.0)

    def draw(self, surf: Surface, sprites: dict) -> None:
        img = sprites.get(self.type)
        if img is not None:
            rect = img.get_rect(center=self.pos)
            surf.blit(img, rect)
        else:
            pygame.draw.circle(surf, NEON_PINK, self.pos, self.radius)
        if self.is_boss:
            pygame.draw.circle(surf, WHITE, self.pos, self.radius + 6, width=2)


@dataclass
class Orb:
    pos: V2
    radius: int = ORB_RADIUS
    def draw(self, surf: Surface) -> None:
        pygame.draw.circle(surf, NEON_YELLOW, self.pos, self.radius)
        pygame.draw.circle(surf, WHITE, self.pos, max(1, self.radius // 3))



@dataclass
class Bullet:
    pos: V2
    vel: V2
    radius: int = BULLET_RADIUS
    lifetime: float = BULLET_LIFETIME
    pierce: int = 0
    dmg: int = BULLET_BASE_DMG
    from_enemy: bool = False
    homing: bool = False

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt
        self.lifetime -= dt
    def alive(self) -> bool:
        if self.lifetime <= 0:
            return False
        return -20 <= self.pos.x <= WIDTH + 20 and -20 <= self.pos.y <= HEIGHT + 20
    def draw(
        self,
        surf: Surface,
        player_img: Optional[Surface] = None,
        enemy_img: Optional[Surface] = None,
    ) -> None:
        if self.from_enemy:
            if enemy_img is not None:
                surf.blit(enemy_img, enemy_img.get_rect(center=self.pos))
            else:
                pygame.draw.circle(surf, RED, self.pos, self.radius)
        else:
            if player_img is not None:
                surf.blit(player_img, player_img.get_rect(center=self.pos))
            else:
                pygame.draw.circle(surf, NEON_GREEN, self.pos, self.radius)


@dataclass
class Particle:
    pos: V2
    vel: V2
    color: Tuple[int, int, int]
    radius: float
    life: float
    full_life: float

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt
        self.life -= dt

    def alive(self) -> bool:
        return self.life > 0

    def draw(self, surf: Surface) -> None:
        if self.life <= 0:
            return
        r = int(self.radius * (self.life / self.full_life))
        if r > 0:
            pygame.draw.circle(surf, self.color, self.pos, r)


class PUType(Enum):
    RAPID = auto()
    SPREAD = auto()
    SHIELD = auto()
    SPEED = auto()
    PIERCE = auto()


@dataclass
class PowerUp:
    pos: V2
    kind: PUType
    radius: int = POWERUP_RADIUS
    def draw(self, surf: Surface) -> None:
        color = {
            PUType.RAPID: NEON_YELLOW,
            PUType.SPREAD: NEON_PINK,
            PUType.SHIELD: BLUE,
            PUType.SPEED: NEON_CYAN,
            PUType.PIERCE: NEON_GREEN,
        }[self.kind]
        pygame.draw.circle(surf, color, self.pos, self.radius)
        glyph = {PUType.RAPID:"R", PUType.SPREAD:"S", PUType.SHIELD:"H", PUType.SPEED:"V", PUType.PIERCE:"P"}[self.kind]
        font = pygame.font.SysFont("consolas", 16)
        img = font.render(glyph, True, BLACK)
        surf.blit(img, img.get_rect(center=self.pos))


# ------------------------------ Starfield ----------------------------------- #
class Starfield:
    def __init__(self, n: int = 120):
        self.stars: List[Tuple[float, float, float]] = []
        for _ in range(n):
            self.stars.append([random.uniform(0, WIDTH), random.uniform(0, HEIGHT), random.uniform(10, 80)])
    def update(self, dt: float, camera_vel: V2) -> None:
        for s in self.stars:
            s[1] += (s[2] + camera_vel.y * 0.2) * dt
            s[0] += (camera_vel.x * 0.2) * dt
            if s[1] > HEIGHT:
                s[0] = random.uniform(0, WIDTH)
                s[1] = -2
    def draw(self, surf: Surface) -> None:
        for x, y, speed in self.stars:
            b = clamp(int(120 + speed * 1.3), 120, 255)
            surf.fill((b, b, b), rect=pygame.Rect(int(x), int(y), 2, 2))


# ------------------------------ Game State ---------------------------------- #
class GameState:
    TITLE = 0
    PLAYING = 1
    GAME_OVER = 2
    SETTINGS = 3


class Game:
    def __init__(self):
        pygame.init()
        # Initialize mixer for sound effects and music
        import pygame.mixer
        pygame.mixer.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        global WIDTH, HEIGHT
        WIDTH, HEIGHT = self.screen.get_size()
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.SysFont("consolas", 48)
        self.font = pygame.font.SysFont("consolas", 24)
        self.font_small = pygame.font.SysFont("consolas", 18)
        self.running = True
        self.state = GameState.TITLE
        self.t = 0.0

        self.starfield = Starfield()

        # Sprites
        self.player_img = load_sprite("player.png", PLAYER_RADIUS * 2, NEON_CYAN)
        self.enemy_sprites = {
            EnemyType.NORMAL: load_sprite("es1.png", ENEMY_RADIUS * 2, NEON_PINK),
            EnemyType.ZIGZAG: load_sprite("es2.png", ENEMY_RADIUS * 2, NEON_YELLOW),
            EnemyType.HOMING: load_sprite("es3.png", ENEMY_RADIUS * 2, NEON_GREEN),
            EnemyType.BOSS: load_sprite("bs1.png", 68, ORANGE),
            EnemyType.MEGA_BOSS: load_sprite("bigboss.png", 96, RED),
        }
        self.bullet_img = load_sprite("bullet.png", BULLET_RADIUS * 2, NEON_GREEN)

        self.high_score = 0
        self._load_save()
        pygame.mixer.music.set_volume(self.music_volume)


        # Gameplay
        self.player = Player(V2(WIDTH / 2, HEIGHT / 2))
        self.enemies: List[Enemy] = []
        self.orb = self._spawn_orb()
        self.score = 0
        self.lives = LIVES_START
        self.spawn_timer = 0.0
        self.diff_timer = 0.0
        self.enemy_speed = ENEMY_BASE_SPEED
        self.max_enemies = 3
        self.enemy_level = 0
        self.shake = 0.0

        # Combat
        self.bullets: List[Bullet] = []
        self.particles: List[Particle] = []

        # Power-ups
        self.powerups: List[PowerUp] = []
        self.pu_spawn_timer = random.uniform(POWERUP_SPAWN_MIN, POWERUP_SPAWN_MAX)
        self.rapid_time = 0.0
        self.speed_time = 0.0
        self.spread_time = 0.0
        self.pierce_time = 0.0

        # Currency & progression
        self.coins = 0
        self.kills = 0
        self.shop_open = False
        self.upgrades = [
            {"name": "Damage +1", "cost": 25, "key": pygame.K_1, "fn": self._buy_damage},
            {"name": "Fire Rate -10%", "cost": 30, "key": pygame.K_2, "fn": self._buy_firerate},
            {"name": "Move Speed +10%", "cost": 30, "key": pygame.K_3, "fn": self._buy_movespeed},
            {"name": "Spread +1 (max 2)", "cost": 40, "key": pygame.K_4, "fn": self._buy_spread},
            {"name": "Pierce +1 (max 3)", "cost": 45, "key": pygame.K_5, "fn": self._buy_pierce},
            {"name": "Shield (recharge)", "cost": 25, "key": pygame.K_6, "fn": self._buy_shield},
        ]

        # Boss logic
        self.boss_timer = 20.0  # seconds to next boss

    # ---------------------- Persistence ---------------------- #

    def _load_save(self) -> None:
        if SAVE_PATH.exists():
            try:
                data = json.loads(SAVE_PATH.read_text())
                self.high_score = int(data.get("high_score", 0))
                self.music_volume = float(data.get("music_volume", 1.0))
                self.sfx_volume = float(data.get("sfx_volume", 1.0))
                self.difficulty_idx = int(data.get("difficulty", 1))
            except Exception:
                self.high_score = 0
                self.music_volume = 1.0
                self.sfx_volume = 1.0
                self.difficulty_idx = 1
        else:
            self.high_score = 0
            self.music_volume = 1.0
            self.sfx_volume = 1.0
            self.difficulty_idx = 1

    def _save(self) -> None:
        try:
            SAVE_PATH.write_text(
                json.dumps(
                    {
                        "high_score": self.high_score,
                        "music_volume": self.music_volume,
                        "sfx_volume": self.sfx_volume,
                        "difficulty": self.difficulty_idx,
                    }
                )
            )
        except Exception:
            pass


    # ---------------------- Spawning ------------------------- #
    def _spawn_enemy(self) -> Enemy:
        side = random.choice(["left", "right", "top", "bottom"])
        if side == "left":
            pos = V2(-ENEMY_RADIUS, random.uniform(ENEMY_RADIUS, HEIGHT - ENEMY_RADIUS))
            vel = V2(1, 0)
        elif side == "right":
            pos = V2(WIDTH + ENEMY_RADIUS, random.uniform(ENEMY_RADIUS, HEIGHT - ENEMY_RADIUS))
            vel = V2(-1, 0)
        elif side == "top":
            pos = V2(random.uniform(ENEMY_RADIUS, WIDTH - ENEMY_RADIUS), -ENEMY_RADIUS)
            vel = V2(0, 1)
        else:
            pos = V2(random.uniform(ENEMY_RADIUS, WIDTH - ENEMY_RADIUS), HEIGHT + ENEMY_RADIUS)
            vel = V2(0, -1)
        speed = self.enemy_speed * random.uniform(0.9, 1.2)
        tier = random.randint(0, self.enemy_level)
        speed *= 1.0 + 0.15 * tier
        hp = 1 + tier
        dash = random.uniform(1.5, 3.0) if tier >= 1 else 0.0

        etype = random.choice([EnemyType.NORMAL, EnemyType.ZIGZAG, EnemyType.HOMING])
        shoot = 0.0
        zig = 0.0
        if etype == EnemyType.ZIGZAG:
            speed *= 1.1
            zig = random.uniform(0, math.tau)
        elif etype == EnemyType.HOMING:
            shoot = random.uniform(2.5, 4.0)
            speed *= 0.9
        elif tier >= 2:
            shoot = random.uniform(2.0, 3.5)

        return Enemy(
            pos=pos,
            vel=vel * speed,
            speed=speed,
            hp=hp,
            tier=tier,
            dash_cd=dash,
            shoot_cd=shoot,
            type=etype,
            zigzag_phase=zig,
        )

    def _spawn_boss(self) -> Enemy:
        pos = V2(random.uniform(120, WIDTH - 120), -40)
        boss_kind = random.choice([0, 1, 2])
        if boss_kind == 2:
            speed = max(80.0, self.enemy_speed * 0.8)
            hp = 60 + int(self.t // 20) * 10
            tier = 3
            dash = 0.0
            shoot = random.uniform(1.5, 2.5)
            radius = 56
            etype = EnemyType.MEGA_BOSS
        else:
            speed = max(90.0, self.enemy_speed * 0.9)
            hp = 24 + int(self.t // 20) * 6
            tier = 2 if boss_kind == 1 else 1
            dash = random.uniform(1.5, 3.0)
            shoot = random.uniform(1.0, 2.0) if boss_kind == 1 else 0.0
            radius = 34
            etype = EnemyType.BOSS

        return Enemy(
            pos=pos,
            vel=V2(0, speed),
            speed=speed,
            radius=radius,
            hp=hp,
            is_boss=True,
            tier=tier,
            dash_cd=dash,
            shoot_cd=shoot,
            boss_kind=boss_kind,
            type=etype,
        )

    def _spawn_orb(self) -> Orb:
        return Orb(V2(random.uniform(40, WIDTH - 40), random.uniform(40, HEIGHT - 40)))

    def _spawn_powerup(self) -> None:
        kind = random.choice(list(PUType))
        pos = V2(random.uniform(60, WIDTH - 60), random.uniform(60, HEIGHT - 60))
        self.powerups.append(PowerUp(pos, kind))

    def _spawn_explosion(self, pos: V2) -> None:
        colors = [
            (255, 0, 0),
            (255, 127, 0),
            (255, 255, 0),
            (0, 255, 0),
            (0, 0, 255),
            (75, 0, 130),
            (148, 0, 211),
        ]
        for _ in range(20):
            direction = V2(random.uniform(-1, 1), random.uniform(-1, 1))
            if direction.length_squared() == 0:
                direction = V2(1, 0)
            vel = direction.normalize() * random.uniform(80, 200)
            life = random.uniform(0.4, 0.8)
            radius = random.uniform(4, 8)
            color = random.choice(colors)
            self.particles.append(Particle(pos.copy(), vel, color, radius, life, life))

    # ---------------------- Reset / Start -------------------- #
    def reset(self) -> None:
        self.player = Player(V2(WIDTH / 2, HEIGHT / 2))
        self.enemies.clear()
        self.orb = self._spawn_orb()
        self.score = 0
        self.lives = LIVES_START
        self.spawn_timer = 0.0
        self.diff_timer = 0.0
        self.enemy_speed = ENEMY_BASE_SPEED
        self.max_enemies = 3
        self.enemy_level = 0
        self.shake = 0.0
        self.bullets.clear()
        self.powerups.clear()
        self.pu_spawn_timer = random.uniform(POWERUP_SPAWN_MIN, POWERUP_SPAWN_MAX)
        self.rapid_time = self.speed_time = self.spread_time = self.pierce_time = 0.0
        self.coins = 0
        self.kills = 0
        self.shop_open = False
        self.boss_timer = 20.0

    # ---------------------- Update Loop ---------------------- #
    def update_title(self, dt: float) -> None:
        self.starfield.update(dt, V2(0, 35))

    def update_settings(self, dt: float, events: List[pygame.event.Event]) -> None:
        self.starfield.update(dt, V2(0, 25))
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_UP:
                self.settings_index = (self.settings_index - 1) % 3
            elif e.key == pygame.K_DOWN:
                self.settings_index = (self.settings_index + 1) % 3
            elif e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                if self.settings_index == 0:
                    delta = 0.1 if e.key == pygame.K_RIGHT else -0.1
                    self.music_volume = clamp(self.music_volume + delta, 0.0, 1.0)
                    pygame.mixer.music.set_volume(self.music_volume)
                    self._save()
                elif self.settings_index == 1:
                    delta = 0.1 if e.key == pygame.K_RIGHT else -0.1
                    self.sfx_volume = clamp(self.sfx_volume + delta, 0.0, 1.0)
                    self._save()
                elif self.settings_index == 2:
                    if e.key == pygame.K_RIGHT:
                        self.difficulty_idx = (self.difficulty_idx + 1) % len(DIFFICULTIES)
                    else:
                        self.difficulty_idx = (self.difficulty_idx - 1) % len(DIFFICULTIES)
                    self._save()

    def _nearest_enemy_dir(self) -> Optional[V2]:
        if not self.enemies:
            return None
        p = self.player.pos
        nearest = min(self.enemies, key=lambda e: e.pos.distance_squared_to(p))
        to = nearest.pos - p
        return to.normalize() if to.length_squared() else V2(1, 0)

    def _try_fire(self) -> None:
        if self.player.fire_timer > 0:
            return
        aim = self._nearest_enemy_dir()
        if aim is None:
            return
        cooldown = self.player.fire_cooldown * (0.45 if self.rapid_time > 0 else 1.0)
        self.player.fire_timer = max(0.08, cooldown)
        dirs = [aim]
        if self.spread_time > 0 or self.player.spread_level > 0:
            level = max(self.player.spread_level, 1)
            angles = [10, -10] if level == 1 else [8, -8, 16, -16]
            for ang in angles:
                rad = math.radians(ang)
                rot = V2(aim.x * math.cos(rad) - aim.y * math.sin(rad), aim.x * math.sin(rad) + aim.y * math.cos(rad))
                dirs.append(rot.normalize())
        for d in dirs:
            vel = d * BULLET_SPEED
            self.bullets.append(Bullet(self.player.pos + d * (self.player.radius + 6), vel, pierce=(1 if self.pierce_time > 0 else self.player.pierce), dmg=self.player.damage))
            if self.snd_shoot:
                self.snd_shoot.play()
        self.shake = min(6.0, self.shake + 1.5)

    def _has_boss(self) -> bool:
        return any(e.is_boss for e in self.enemies)

    def update_play(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        # Toggle shop (handled in event too, but keep here if holding)
        if keys[pygame.K_b]:
            pass
        # Pause gameplay when shop is open
        if self.shop_open:
            self.player.update(dt, keys)  # allow moving cursor feel; but no enemies
            self.starfield.update(dt, self.player.vel)
            return

        self.player.update(dt, keys)
        self.starfield.update(dt, self.player.vel)

        self.enemy_level = min(2, int(self.t // 30))

        # Auto-fire
        self._try_fire()

        # Bullets
        for b in self.bullets:
            if b.from_enemy and b.homing:
                to = self.player.pos - b.pos
                if to.length_squared() > 0:
                    desired = to.normalize() * ENEMY_BULLET_SPEED
                    b.vel += (desired - b.vel) * clamp(4.0 * dt, 0.0, 1.0)
            b.update(dt)
        new_bullets: List[Bullet] = []
        for b in self.bullets:
            if not b.alive():
                continue
            if b.from_enemy:
                if self.player.iframes <= 0 and circle_collision(b.pos, b.radius, self.player.pos, self.player.radius):
                    if self.player.shield_time >= POWERUP_DURATION:
                        self.player.shield_time = 0.0
                        self.player.iframes = 0.2
                        self.shake = 8.0
                    else:
                        self.lives -= 1
                        self.player.iframes = PLAYER_IFRAMES
                        self.shake = 12.0
                        if self.lives <= 0:
                            self.state = GameState.GAME_OVER
                else:
                    new_bullets.append(b)
                continue
            hit_any = False
            for e in list(self.enemies):
                if circle_collision(b.pos, b.radius, e.pos, e.radius):
                    e.hp -= b.dmg
                    hit_any = True
                    if e.hp <= 0:
                        self.enemies.remove(e)
                        self.kills += 1
                        self._spawn_explosion(e.pos)
                        if e.is_boss:
                            self.score += BOSS_KILL_SCORE
                            self.coins += random.randint(COINS_BOSS_MIN, COINS_BOSS_MAX)
                            self.player.gain_xp(XP_BOSS_KILL)
                            self.boss_timer = max(12.0, 28.0 - (self.t * 0.05))
                        else:
                            self.score += KILL_SCORE
                            self.coins += random.randint(COINS_NORMAL_MIN, COINS_NORMAL_MAX)
                            self.player.gain_xp(XP_KILL)
                        self.shake = min(10.0, self.shake + (4.0 if e.is_boss else 2.5))
                    if b.pierce > 0:
                        b.pierce -= 1
                        hit_any = False
                    else:
                        break
            if not hit_any:
                new_bullets.append(b)
        self.bullets = new_bullets

        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.alive()]

        # Enemies
        for e in self.enemies:
            e.update(dt, self.player.pos)
            if e.type == EnemyType.ZIGZAG:
                e.zigzag_phase += dt * 4.0
                perp = V2(-e.vel.y, e.vel.x)
                if perp.length_squared() > 0:
                    perp = perp.normalize()
                    e.pos += perp * math.sin(e.zigzag_phase) * e.speed * 0.5 * dt
            elif e.type == EnemyType.HOMING:
                e.shoot_cd -= dt
                if e.shoot_cd <= 0:
                    to = self.player.pos - e.pos
                    dir = to.normalize() if to.length_squared() > 0 else V2(0, 1)
                    self.bullets.append(
                        Bullet(
                            e.pos + dir * (e.radius + 4),
                            dir * ENEMY_BULLET_SPEED * 0.8,
                            dmg=1,
                            from_enemy=True,
                            homing=True,
                        )
                    )
                    e.shoot_cd = random.uniform(2.0, 3.0)
            elif e.type == EnemyType.MEGA_BOSS:
                e.shoot_cd -= dt
                if e.shoot_cd <= 0:
                    for i in range(8):
                        ang = i * (math.tau / 8)
                        vel = V2(math.cos(ang), math.sin(ang)) * ENEMY_BULLET_SPEED * 0.6
                        self.bullets.append(Bullet(e.pos, vel, dmg=2, from_enemy=True))
                    to = self.player.pos - e.pos
                    dir = to.normalize() if to.length_squared() > 0 else V2(0, 1)
                    self.bullets.append(Bullet(e.pos, dir * ENEMY_BULLET_SPEED * 0.8, dmg=2, from_enemy=True, homing=True))
                    e.shoot_cd = random.uniform(1.5, 2.5)
            else:
                if (e.tier >= 2) or (e.is_boss and e.boss_kind == 1):
                    e.shoot_cd -= dt
                    if e.shoot_cd <= 0:
                        to = self.player.pos - e.pos
                        dir = to.normalize() if to.length_squared() > 0 else V2(0, 1)
                        dmg = 2 if e.is_boss else 1
                        self.bullets.append(Bullet(e.pos + dir * (e.radius + 4), dir * ENEMY_BULLET_SPEED, dmg=dmg, from_enemy=True))
                        e.shoot_cd = random.uniform(1.0, 2.0) if e.is_boss else random.uniform(1.5, 3.0)

        # Spawn logic
        self.spawn_timer -= dt
        if not self._has_boss():
            if self.spawn_timer <= 0 and len(self.enemies) < self.max_enemies:
                self.enemies.append(self._spawn_enemy())
                self.spawn_timer = (
                    ENEMY_SPAWN_COOLDOWN
                    * DIFF_SPAWN_MULT[self.difficulty_idx]
                    * random.uniform(0.6, 1.2)
                )
        # Boss timer
        self.boss_timer -= dt
        if self.boss_timer <= 0 and not self._has_boss():
            self.enemies.append(self._spawn_boss())
            self.boss_timer = 999.0  # wait for kill before next schedule

        # Difficulty ramp
        self.diff_timer += dt
        if self.diff_timer >= 2.0:
            self.diff_timer = 0.0
            self.enemy_speed = min(self.enemy_speed + 6.0, 260.0)
            self.max_enemies = min(self.max_enemies + 1, ENEMY_MAX)

        # Collisions: orb
        if circle_collision(self.player.pos, self.player.radius, self.orb.pos, self.orb.radius):
            self.score += ORB_SCORE
            self.player.gain_xp(XP_ORB)
            self.orb = self._spawn_orb()
            self.shake = min(8.0, self.shake + 4.0)

        # Passive score tick
        self.score += int(20 * dt)

        # Enemy collision with player
        if self.player.iframes <= 0:
            for e in self.enemies:
                if circle_collision(self.player.pos, self.player.radius, e.pos, e.radius):
                    if self.player.shield_time >= POWERUP_DURATION:
                        self.player.shield_time = 0.0
                        self.player.iframes = 0.2
                        self.shake = 8.0
                    else:
                        self.lives -= 1
                        self.player.iframes = PLAYER_IFRAMES
                        self.shake = 12.0
                        if self.lives <= 0:
                            self.state = GameState.GAME_OVER
                    break

        # Power-up spawning and pickups
        self.pu_spawn_timer -= dt
        if self.pu_spawn_timer <= 0:
            self._spawn_powerup()
            self.pu_spawn_timer = random.uniform(POWERUP_SPAWN_MIN, POWERUP_SPAWN_MAX)
        for pu in list(self.powerups):
            if circle_collision(self.player.pos, self.player.radius, pu.pos, POWERUP_RADIUS):
                self.apply_powerup(pu.kind)
                self.powerups.remove(pu)
                self.shake = min(8.0, self.shake + 3.0)

        # Tick effect timers & apply
        self.rapid_time = max(0.0, self.rapid_time - dt)
        self.speed_time = max(0.0, self.speed_time - dt)
        self.spread_time = max(0.0, self.spread_time - dt)
        self.pierce_time = max(0.0, self.pierce_time - dt)
        self.player.speed_mult = 1.3 if self.speed_time > 0 else 1.0

        # Screen shake decay
        if self.shake > 0:
            self.shake = max(0.0, self.shake - 20.0 * dt)

    def apply_powerup(self, kind: PUType) -> None:
        if kind == PUType.RAPID:
            self.rapid_time = POWERUP_DURATION
        elif kind == PUType.SPREAD:
            self.spread_time = POWERUP_DURATION
        elif kind == PUType.SHIELD:
            self.player.has_shield = True
            self.player.shield_time = POWERUP_DURATION
        elif kind == PUType.SPEED:
            self.speed_time = POWERUP_DURATION
        elif kind == PUType.PIERCE:
            self.pierce_time = POWERUP_DURATION

    # ---------------------- Shop Logic ----------------------- #
    def _inflate_cost(self, cost: int) -> int:
        return int(cost * 1.4) + 1

    def _buy_if_can(self, idx: int) -> None:
        if 0 <= idx < len(self.upgrades):
            up = self.upgrades[idx]
            if self.coins >= up["cost"]:
                self.coins -= up["cost"]
                up["fn"]()
                up["cost"] = min(999, self._inflate_cost(up["cost"]))

    def _buy_damage(self) -> None:
        self.player.damage += 1

    def _buy_firerate(self) -> None:
        self.player.fire_cooldown = max(0.08, self.player.fire_cooldown * 0.9)

    def _buy_movespeed(self) -> None:
        self.player.base_speed *= 1.1

    def _buy_spread(self) -> None:
        if self.player.spread_level < 2:
            self.player.spread_level += 1

    def _buy_pierce(self) -> None:
        if self.player.pierce < 3:
            self.player.pierce += 1

    def _buy_shield(self) -> None:
        self.player.has_shield = True
        self.player.shield_time = POWERUP_DURATION

    def update_game_over(self, dt: float) -> None:
        self.starfield.update(dt, V2(0, 10))
        if self.score > self.high_score:
            self.high_score = self.score
            self._save()

    # ---------------------- Draw Loop ------------------------ #
    def draw_title(self) -> None:
        self.screen.fill(BLACK)
        self.starfield.draw(self.screen)
        title = self.font_big.render(TITLE, True, NEON_PINK)
        sub = self.font.render("SPACE to start — WASD/Arrows to move", True, GREY)
        hint = self.font_small.render("Auto-shoot, collect coins, B for shop, P to pause.", True, GREY)
        set_hint = self.font_small.render("S for Settings", True, GREY)
        self.screen.blit(title, title.get_rect(center=(WIDTH / 2, HEIGHT / 2 - 40)))
        self.screen.blit(sub, sub.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 10)))
        self.screen.blit(hint, hint.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 40)))
        self.screen.blit(set_hint, set_hint.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 70)))

    def draw_settings(self) -> None:
        self.screen.fill(BLACK)
        self.starfield.draw(self.screen)
        title = self.font_big.render("SETTINGS", True, NEON_PINK)
        self.screen.blit(title, title.get_rect(center=(WIDTH / 2, 80)))
        options = [
            f"Music Volume: {int(self.music_volume * 100)}%",
            f"SFX Volume: {int(self.sfx_volume * 100)}%",
            f"Difficulty: {DIFFICULTIES[self.difficulty_idx]}",
        ]
        y = 160
        for i, text in enumerate(options):
            color = NEON_YELLOW if i == self.settings_index else GREY
            surf = self.font.render(text, True, color)
            self.screen.blit(surf, surf.get_rect(center=(WIDTH / 2, y)))
            y += 40
        hint = self.font_small.render("Arrows to change, ESC to exit", True, GREY)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH / 2, HEIGHT - 60)))

    def draw_hud(self) -> None:
        score_s = self.font.render(f"Score: {self.score}", True, WHITE)
        hi_s = self.font.render(f"High: {self.high_score}", True, GREY)
        coins_s = self.font.render(f"Coins: {self.coins}", True, NEON_YELLOW)
        kills_s = self.font.render(f"Kills: {self.kills}", True, NEON_GREEN)
        level_s = self.font.render(f"Level: {self.player.level}", True, NEON_CYAN)
        xp_s = self.font_small.render(
            f"XP: {self.player.xp}/{self.player.xp_to_next()}", True, NEON_CYAN
        )
        self.screen.blit(score_s, (14, 10))
        self.screen.blit(hi_s, (14, 38))
        self.screen.blit(coins_s, (14, 66))
        self.screen.blit(kills_s, (14, 94))
        self.screen.blit(level_s, (14, 122))
        self.screen.blit(xp_s, (14, 150))

        # Health bar (top-right)
        hp_label = self.font_small.render("HP", True, WHITE)
        hp_label_x = WIDTH - hp_label.get_width() - 14
        hp_label_y = 10
        self.screen.blit(hp_label, (hp_label_x, hp_label_y))
        bar_x = WIDTH - BAR_WIDTH - 14
        bar_y = hp_label_y + hp_label.get_height() + 4
        ratio = self.lives / LIVES_START
        pygame.draw.rect(self.screen, NEON_GREEN, (bar_x, bar_y, int(BAR_WIDTH * ratio), BAR_HEIGHT))
        pygame.draw.rect(self.screen, WHITE, (bar_x, bar_y, BAR_WIDTH, BAR_HEIGHT), 2)

        # Shield bar below health
        shield_label = self.font_small.render("Shield", True, WHITE)
        shield_label_x = WIDTH - shield_label.get_width() - 14
        shield_label_y = bar_y + BAR_HEIGHT + 8
        self.screen.blit(shield_label, (shield_label_x, shield_label_y))
        sy = shield_label_y + shield_label.get_height() + 4
        shield_ratio = clamp(self.player.shield_time / POWERUP_DURATION, 0.0, 1.0)
        pygame.draw.rect(self.screen, BLUE, (bar_x, sy, int(BAR_WIDTH * shield_ratio), BAR_HEIGHT))
        pygame.draw.rect(self.screen, WHITE, (bar_x, sy, BAR_WIDTH, BAR_HEIGHT), 2)

        # Power-up badges
        badges = []
        if self.rapid_time > 0: badges.append(("Rapid", self.rapid_time))
        if self.spread_time > 0: badges.append(("Spread", self.spread_time))
        if self.pierce_time > 0: badges.append(("Pierce", self.pierce_time))
        if self.speed_time > 0: badges.append(("Speed", self.speed_time))
        x0, y0 = 12, HEIGHT - 28
        for i, (name, tleft) in enumerate(badges[:6]):
            label = self.font_small.render(f"{name}:{int(tleft)}s", True, WHITE)
            self.screen.blit(label, (x0 + i * 130, y0))

        prompt = self.font_small.render("Press B for Shop", True, GREY)
        self.screen.blit(prompt, (WIDTH - prompt.get_width() - 14, HEIGHT - 28))

    def draw_shop(self) -> None:
        panel = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 200))
        self.screen.blit(panel, (0, 0))
        title = self.font_big.render("SHOP", True, NEON_YELLOW)
        self.screen.blit(title, title.get_rect(center=(WIDTH / 2, 80)))
        info = self.font_small.render("Press 1–6 to buy, B to close", True, GREY)
        self.screen.blit(info, info.get_rect(center=(WIDTH / 2, 120)))
        # List upgrades
        y = 170
        for i, up in enumerate(self.upgrades, start=1):
            name = up["name"]
            cost = up["cost"]
            line = self.font.render(f"{i}. {name}  —  {cost} coins", True, WHITE)
            self.screen.blit(line, (WIDTH / 2 - 260, y))
            y += 36
        wallet = self.font.render(f"Coins: {self.coins}", True, NEON_YELLOW)
        self.screen.blit(wallet, (WIDTH / 2 - 260, y + 10))

    def draw_play(self) -> None:
        self.screen.fill(BLACK)
        self.starfield.draw(self.screen)
        ox = random.uniform(-self.shake, self.shake)
        oy = random.uniform(-self.shake, self.shake)
        temp = self.screen.copy()
        self.orb.draw(temp)
        for pu in self.powerups:
            pu.draw(temp)
        for e in self.enemies:
            e.draw(temp, self.enemy_sprites)
        for p in self.particles:
            p.draw(temp)
        for b in self.bullets:
            b.draw(temp, self.bullet_img)
        self.player.draw(temp, self.t, self.player_img)
        self.screen.blit(temp, (ox, oy))
        self.draw_hud()
        if self.shop_open:
            self.draw_shop()

    def draw_game_over(self) -> None:
        self.draw_play()
        panel = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 160))
        self.screen.blit(panel, (0, 0))
        over = self.font_big.render("GAME OVER", True, NEON_PINK)
        s1 = self.font.render(f"Score: {self.score}", True, WHITE)
        s2 = self.font.render(f"High:  {self.high_score}", True, GREY)
        s3 = self.font_small.render("Press R to restart, ESC to quit", True, GREY)
        self.screen.blit(over, over.get_rect(center=(WIDTH / 2, HEIGHT / 2 - 40)))
        self.screen.blit(s1, s1.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 5)))
        self.screen.blit(s2, s2.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 35)))
        self.screen.blit(s3, s3.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 70)))

    # ---------------------- Main Loop ------------------------ #
    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.t += dt

            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.state == GameState.SETTINGS:
                            self.state = GameState.TITLE
                            self._save()
                        else:
                            self.running = False
                    if self.state == GameState.TITLE:
                        if event.key == pygame.K_SPACE:
                            self.reset()
                            self.state = GameState.PLAYING
                        elif event.key == pygame.K_s:
                            self.state = GameState.SETTINGS
                    elif self.state == GameState.PLAYING:
                        if event.key == pygame.K_p:
                            self.state = GameState.TITLE
                        if event.key == pygame.K_b:
                            self.shop_open = not self.shop_open
                        if self.shop_open:
                            if event.key in (
                                pygame.K_1,
                                pygame.K_2,
                                pygame.K_3,
                                pygame.K_4,
                                pygame.K_5,
                                pygame.K_6,
                            ):
                                idx = {
                                    pygame.K_1: 0,
                                    pygame.K_2: 1,
                                    pygame.K_3: 2,
                                    pygame.K_4: 3,
                                    pygame.K_5: 4,
                                    pygame.K_6: 5,
                                }[event.key]
                                self._buy_if_can(idx)
                        if event.key == pygame.K_r:
                            self.reset()
                    elif self.state == GameState.GAME_OVER:
                        if event.key == pygame.K_r:
                            self.reset()
                            self.state = GameState.PLAYING

            if self.state == GameState.TITLE:
                self.update_title(dt)
            elif self.state == GameState.PLAYING:
                self.update_play(dt)
            elif self.state == GameState.SETTINGS:
                self.update_settings(dt, events)
            else:
                self.update_game_over(dt)

            if self.state == GameState.TITLE:
                self.draw_title()
            elif self.state == GameState.PLAYING:
                self.draw_play()
            elif self.state == GameState.SETTINGS:
                self.draw_settings()
            else:
                self.draw_game_over()

            pygame.display.flip()

        pygame.quit()


if __name__ == "__main__":
    Game().run()
