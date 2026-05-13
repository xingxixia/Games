# -*- coding: utf-8 -*-
"""A small desktop Plants-vs-Zombies-style game built with tkinter."""

from __future__ import annotations

import math
import os
import random
import sys
import traceback
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox


ROWS = 5
COLS = 9
CELL_W = 94
CELL_H = 82
LEFT_PAD = 74
TOP_PAD = 132
CANVAS_W = LEFT_PAD + COLS * CELL_W + 86
CANVAS_H = TOP_PAD + ROWS * CELL_H + 26


PLANTS = {
    "sunflower": {
        "name": "向日葵",
        "cost": 50,
        "hp": 170,
        "cooldown": 6.0,
        "produce": 7.2,
    },
    "peashooter": {
        "name": "豌豆射手",
        "cost": 100,
        "hp": 220,
        "cooldown": 7.2,
        "shoot": 1.35,
        "damage": 22,
    },
    "wallnut": {
        "name": "坚果墙",
        "cost": 50,
        "hp": 720,
        "cooldown": 11.0,
    },
    "snowpea": {
        "name": "寒冰射手",
        "cost": 175,
        "hp": 210,
        "cooldown": 9.0,
        "shoot": 1.75,
        "damage": 20,
        "slow": True,
    },
}

WAVES = [
    {"count": 3, "every": 2.8, "hp": 165, "speed": 15},
    {"count": 5, "every": 2.4, "hp": 190, "speed": 16},
    {"count": 7, "every": 2.1, "hp": 220, "speed": 17},
    {"count": 9, "every": 1.8, "hp": 255, "speed": 18},
    {"count": 12, "every": 1.45, "hp": 310, "speed": 20},
]


def configure_tcl_tk_paths() -> None:
    """Point tkinter at bundled Tcl/Tk data when running as a PyInstaller exe."""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if not bundle_dir:
        return
    tcl_dir = Path(bundle_dir) / "tcl8.6"
    tk_dir = Path(bundle_dir) / "tk8.6"
    if tcl_dir.exists():
        os.environ["TCL_LIBRARY"] = str(tcl_dir)
    if tk_dir.exists():
        os.environ["TK_LIBRARY"] = str(tk_dir)


@dataclass
class Plant:
    kind: str
    row: int
    col: int
    hp: float
    max_hp: float
    next_action: float


@dataclass
class Zombie:
    row: int
    x: float
    hp: float
    max_hp: float
    speed: float
    next_bite: float = 0.0
    slow_until: float = 0.0


@dataclass
class Projectile:
    row: int
    x: float
    y: float
    damage: float
    slow: bool = False


@dataclass
class Sun:
    x: float
    y: float
    target_y: float
    value: int
    expires: float


@dataclass
class Mower:
    row: int
    x: float
    active: bool = False
    used: bool = False


class PvZDesktop:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("草坪守卫战 - 桌面版")
        self.root.resizable(False, False)

        self.sun = 150
        self.selected: str | None = None
        self.shovel = False
        self.running = False
        self.ended = False
        self.wave = 0
        self.spawned = 0
        self.next_spawn = 0.0
        self.next_sky_sun = 0.0
        self.last_tick = time.perf_counter()

        self.board: list[list[Plant | None]] = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.projectiles: list[Projectile] = []
        self.suns: list[Sun] = []
        self.mowers: list[Mower] = [Mower(row, LEFT_PAD - 35) for row in range(ROWS)]
        self.cooldowns: dict[str, float] = {}
        self.card_buttons: dict[str, tk.Button] = {}

        self._build_ui()
        self._draw_static()
        self._redraw()
        self.root.after(16, self._tick)

    def _build_ui(self) -> None:
        self.canvas = tk.Canvas(
            self.root,
            width=CANVAS_W,
            height=CANVAS_H,
            bg="#7fbf68",
            highlightthickness=0,
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._click_canvas)

        self.sun_text = self.canvas.create_text(
            74,
            34,
            text=f"☀ {self.sun}",
            font=("Microsoft YaHei", 24, "bold"),
            fill="#3b2a16",
            tags=("ui",),
        )
        self.message_text = self.canvas.create_text(
            340,
            30,
            anchor="w",
            text="选择植物卡片，然后点击草坪格子。",
            font=("Microsoft YaHei", 13, "bold"),
            fill="#203224",
            tags=("ui",),
        )
        self.wave_text = self.canvas.create_text(
            CANVAS_W - 100,
            31,
            text=f"波次 0/{len(WAVES)}",
            font=("Microsoft YaHei", 15, "bold"),
            fill="#203224",
            tags=("ui",),
        )

        x = 20
        for kind, data in PLANTS.items():
            btn = tk.Button(
                self.root,
                text=f"{data['name']}\n☀ {data['cost']}",
                width=10,
                height=2,
                bg="#f6d77a",
                activebackground="#ffe88d",
                relief="raised",
                command=lambda value=kind: self._select_plant(value),
            )
            self.canvas.create_window(x + 54, 86, window=btn, width=104, height=52, tags=("ui",))
            self.card_buttons[kind] = btn
            x += 112

        self.shovel_btn = tk.Button(
            self.root,
            text="铲子",
            width=7,
            height=2,
            bg="#d8c28a",
            command=self._toggle_shovel,
        )
        self.canvas.create_window(x + 48, 86, window=self.shovel_btn, width=86, height=52, tags=("ui",))

        self.start_btn = tk.Button(
            self.root,
            text="开始",
            width=8,
            height=2,
            bg="#8bd35d",
            font=("Microsoft YaHei", 10, "bold"),
            command=self._start,
        )
        self.canvas.create_window(CANVAS_W - 58, 86, window=self.start_btn, width=84, height=52, tags=("ui",))

    def _draw_static(self) -> None:
        self.canvas.delete("static")
        self.canvas.create_rectangle(0, 0, CANVAS_W, TOP_PAD, fill="#f3df9a", outline="", tags=("static",))
        self.canvas.create_rectangle(
            0,
            TOP_PAD - 20,
            CANVAS_W,
            CANVAS_H,
            fill="#6d4529",
            outline="",
            tags=("static",),
        )
        for row in range(ROWS):
            for col in range(COLS):
                x1 = LEFT_PAD + col * CELL_W
                y1 = TOP_PAD + row * CELL_H
                x2 = x1 + CELL_W
                y2 = y1 + CELL_H
                color = "#78b85b" if (row + col) % 2 == 0 else "#69a94f"
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="#5b9442", tags=("static",))
                self.canvas.create_arc(
                    x1 + 18,
                    y1 + 12,
                    x1 + 48,
                    y1 + 40,
                    start=20,
                    extent=120,
                    outline="#8fcb70",
                    style="arc",
                    tags=("static",),
                )
        self.canvas.tag_lower("static")

    def _start(self) -> None:
        if self.running or self.ended:
            return
        now = time.perf_counter()
        self.running = True
        self.next_spawn = now + 1.2
        self.next_sky_sun = now + 5.0
        self.start_btn.config(text="守卫中", state="disabled")
        self._message("第一波正在靠近。")

    def _select_plant(self, kind: str) -> None:
        now = time.perf_counter()
        data = PLANTS[kind]
        if self.sun < data["cost"]:
            self._message("阳光不够。")
            return
        if self.cooldowns.get(kind, 0) > now:
            self._message("这张卡还在冷却。")
            return
        self.selected = kind
        self.shovel = False
        self._message(f"已选择{data['name']}。")
        self._update_buttons()

    def _toggle_shovel(self) -> None:
        self.shovel = not self.shovel
        self.selected = None
        self._message("铲子已拿起，点击植物移除。" if self.shovel else "铲子已收起。")
        self._update_buttons()

    def _click_canvas(self, event: tk.Event) -> None:
        if self.ended:
            return
        clicked_sun = self._sun_at(event.x, event.y)
        if clicked_sun:
            self.sun += clicked_sun.value
            self.suns.remove(clicked_sun)
            self._redraw()
            return

        row, col = self._cell_from_xy(event.x, event.y)
        if row is None or col is None:
            return
        existing = self.board[row][col]
        if self.shovel:
            if not existing:
                self._message("这里没有植物。")
                return
            self.board[row][col] = None
            self.plants.remove(existing)
            self._message("植物已铲除。")
            self._redraw()
            return
        if not self.selected:
            self._message("先选择一张植物卡片。")
            return
        if existing:
            self._message("这个格子已经有植物了。")
            return

        data = PLANTS[self.selected]
        now = time.perf_counter()
        if self.sun < data["cost"]:
            self._message("阳光不够。")
            return
        if self.cooldowns.get(self.selected, 0) > now:
            self._message("这张卡还在冷却。")
            return

        self.sun -= data["cost"]
        plant = Plant(self.selected, row, col, data["hp"], data["hp"], now + 1.0)
        self.board[row][col] = plant
        self.plants.append(plant)
        self.cooldowns[self.selected] = now + data["cooldown"]
        self._message(f"{data['name']}上场。")
        self.selected = None
        self._redraw()

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = min(0.05, now - self.last_tick)
        self.last_tick = now
        if self.running and not self.ended:
            self._update_game(now, dt)
        self._update_buttons()
        self._redraw()
        self.root.after(16, self._tick)

    def _update_game(self, now: float, dt: float) -> None:
        if self.wave < len(WAVES):
            wave = WAVES[self.wave]
            if self.spawned < wave["count"] and now >= self.next_spawn:
                self._spawn_zombie(now)
            if self.spawned >= wave["count"] and not self.zombies:
                self.wave += 1
                self.spawned = 0
                self.next_spawn = now + 2.4
                if self.wave >= len(WAVES):
                    self._finish(True)
                    return
                self._message(f"第 {self.wave + 1} 波来了。")

        if now >= self.next_sky_sun:
            x = random.uniform(LEFT_PAD + 50, LEFT_PAD + COLS * CELL_W - 45)
            y = random.uniform(TOP_PAD + 42, TOP_PAD + ROWS * CELL_H - 42)
            self.suns.append(Sun(x, TOP_PAD - 40, y, 25, now + 10.0))
            self.next_sky_sun = now + random.uniform(7.5, 10.5)

        self._update_plants(now)
        self._update_zombies(now, dt)
        self._update_mowers(dt)
        self._update_projectiles(now, dt)
        self._update_suns(now, dt)
        self._cleanup()

    def _spawn_zombie(self, now: float) -> None:
        wave = WAVES[self.wave]
        hp = wave["hp"] + random.uniform(0, 38)
        zombie = Zombie(
            row=random.randrange(ROWS),
            x=LEFT_PAD + COLS * CELL_W + 52,
            hp=hp,
            max_hp=hp,
            speed=wave["speed"] + random.uniform(0, 3.8),
        )
        self.zombies.append(zombie)
        self.spawned += 1
        self.next_spawn = now + wave["every"]

    def _update_plants(self, now: float) -> None:
        for plant in self.plants:
            data = PLANTS[plant.kind]
            cx, cy = self._cell_center(plant.row, plant.col)
            if "produce" in data and now >= plant.next_action:
                self.suns.append(Sun(cx + random.uniform(-18, 18), cy - 18, cy - 18, 25, now + 9.0))
                plant.next_action = now + data["produce"]
            if "shoot" in data and now >= plant.next_action:
                has_target = any(z.row == plant.row and z.x > cx - 12 for z in self.zombies)
                if has_target:
                    self.projectiles.append(
                        Projectile(
                            plant.row,
                            cx + 30,
                            cy - 10,
                            data["damage"],
                            bool(data.get("slow")),
                        )
                    )
                    plant.next_action = now + data["shoot"]

    def _update_zombies(self, now: float, dt: float) -> None:
        for zombie in self.zombies:
            blocker = None
            for plant in self.plants:
                if plant.row == zombie.row:
                    px, _ = self._cell_center(plant.row, plant.col)
                    if abs(zombie.x - px) < 36:
                        blocker = plant
                        break
            if blocker:
                if now >= zombie.next_bite:
                    blocker.hp -= 28
                    zombie.next_bite = now + 0.72
            else:
                speed = zombie.speed * (0.45 if now < zombie.slow_until else 1.0)
                zombie.x -= speed * dt

            if zombie.x < LEFT_PAD - 22:
                mower = next((m for m in self.mowers if m.row == zombie.row and not m.used), None)
                if mower:
                    mower.active = True
                    mower.used = True
                    self._message(f"第 {zombie.row + 1} 行小推车启动。")
                else:
                    self._finish(False)
                return

    def _update_mowers(self, dt: float) -> None:
        for mower in self.mowers:
            if not mower.active:
                continue
            mower.x += 520 * dt
            for zombie in self.zombies:
                if zombie.row == mower.row and mower.x - 48 < zombie.x < mower.x + 42:
                    zombie.hp = 0
            if mower.x > LEFT_PAD + COLS * CELL_W + 110:
                mower.active = False
                mower.x = -300

    def _update_projectiles(self, now: float, dt: float) -> None:
        for pea in self.projectiles:
            pea.x += 290 * dt
            for zombie in self.zombies:
                if zombie.row == pea.row and abs(zombie.x - pea.x) < 24:
                    zombie.hp -= pea.damage
                    if pea.slow:
                        zombie.slow_until = now + 2.6
                    pea.x = CANVAS_W + 100
                    break

    def _update_suns(self, now: float, dt: float) -> None:
        for sun in self.suns:
            if sun.y < sun.target_y:
                sun.y = min(sun.target_y, sun.y + 38 * dt)
        self.suns = [sun for sun in self.suns if sun.expires > now]

    def _cleanup(self) -> None:
        for plant in list(self.plants):
            if plant.hp <= 0:
                self.board[plant.row][plant.col] = None
                self.plants.remove(plant)
        self.zombies = [z for z in self.zombies if z.hp > 0]
        self.projectiles = [
            pea for pea in self.projectiles if LEFT_PAD - 10 < pea.x < LEFT_PAD + COLS * CELL_W + 90
        ]

    def _redraw(self) -> None:
        self.canvas.delete("actors")
        self.canvas.itemconfig(self.sun_text, text=f"☀ {self.sun}")
        self.canvas.itemconfig(self.wave_text, text=f"波次 {min(self.wave, len(WAVES))}/{len(WAVES)}")

        for mower in self.mowers:
            if mower.x > -100:
                self._draw_mower(mower)
        for plant in self.plants:
            self._draw_plant(plant)
        for pea in self.projectiles:
            self._draw_projectile(pea)
        for zombie in self.zombies:
            self._draw_zombie(zombie)
        for sun in self.suns:
            self._draw_sun(sun)

        if self.selected:
            self._draw_grid_hint("#fff06a")
        elif self.shovel:
            self._draw_grid_hint("#e7d0a4")

    def _draw_grid_hint(self, color: str) -> None:
        for row in range(ROWS):
            for col in range(COLS):
                x1 = LEFT_PAD + col * CELL_W + 3
                y1 = TOP_PAD + row * CELL_H + 3
                x2 = x1 + CELL_W - 6
                y2 = y1 + CELL_H - 6
                self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, tags=("actors",))

    def _draw_plant(self, plant: Plant) -> None:
        x, y = self._cell_center(plant.row, plant.col)
        if plant.kind == "sunflower":
            for i in range(12):
                angle = i * math.pi / 6
                px = x + math.cos(angle) * 17
                py = y - 9 + math.sin(angle) * 17
                self.canvas.create_oval(px - 8, py - 8, px + 8, py + 8, fill="#ffd54d", outline="", tags=("actors",))
            self.canvas.create_oval(x - 16, y - 25, x + 16, y + 7, fill="#7b4b21", outline="#553217", tags=("actors",))
        elif plant.kind == "wallnut":
            self.canvas.create_oval(x - 25, y - 34, x + 25, y + 28, fill="#b88145", outline="#704421", width=2, tags=("actors",))
            self.canvas.create_arc(x - 10, y - 28, x + 18, y + 24, start=95, extent=190, outline="#7a4b27", width=3, tags=("actors",))
        else:
            body = "#6ecf58" if plant.kind == "peashooter" else "#8eeef2"
            dark = "#3a9038" if plant.kind == "peashooter" else "#3eb8ca"
            self.canvas.create_line(x - 5, y + 24, x - 2, y + 6, fill="#2f7f36", width=8, tags=("actors",))
            self.canvas.create_oval(x - 25, y - 33, x + 15, y + 7, fill=body, outline="#2d6e34", width=2, tags=("actors",))
            self.canvas.create_oval(x + 2, y - 25, x + 38, y - 3, fill=body, outline="#2d6e34", width=2, tags=("actors",))
            self.canvas.create_oval(x + 25, y - 20, x + 36, y - 9, fill=dark, outline="", tags=("actors",))
        self._draw_hp(x, y - 42, plant.hp / plant.max_hp)

    def _draw_zombie(self, zombie: Zombie) -> None:
        y = TOP_PAD + zombie.row * CELL_H + CELL_H / 2
        skin = "#9eb89a" if time.perf_counter() >= zombie.slow_until else "#9fd4e7"
        self.canvas.create_line(zombie.x - 8, y + 10, zombie.x - 18, y + 38, fill="#51483e", width=8, tags=("actors",))
        self.canvas.create_line(zombie.x + 8, y + 10, zombie.x + 20, y + 38, fill="#51483e", width=8, tags=("actors",))
        self.canvas.create_rectangle(zombie.x - 17, y - 6, zombie.x + 18, y + 27, fill="#815b4a", outline="", tags=("actors",))
        self.canvas.create_oval(zombie.x - 19, y - 38, zombie.x + 18, y - 2, fill=skin, outline="#53654f", width=2, tags=("actors",))
        self.canvas.create_oval(zombie.x - 9, y - 26, zombie.x - 3, y - 20, fill="#151a14", outline="", tags=("actors",))
        self.canvas.create_oval(zombie.x + 7, y - 25, zombie.x + 13, y - 19, fill="#151a14", outline="", tags=("actors",))
        self.canvas.create_line(zombie.x - 8, y - 12, zombie.x + 12, y - 10, fill="#2c362b", width=2, tags=("actors",))
        self._draw_hp(zombie.x, y - 47, zombie.hp / zombie.max_hp)

    def _draw_projectile(self, pea: Projectile) -> None:
        color = "#7bd247" if not pea.slow else "#75d7ef"
        outline = "#2d6e20" if not pea.slow else "#23758c"
        self.canvas.create_oval(pea.x - 8, pea.y - 8, pea.x + 8, pea.y + 8, fill=color, outline=outline, tags=("actors",))

    def _draw_sun(self, sun: Sun) -> None:
        for i in range(12):
            angle = i * math.pi / 6
            x2 = sun.x + math.cos(angle) * 25
            y2 = sun.y + math.sin(angle) * 25
            self.canvas.create_line(sun.x, sun.y, x2, y2, fill="#ffc342", width=3, tags=("actors",))
        self.canvas.create_oval(sun.x - 18, sun.y - 18, sun.x + 18, sun.y + 18, fill="#ffe56b", outline="#e58d1e", width=2, tags=("actors",))

    def _draw_mower(self, mower: Mower) -> None:
        y = TOP_PAD + mower.row * CELL_H + CELL_H / 2 + 15
        self.canvas.create_rectangle(mower.x - 28, y - 16, mower.x + 28, y + 8, fill="#d33b31", outline="#7b1c18", width=2, tags=("actors",))
        self.canvas.create_polygon(mower.x - 20, y - 28, mower.x + 16, y - 28, mower.x + 30, y - 16, mower.x - 28, y - 16, fill="#f05a3d", outline="#7b1c18", tags=("actors",))
        self.canvas.create_line(mower.x + 20, y - 28, mower.x + 38, y - 42, fill="#633a22", width=5, tags=("actors",))
        self.canvas.create_oval(mower.x - 24, y + 2, mower.x - 10, y + 16, fill="#252525", outline="", tags=("actors",))
        self.canvas.create_oval(mower.x + 12, y + 2, mower.x + 26, y + 16, fill="#252525", outline="", tags=("actors",))

    def _draw_hp(self, x: float, y: float, ratio: float) -> None:
        ratio = max(0.0, min(1.0, ratio))
        self.canvas.create_rectangle(x - 25, y, x + 25, y + 5, fill="#2e302c", outline="", tags=("actors",))
        self.canvas.create_rectangle(x - 25, y, x - 25 + 50 * ratio, y + 5, fill="#6fd34e", outline="", tags=("actors",))

    def _update_buttons(self) -> None:
        now = time.perf_counter()
        for kind, btn in self.card_buttons.items():
            data = PLANTS[kind]
            ready = self.cooldowns.get(kind, 0) <= now
            affordable = self.sun >= data["cost"]
            label = f"{data['name']}\n☀ {data['cost']}"
            if not ready:
                label += f"  {math.ceil(self.cooldowns[kind] - now)}s"
            btn.config(
                text=label,
                state=("normal" if ready and affordable and not self.ended else "disabled"),
                bg=("#fff06a" if self.selected == kind else "#f6d77a"),
            )
        self.shovel_btn.config(bg=("#d9f06a" if self.shovel else "#d8c28a"), state=("disabled" if self.ended else "normal"))

    def _message(self, text: str) -> None:
        self.canvas.itemconfig(self.message_text, text=text)

    def _finish(self, won: bool) -> None:
        self.ended = True
        self.running = False
        self.start_btn.config(state="disabled")
        title = "胜利！" if won else "草坪失守"
        detail = "所有僵尸都被挡住了。" if won else "僵尸闯进了屋子。"
        self.canvas.create_rectangle(220, 245, CANVAS_W - 220, 415, fill="#fff0bd", outline="#4f311b", width=4, tags=("actors",))
        self.canvas.create_text(CANVAS_W / 2, 295, text=title, font=("Microsoft YaHei", 34, "bold"), fill="#2e2116", tags=("actors",))
        self.canvas.create_text(CANVAS_W / 2, 350, text=detail, font=("Microsoft YaHei", 16, "bold"), fill="#2e2116", tags=("actors",))
        self._message("关闭窗口后重新运行可再来一局。")

    def _cell_from_xy(self, x: float, y: float) -> tuple[int | None, int | None]:
        if x < LEFT_PAD or y < TOP_PAD:
            return None, None
        col = int((x - LEFT_PAD) // CELL_W)
        row = int((y - TOP_PAD) // CELL_H)
        if 0 <= row < ROWS and 0 <= col < COLS:
            return row, col
        return None, None

    def _cell_center(self, row: int, col: int) -> tuple[float, float]:
        return LEFT_PAD + col * CELL_W + CELL_W / 2, TOP_PAD + row * CELL_H + CELL_H / 2

    def _sun_at(self, x: float, y: float) -> Sun | None:
        for sun in reversed(self.suns):
            if (sun.x - x) ** 2 + (sun.y - y) ** 2 <= 24**2:
                return sun
        return None

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    configure_tcl_tk_paths()
    PvZDesktop().run()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_path = Path(__file__).with_name("GrassDefense-error.log")
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("GrassDefense 启动失败", f"{exc}\n\n错误日志：{log_path}")
            root.destroy()
        except Exception:
            pass
        raise
