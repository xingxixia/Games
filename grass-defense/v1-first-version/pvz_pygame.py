from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pygame


ROWS, COLS = 5, 9
CELL_W, CELL_H = 94, 78
LEFT, TOP = 82, 126
WIDTH, HEIGHT = LEFT + COLS * CELL_W + 76, TOP + ROWS * CELL_H + 30
FPS = 60

PLANTS = {
    "sunflower": {"name": "Sunflower", "cost": 50, "hp": 170, "cool": 6.0, "sun": 7.2},
    "peashooter": {"name": "Pea", "cost": 100, "hp": 220, "cool": 7.2, "shoot": 1.35, "damage": 22},
    "wallnut": {"name": "Wallnut", "cost": 50, "hp": 720, "cool": 11.0},
    "snowpea": {"name": "Snow Pea", "cost": 175, "hp": 210, "cool": 9.0, "shoot": 1.75, "damage": 20, "slow": True},
    "potatomine": {"name": "Potato Mine", "cost": 25, "hp": 120, "cool": 14.0, "arm": 4.5, "blast": 1300},
}

ZOMBIES = {
    "basic": {"name": "Zombie", "hp": 170, "speed": 15, "color": (158, 184, 154), "shirt": (129, 91, 74), "bite": 28},
    "cone": {"name": "Conehead", "hp": 310, "speed": 13, "color": (160, 184, 153), "shirt": (135, 83, 63), "bite": 28, "cone": True},
    "bucket": {"name": "Buckethead", "hp": 470, "speed": 11, "color": (156, 180, 152), "shirt": (102, 94, 105), "bite": 30, "bucket": True},
    "runner": {"name": "Runner", "hp": 135, "speed": 28, "color": (173, 190, 142), "shirt": (156, 68, 58), "bite": 22, "runner": True},
}

WAVES = [
    {"count": 4, "every": 2.8, "types": [("basic", 1.0)]},
    {"count": 6, "every": 2.35, "types": [("basic", 0.72), ("runner", 0.28)]},
    {"count": 8, "every": 2.05, "types": [("basic", 0.52), ("runner", 0.25), ("cone", 0.23)]},
    {"count": 11, "every": 1.7, "types": [("basic", 0.38), ("runner", 0.25), ("cone", 0.27), ("bucket", 0.10)]},
    {"count": 16, "every": 1.2, "types": [("basic", 0.26), ("runner", 0.24), ("cone", 0.30), ("bucket", 0.20)], "final": True},
]


@dataclass
class Plant:
    kind: str
    row: int
    col: int
    hp: float
    max_hp: float
    next_action: float
    planted_at: float
    armed: bool = False


@dataclass
class Zombie:
    kind: str
    row: int
    x: float
    hp: float
    max_hp: float
    speed: float
    bite: float
    next_bite: float = 0.0
    slow_until: float = 0.0
    hit_until: float = 0.0
    hit_x: float = 0.0
    hit_y: float = 0.0


@dataclass
class Pea:
    row: int
    x: float
    y: float
    damage: float
    slow: bool


@dataclass
class Sun:
    x: float
    y: float
    target_y: float
    expires: float
    value: int = 25


@dataclass
class Mower:
    row: int
    x: float
    active: bool = False
    used: bool = False


@dataclass
class Blast:
    x: float
    y: float
    until: float


@dataclass
class DeathEffect:
    x: float
    y: float
    kind: str
    started: float
    until: float
    seed: int


ACTION_SCHEMA = {
    "actions": [
        {"type": "start_game", "description": "Leave the start menu and begin wave spawning."},
        {"type": "toggle_pause", "description": "Pause or resume the game."},
        {"type": "select_card", "plant": "sunflower|peashooter|wallnut|snowpea|potatomine"},
        {"type": "place_plant", "plant": "sunflower|peashooter|wallnut|snowpea|potatomine", "row": "0-4", "col": "0-8"},
        {"type": "use_shovel", "row": "0-4", "col": "0-8"},
        {"type": "collect_sun", "index": "visible sun index from state.suns"},
        {"type": "click", "x": "screen x", "y": "screen y"},
        {"type": "wait", "seconds": "simulation seconds"},
        {"type": "export_observation", "path": "png output path"},
    ],
    "notes": [
        "Rows are top-to-bottom, columns are left-to-right.",
        "The observation image is what a vision model should inspect.",
        "The state JSON is a compact machine-readable helper, not hidden game logic for a player.",
    ],
}


class Game:
    def __init__(self, headless: bool = False) -> None:
        if headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Grass Defense")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 17)
        self.small_font = pygame.font.SysFont("arial", 14)
        self.mid_font = pygame.font.SysFont("arial", 24, bold=True)
        self.big_font = pygame.font.SysFont("arial", 48, bold=True)

        self.mode = "menu"
        self.paused = False
        self.ended = False
        self.won = False
        self.final_banner_until = 0.0

        self.sun = 150
        self.selected: str | None = None
        self.shovel = False
        self.wave = 0
        self.spawned = 0
        self.next_spawn = 0.0
        self.next_sky_sun = 0.0
        self.message = "Pick a plant card, then click the lawn."

        self.board: list[list[Plant | None]] = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.peas: list[Pea] = []
        self.suns: list[Sun] = []
        self.mowers = [Mower(row, LEFT - 38) for row in range(ROWS)]
        self.blasts: list[Blast] = []
        self.deaths: list[DeathEffect] = []
        self.cooldowns: dict[str, float] = {}

        self.card_rects: dict[str, pygame.Rect] = {}
        self.start_rect = pygame.Rect(0, 0, 0, 0)
        self.pause_rect = pygame.Rect(0, 0, 0, 0)
        self.shovel_rect = pygame.Rect(0, 0, 0, 0)
        self.menu_start_rect = pygame.Rect(WIDTH // 2 - 110, HEIGHT // 2 + 42, 220, 54)

    def run(self) -> None:
        last = time.perf_counter()
        while True:
            now = time.perf_counter()
            dt = min(0.05, now - last)
            last = now
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_p):
                    if self.mode == "game" and not self.ended:
                        self.paused = not self.paused
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.click(event.pos, now)
            if self.mode == "game" and not self.paused and not self.ended:
                self.update(now, dt)
            self.draw(now)
            pygame.display.flip()
            self.clock.tick(FPS)

    def click(self, pos: tuple[int, int], now: float) -> None:
        if self.mode == "menu":
            if self.menu_start_rect.collidepoint(pos):
                self.start_game(now)
            return
        if self.ended:
            return
        if self.pause_rect.collidepoint(pos):
            self.paused = not self.paused
            return
        if self.paused:
            return
        if self.shovel_rect.collidepoint(pos):
            self.shovel = not self.shovel
            self.selected = None
            self.message = "Shovel ready." if self.shovel else "Shovel put away."
            return
        for kind, rect in self.card_rects.items():
            data = PLANTS[kind]
            if rect.collidepoint(pos):
                ready = self.cooldowns.get(kind, 0) <= now
                if self.sun >= data["cost"] and ready:
                    self.selected = kind
                    self.shovel = False
                    self.message = f"Selected {data['name']}."
                else:
                    self.message = "Not enough sun or card is cooling."
                return
        for sun in list(self.suns):
            if (sun.x - pos[0]) ** 2 + (sun.y - pos[1]) ** 2 <= 26**2:
                self.sun += sun.value
                self.suns.remove(sun)
                return
        row, col = self.cell_at(pos)
        if row is None:
            return
        plant = self.board[row][col]
        if self.shovel:
            if plant:
                self.board[row][col] = None
                self.plants.remove(plant)
                self.message = "Plant removed."
            return
        if not self.selected:
            self.message = "Choose a card first."
            return
        if plant:
            self.message = "This tile is occupied."
            return
        data = PLANTS[self.selected]
        if self.sun < data["cost"] or self.cooldowns.get(self.selected, 0) > now:
            return
        self.sun -= data["cost"]
        new_plant = Plant(self.selected, row, col, data["hp"], data["hp"], now + 1.0, now)
        self.board[row][col] = new_plant
        self.plants.append(new_plant)
        self.cooldowns[self.selected] = now + data["cool"]
        self.message = f"{data['name']} planted."
        self.selected = None

    def start_game(self, now: float) -> None:
        self.mode = "game"
        self.paused = False
        self.next_spawn = now + 1.0
        self.next_sky_sun = now + 5.0
        self.message = "The first wave is coming."

    def perform_action(self, action: dict, now: float | None = None) -> None:
        now = time.perf_counter() if now is None else now
        kind = action.get("type")
        if kind == "start_game":
            if self.mode == "menu":
                self.start_game(now)
        elif kind == "toggle_pause":
            if self.mode == "game" and not self.ended:
                self.paused = not self.paused
        elif kind == "select_card":
            plant = action.get("plant")
            if plant in PLANTS:
                self.selected = plant
                self.shovel = False
        elif kind == "place_plant":
            plant = action.get("plant")
            row = int(action.get("row", -1))
            col = int(action.get("col", -1))
            if plant in PLANTS and 0 <= row < ROWS and 0 <= col < COLS:
                self.selected = plant
                x, y = self.center(row, col)
                self.click((int(x), int(y)), now)
        elif kind == "use_shovel":
            row = int(action.get("row", -1))
            col = int(action.get("col", -1))
            if 0 <= row < ROWS and 0 <= col < COLS:
                old = self.shovel
                self.shovel = True
                x, y = self.center(row, col)
                self.click((int(x), int(y)), now)
                self.shovel = old
        elif kind == "collect_sun":
            index = int(action.get("index", -1))
            if 0 <= index < len(self.suns):
                self.sun += self.suns[index].value
                self.suns.pop(index)
        elif kind == "click":
            self.click((int(action.get("x", 0)), int(action.get("y", 0))), now)
        elif kind == "wait":
            self.step_simulation(float(action.get("seconds", 0.5)))
        elif kind == "export_observation":
            self.export_observation(action.get("path", "observation.png"))

    def step_simulation(self, seconds: float, fps: int = FPS) -> None:
        steps = max(1, int(seconds * fps))
        dt = 1 / fps
        start = time.perf_counter()
        for step in range(steps):
            now = start + step * dt
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
            if self.mode == "game" and not self.paused and not self.ended:
                self.update(now, dt)

    def get_state(self) -> dict:
        now = time.perf_counter()
        return {
            "screen": {"width": WIDTH, "height": HEIGHT},
            "mode": self.mode,
            "paused": self.paused,
            "ended": self.ended,
            "won": self.won,
            "sun": self.sun,
            "wave": {"current": min(self.wave, len(WAVES)), "total": len(WAVES), "spawned_in_wave": self.spawned},
            "selected": self.selected,
            "message": self.message,
            "plants": [
                {
                    "kind": p.kind,
                    "row": p.row,
                    "col": p.col,
                    "hp": round(p.hp, 1),
                    "max_hp": p.max_hp,
                    "armed": p.armed,
                    "screen_xy": [round(self.center(p.row, p.col)[0]), round(self.center(p.row, p.col)[1])],
                }
                for p in self.plants
            ],
            "zombies": [
                {
                    "kind": z.kind,
                    "row": z.row,
                    "x": round(z.x, 1),
                    "hp": round(z.hp, 1),
                    "max_hp": round(z.max_hp, 1),
                    "slowed": now < z.slow_until,
                }
                for z in self.zombies
            ],
            "suns": [{"index": i, "x": round(s.x, 1), "y": round(s.y, 1), "value": s.value} for i, s in enumerate(self.suns)],
            "cards": [
                {
                    "plant": kind,
                    "cost": data["cost"],
                    "cooldown_remaining": round(max(0.0, self.cooldowns.get(kind, 0) - now), 2),
                    "affordable": self.sun >= data["cost"],
                }
                for kind, data in PLANTS.items()
            ],
            "actions": ACTION_SCHEMA["actions"],
        }

    def export_observation(self, image_path: str | Path, state_path: str | Path | None = None, schema_path: str | Path | None = None) -> None:
        now = time.perf_counter()
        self.draw(now)
        pygame.display.flip()
        image_path = Path(image_path)
        image_path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(self.screen, str(image_path))
        if state_path:
            Path(state_path).write_text(json.dumps(self.get_state(), indent=2), encoding="utf-8")
        if schema_path:
            Path(schema_path).write_text(json.dumps(ACTION_SCHEMA, indent=2), encoding="utf-8")

    def update(self, now: float, dt: float) -> None:
        if self.wave < len(WAVES):
            wave = WAVES[self.wave]
            if self.spawned < wave["count"] and now >= self.next_spawn:
                self.spawn_zombie(wave)
                self.spawned += 1
                self.next_spawn = now + wave["every"]
            if self.spawned >= wave["count"] and not self.zombies:
                self.wave += 1
                self.spawned = 0
                self.next_spawn = now + 2.4
                if self.wave >= len(WAVES):
                    self.finish(True)
                    return
                if WAVES[self.wave].get("final"):
                    self.final_banner_until = now + 3.0
                    self.message = "FINAL HUGE WAVE!"
                else:
                    self.message = f"Wave {self.wave + 1} is coming."

        if now >= self.next_sky_sun:
            x = random.uniform(LEFT + 40, LEFT + COLS * CELL_W - 40)
            target = random.uniform(TOP + 45, TOP + ROWS * CELL_H - 45)
            self.suns.append(Sun(x, TOP - 36, target, now + 10))
            self.next_sky_sun = now + random.uniform(7.5, 10.5)

        self.update_plants(now)
        self.update_zombies(now, dt)
        self.update_mowers(dt)
        self.update_peas(now, dt)
        self.update_suns(now, dt)
        self.cleanup(now)

    def spawn_zombie(self, wave: dict) -> None:
        kind = self.weighted_choice(wave["types"])
        data = ZOMBIES[kind]
        hp = data["hp"] + random.uniform(-8, 18)
        self.zombies.append(
            Zombie(kind, random.randrange(ROWS), LEFT + COLS * CELL_W + 52, hp, hp, data["speed"] + random.uniform(-1.2, 1.8), data["bite"])
        )

    def update_plants(self, now: float) -> None:
        for plant in list(self.plants):
            data = PLANTS[plant.kind]
            x, y = self.center(plant.row, plant.col)
            if plant.kind == "potatomine":
                if not plant.armed and now - plant.planted_at >= data["arm"]:
                    plant.armed = True
                if plant.armed:
                    victims = [z for z in self.zombies if z.row == plant.row and abs(z.x - x) < 44]
                    if victims:
                        for zombie in victims:
                            zombie.hp -= data["blast"]
                            zombie.hit_until = now + 0.18
                            zombie.hit_x = x
                            zombie.hit_y = y
                        self.blasts.append(Blast(x, y, now + 0.36))
                        plant.hp = 0
                continue
            if "sun" in data and now >= plant.next_action:
                target_y = y - 12 + random.uniform(-4, 8)
                self.suns.append(Sun(x + random.uniform(-16, 16), target_y - 28, target_y, now + 9))
                plant.next_action = now + data["sun"]
            if "shoot" in data and now >= plant.next_action and any(z.row == plant.row and z.x > x - 12 for z in self.zombies):
                self.peas.append(Pea(plant.row, x + 28, y - 8, data["damage"], bool(data.get("slow"))))
                plant.next_action = now + data["shoot"]

    def update_zombies(self, now: float, dt: float) -> None:
        for zombie in self.zombies:
            blocker = next((p for p in self.plants if p.row == zombie.row and abs(zombie.x - self.center(p.row, p.col)[0]) < 36), None)
            if blocker:
                if now >= zombie.next_bite:
                    blocker.hp -= zombie.bite
                    zombie.next_bite = now + 0.72
            else:
                zombie.x -= zombie.speed * (0.45 if now < zombie.slow_until else 1) * dt
            if zombie.x < LEFT - 22:
                mower = next((m for m in self.mowers if m.row == zombie.row and not m.used), None)
                if mower:
                    mower.active = True
                    mower.used = True
                    self.message = f"Lane {zombie.row + 1} mower launched."
                else:
                    self.finish(False)
                return

    def update_mowers(self, dt: float) -> None:
        for mower in self.mowers:
            if mower.active:
                mower.x += 520 * dt
                for zombie in self.zombies:
                    if zombie.row == mower.row and mower.x - 48 < zombie.x < mower.x + 42:
                        zombie.hp = 0
                if mower.x > LEFT + COLS * CELL_W + 120:
                    mower.active = False
                    mower.x = -400

    def update_peas(self, now: float, dt: float) -> None:
        for pea in self.peas:
            pea.x += 290 * dt
            for zombie in self.zombies:
                if zombie.row == pea.row and abs(zombie.x - pea.x) < 24:
                    zombie.hp -= pea.damage
                    zombie.hit_until = now + 0.16
                    zombie.hit_x = pea.x
                    zombie.hit_y = pea.y
                    if pea.slow:
                        zombie.slow_until = now + 2.6
                    pea.x = WIDTH + 100
                    break

    def update_suns(self, now: float, dt: float) -> None:
        for sun in self.suns:
            if sun.y < sun.target_y:
                sun.y = min(sun.target_y, sun.y + 38 * dt)

    def cleanup(self, now: float) -> None:
        for plant in list(self.plants):
            if plant.hp <= 0:
                self.board[plant.row][plant.col] = None
                self.plants.remove(plant)
        for zombie in list(self.zombies):
            if zombie.hp <= 0:
                y = TOP + zombie.row * CELL_H + CELL_H / 2
                self.deaths.append(DeathEffect(zombie.x, y, zombie.kind, now, now + 0.75, random.randrange(100000)))
                self.zombies.remove(zombie)
        self.peas = [p for p in self.peas if p.x < WIDTH + 50]
        self.suns = [s for s in self.suns if s.expires > now]
        self.blasts = [b for b in self.blasts if b.until > now]
        self.deaths = [d for d in self.deaths if d.until > now]

    def draw(self, now: float) -> None:
        if self.mode == "menu":
            self.draw_menu()
            return
        self.screen.fill((130, 190, 105))
        pygame.draw.rect(self.screen, (244, 222, 154), (0, 0, WIDTH, TOP))
        self.draw_text(f"Sun {self.sun}", 24, 22, self.mid_font, (55, 42, 20))
        self.draw_text(self.message, 200, 28, self.font, (30, 50, 36))
        self.draw_text(f"Wave {min(self.wave, len(WAVES))}/{len(WAVES)}", WIDTH - 140, 28, self.font, (30, 50, 36))
        self.draw_cards(now)
        self.draw_board()

        for mower in self.mowers:
            if mower.x > -100:
                self.draw_mower(mower)
        for plant in self.plants:
            self.draw_plant(plant, now)
        for pea in self.peas:
            pygame.draw.circle(self.screen, (117, 215, 239) if pea.slow else (123, 210, 71), (int(pea.x), int(pea.y)), 8)
        for zombie in self.zombies:
            self.draw_zombie(zombie, now)
        for death in self.deaths:
            self.draw_death_effect(death, now)
        for sun in self.suns:
            self.draw_sun(sun)
        for blast in self.blasts:
            pulse = max(0, (blast.until - now) / 0.36)
            radius = int(80 * (1 - pulse) + 22)
            pygame.draw.circle(self.screen, (255, 201, 83), (int(blast.x), int(blast.y)), radius, 5)

        if now < self.final_banner_until:
            banner = self.big_font.render("A HUGE WAVE IS APPROACHING!", True, (180, 38, 28))
            self.screen.blit(banner, (WIDTH / 2 - banner.get_width() / 2, HEIGHT / 2 - 34))
        if self.paused:
            self.draw_center_panel("PAUSED", "Click Pause or press P/Space to continue.")
        if self.ended:
            self.draw_center_panel("VICTORY!" if self.won else "LAWN LOST", "Close the window and run again to restart.")

    def draw_menu(self) -> None:
        self.screen.fill((90, 151, 83))
        pygame.draw.rect(self.screen, (116, 178, 95), (0, HEIGHT * 0.42, WIDTH, HEIGHT * 0.58))
        title = self.big_font.render("GRASS DEFENSE", True, (255, 239, 158))
        self.screen.blit(title, (WIDTH / 2 - title.get_width() / 2, 116))
        subtitle = self.font.render("A tiny PVZ-like prototype made for AI game-making practice", True, (31, 52, 32))
        self.screen.blit(subtitle, (WIDTH / 2 - subtitle.get_width() / 2, 178))
        pygame.draw.rect(self.screen, (246, 215, 122), self.menu_start_rect, border_radius=8)
        pygame.draw.rect(self.screen, (80, 50, 25), self.menu_start_rect, 3, border_radius=8)
        label = self.mid_font.render("START GAME", True, (45, 32, 20))
        self.screen.blit(label, (self.menu_start_rect.centerx - label.get_width() / 2, self.menu_start_rect.y + 13))

    def draw_cards(self, now: float) -> None:
        x = 16
        self.card_rects.clear()
        for kind, data in PLANTS.items():
            rect = pygame.Rect(x, 62, 98, 54)
            self.card_rects[kind] = rect
            ready_at = self.cooldowns.get(kind, 0)
            remaining = max(0.0, ready_at - now)
            ready = remaining <= 0
            color = (255, 240, 106) if self.selected == kind else (246, 215, 122)
            if self.sun < data["cost"] or not ready:
                color = (178, 164, 125)
            pygame.draw.rect(self.screen, color, rect, border_radius=6)
            pygame.draw.rect(self.screen, (80, 50, 25), rect, 2, border_radius=6)
            self.draw_multiline(f"{data['name']}\nSun {data['cost']}", rect.centerx, rect.y + 6, self.small_font)
            if remaining > 0:
                ratio = min(1.0, remaining / data["cool"])
                overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
                overlay.fill((25, 25, 25, 120))
                self.screen.blit(overlay, rect)
                h = int(rect.height * ratio)
                pygame.draw.rect(self.screen, (44, 44, 44, 160), (rect.x, rect.bottom - h, rect.width, h), border_radius=6)
                sec = self.mid_font.render(str(math.ceil(remaining)), True, (255, 255, 255))
                self.screen.blit(sec, (rect.centerx - sec.get_width() / 2, rect.centery - sec.get_height() / 2))
            x += 103
        self.shovel_rect = pygame.Rect(x + 4, 62, 72, 54)
        pygame.draw.rect(self.screen, (217, 240, 106) if self.shovel else (216, 194, 138), self.shovel_rect, border_radius=6)
        pygame.draw.rect(self.screen, (80, 50, 25), self.shovel_rect, 2, border_radius=6)
        self.draw_text("Shovel", self.shovel_rect.x + 11, self.shovel_rect.y + 18, self.small_font, (40, 30, 18))
        self.pause_rect = pygame.Rect(WIDTH - 86, 62, 68, 54)
        pygame.draw.rect(self.screen, (139, 211, 93), self.pause_rect, border_radius=6)
        pygame.draw.rect(self.screen, (80, 50, 25), self.pause_rect, 2, border_radius=6)
        self.draw_text("Pause" if not self.paused else "Resume", self.pause_rect.x + 8, self.pause_rect.y + 18, self.small_font, (30, 42, 22))

    def draw_board(self) -> None:
        pygame.draw.rect(self.screen, (106, 69, 39), (0, TOP, LEFT, ROWS * CELL_H))
        for row in range(ROWS):
            for col in range(COLS):
                rect = pygame.Rect(LEFT + col * CELL_W, TOP + row * CELL_H, CELL_W, CELL_H)
                color = (120, 184, 91) if (row + col) % 2 == 0 else (105, 169, 79)
                pygame.draw.rect(self.screen, color, rect)
                pygame.draw.rect(self.screen, (91, 148, 66), rect, 1)
                if self.selected or self.shovel:
                    pygame.draw.rect(self.screen, (255, 240, 106), rect.inflate(-7, -7), 2)

    def draw_plant(self, plant: Plant, now: float) -> None:
        x, y = self.center(plant.row, plant.col)
        if plant.kind == "sunflower":
            for i in range(12):
                a = i * math.pi / 6
                pygame.draw.circle(self.screen, (255, 213, 77), (int(x + math.cos(a) * 18), int(y - 10 + math.sin(a) * 18)), 8)
            pygame.draw.circle(self.screen, (123, 75, 33), (int(x), int(y - 10)), 17)
        elif plant.kind == "wallnut":
            pygame.draw.ellipse(self.screen, (184, 129, 69), (x - 25, y - 34, 50, 62))
            pygame.draw.circle(self.screen, (45, 32, 22), (int(x - 9), int(y - 8)), 3)
            pygame.draw.circle(self.screen, (45, 32, 22), (int(x + 9), int(y - 8)), 3)
        elif plant.kind == "potatomine":
            armed = plant.armed
            body = (151, 90, 47) if armed else (115, 78, 47)
            pygame.draw.ellipse(self.screen, body, (x - 23, y - 13, 46, 30))
            pygame.draw.circle(self.screen, (38, 30, 22), (int(x - 7), int(y - 2)), 3)
            pygame.draw.circle(self.screen, (38, 30, 22), (int(x + 8), int(y - 3)), 3)
            if armed:
                pygame.draw.circle(self.screen, (230, 55, 38), (int(x), int(y - 21)), 6)
            else:
                left = max(0, PLANTS["potatomine"]["arm"] - (now - plant.planted_at))
                self.draw_text(str(math.ceil(left)), x - 5, y - 36, self.small_font, (60, 40, 20))
        else:
            body = (110, 207, 88) if plant.kind == "peashooter" else (142, 238, 242)
            pygame.draw.line(self.screen, (47, 127, 54), (x - 4, y + 25), (x - 2, y + 5), 8)
            pygame.draw.circle(self.screen, body, (int(x - 8), int(y - 14)), 20)
            pygame.draw.ellipse(self.screen, body, (x + 4, y - 25, 36, 22))
        self.draw_hp(x, y - 43, plant.hp / plant.max_hp)

    def draw_zombie(self, zombie: Zombie, now: float) -> None:
        data = ZOMBIES[zombie.kind]
        y = TOP + zombie.row * CELL_H + CELL_H / 2
        if now < zombie.hit_until:
            skin = (255, 238, 156)
        elif now < zombie.slow_until:
            skin = (159, 212, 231)
        else:
            skin = data["color"]
        pygame.draw.line(self.screen, (81, 72, 62), (zombie.x - 8, y + 8), (zombie.x - 18, y + 36), 8)
        pygame.draw.line(self.screen, (81, 72, 62), (zombie.x + 8, y + 8), (zombie.x + 20, y + 36), 8)
        pygame.draw.rect(self.screen, data["shirt"], (zombie.x - 17, y - 5, 35, 32))
        pygame.draw.circle(self.screen, skin, (int(zombie.x), int(y - 22)), 19)
        pygame.draw.circle(self.screen, (18, 23, 18), (int(zombie.x - 8), int(y - 26)), 3)
        pygame.draw.circle(self.screen, (18, 23, 18), (int(zombie.x + 8), int(y - 25)), 3)
        if data.get("cone"):
            pygame.draw.polygon(self.screen, (224, 108, 31), [(zombie.x - 12, y - 38), (zombie.x + 12, y - 38), (zombie.x, y - 62)])
        if data.get("bucket"):
            pygame.draw.rect(self.screen, (166, 174, 181), (zombie.x - 15, y - 45, 30, 16))
        if data.get("runner"):
            pygame.draw.line(self.screen, (242, 230, 88), (zombie.x - 22, y - 8), (zombie.x - 38, y - 8), 3)
        if now < zombie.hit_until:
            pulse = 1 - (zombie.hit_until - now) / 0.16
            pygame.draw.circle(self.screen, (255, 245, 128), (int(zombie.hit_x), int(zombie.hit_y)), int(8 + pulse * 12), 3)
        self.draw_hp(zombie.x, y - 50, zombie.hp / zombie.max_hp)

    def draw_death_effect(self, death: DeathEffect, now: float) -> None:
        progress = 1 - max(0.0, (death.until - now) / (death.until - death.started))
        alpha = int(210 * (1 - progress))
        rng = random.Random(death.seed)
        dust = pygame.Surface((120, 90), pygame.SRCALPHA)
        for _ in range(9):
            angle = rng.uniform(math.pi * 0.9, math.pi * 2.1)
            speed = rng.uniform(18, 54)
            px = 60 + math.cos(angle) * speed * progress
            py = 54 + math.sin(angle) * speed * progress + 18 * progress
            radius = int(rng.uniform(4, 9) * (1 - progress * 0.45))
            pygame.draw.circle(dust, (93, 74, 54, max(0, alpha - 40)), (int(px), int(py)), max(1, radius))
        pygame.draw.ellipse(dust, (64, 52, 42, max(0, alpha - 70)), (22, 56, 76, 15))
        self.screen.blit(dust, (death.x - 60, death.y - 48))

        body_alpha = int(230 * (1 - progress))
        corpse = pygame.Surface((92, 64), pygame.SRCALPHA)
        data = ZOMBIES[death.kind]
        tilt = progress * 18
        pygame.draw.line(corpse, (81, 72, 62, body_alpha), (38 - tilt, 44), (22 - tilt, 56), 7)
        pygame.draw.line(corpse, (81, 72, 62, body_alpha), (54 - tilt, 43), (73 - tilt, 55), 7)
        pygame.draw.rect(corpse, (*data["shirt"], body_alpha), (30 - tilt, 25, 36, 21))
        pygame.draw.circle(corpse, (*data["color"], body_alpha), (int(38 - tilt), 24), 16)
        pygame.draw.circle(corpse, (18, 23, 18, body_alpha), (int(33 - tilt), 20), 3)
        if data.get("cone"):
            pygame.draw.polygon(corpse, (224, 108, 31, body_alpha), [(23 - tilt, 13), (45 - tilt, 12), (34 - tilt, -8)])
        if data.get("bucket"):
            pygame.draw.rect(corpse, (166, 174, 181, body_alpha), (23 - tilt, 5, 30, 14))
        self.screen.blit(corpse, (death.x - 45, death.y - 30 + progress * 18))

    def draw_mower(self, mower: Mower) -> None:
        y = TOP + mower.row * CELL_H + CELL_H / 2 + 13
        pygame.draw.rect(self.screen, (211, 59, 49), (mower.x - 28, y - 16, 56, 24))
        pygame.draw.polygon(self.screen, (240, 90, 61), [(mower.x - 22, y - 28), (mower.x + 16, y - 28), (mower.x + 30, y - 16), (mower.x - 28, y - 16)])
        pygame.draw.circle(self.screen, (32, 32, 32), (int(mower.x - 18), int(y + 10)), 8)
        pygame.draw.circle(self.screen, (32, 32, 32), (int(mower.x + 18), int(y + 10)), 8)

    def draw_sun(self, sun: Sun) -> None:
        for i in range(12):
            a = i * math.pi / 6
            pygame.draw.line(self.screen, (255, 195, 66), (sun.x, sun.y), (sun.x + math.cos(a) * 25, sun.y + math.sin(a) * 25), 3)
        pygame.draw.circle(self.screen, (255, 229, 107), (int(sun.x), int(sun.y)), 18)

    def draw_hp(self, x: float, y: float, ratio: float) -> None:
        ratio = max(0, min(1, ratio))
        pygame.draw.rect(self.screen, (46, 48, 44), (x - 25, y, 50, 5))
        pygame.draw.rect(self.screen, (111, 211, 78), (x - 25, y, 50 * ratio, 5))

    def draw_center_panel(self, title: str, detail: str) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 100))
        self.screen.blit(shade, (0, 0))
        panel = pygame.Rect(WIDTH // 2 - 240, HEIGHT // 2 - 86, 480, 172)
        pygame.draw.rect(self.screen, (255, 240, 189), panel, border_radius=8)
        pygame.draw.rect(self.screen, (79, 49, 27), panel, 4, border_radius=8)
        title_surf = self.big_font.render(title, True, (45, 32, 20))
        self.screen.blit(title_surf, (panel.centerx - title_surf.get_width() / 2, panel.y + 26))
        detail_surf = self.font.render(detail, True, (45, 32, 20))
        self.screen.blit(detail_surf, (panel.centerx - detail_surf.get_width() / 2, panel.y + 110))

    def draw_text(self, text: str, x: float, y: float, font: pygame.font.Font, color: tuple[int, int, int]) -> None:
        self.screen.blit(font.render(text, True, color), (x, y))

    def draw_multiline(self, text: str, cx: float, y: float, font: pygame.font.Font) -> None:
        for i, line in enumerate(text.splitlines()):
            surf = font.render(line, True, (43, 32, 20))
            self.screen.blit(surf, (cx - surf.get_width() / 2, y + i * 18))

    def cell_at(self, pos: tuple[int, int]) -> tuple[int | None, int | None]:
        x, y = pos
        if x < LEFT or y < TOP:
            return None, None
        col = int((x - LEFT) // CELL_W)
        row = int((y - TOP) // CELL_H)
        if 0 <= row < ROWS and 0 <= col < COLS:
            return row, col
        return None, None

    def center(self, row: int, col: int) -> tuple[float, float]:
        return LEFT + col * CELL_W + CELL_W / 2, TOP + row * CELL_H + CELL_H / 2

    def weighted_choice(self, items: list[tuple[str, float]]) -> str:
        roll = random.random() * sum(weight for _, weight in items)
        upto = 0.0
        for name, weight in items:
            upto += weight
            if roll <= upto:
                return name
        return items[-1][0]

    def finish(self, won: bool) -> None:
        self.ended = True
        self.won = won
        self.message = "Victory." if won else "Zombies entered the house."


def load_actions(path: str | None) -> list[dict]:
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("actions", [data])
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Grass Defense game and AI test interface.")
    parser.add_argument("--export-observation", metavar="PNG", help="Render one frame to a PNG file.")
    parser.add_argument("--export-state", metavar="JSON", help="Write machine-readable game state JSON.")
    parser.add_argument("--export-schema", metavar="JSON", help="Write action interface schema JSON.")
    parser.add_argument("--actions", metavar="JSON", help="Apply a JSON action or action list before exporting/running.")
    parser.add_argument("--simulate", type=float, default=0.0, help="Run headless simulation for N seconds.")
    parser.add_argument("--headless", action="store_true", help="Use dummy SDL video driver for automation.")
    parser.add_argument("--run", action="store_true", help="Open the playable game window after setup.")
    args = parser.parse_args()

    automation = bool(args.headless or args.export_observation or args.export_state or args.export_schema or args.actions or args.simulate)
    game = Game(headless=args.headless or (automation and not args.run))
    now = time.perf_counter()
    for action in load_actions(args.actions):
        game.perform_action(action, now)
    if args.simulate:
        game.step_simulation(args.simulate)
    if args.export_observation or args.export_state or args.export_schema:
        image_path = args.export_observation or "observation.png"
        game.export_observation(image_path, args.export_state, args.export_schema)
    if args.run or not automation:
        game.run()
    pygame.quit()


if __name__ == "__main__":
    main()
