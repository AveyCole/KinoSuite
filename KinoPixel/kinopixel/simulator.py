"""Live 60fps Hardware-Faithful Playtest Engine for KinoPixel (GB / GBC / GBA).

Mirrors the exact compiled GBA ARM7TDMI kernel behavior: tilemap collisions,
user-wired button rules, multi-frame sprite animations, patrolling enemies,
projectiles, camera scroll, HUD, and real-time chiptune SFX playback.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, List, Optional, Set, Tuple

import numpy as np

from .models import (
    ACTION_DASH,
    ACTION_JUMP,
    ACTION_MELEE,
    ACTION_MOVE_DOWN,
    ACTION_MOVE_LEFT,
    ACTION_MOVE_RIGHT,
    ACTION_MOVE_UP,
    ACTION_PALETTE_NEXT,
    ACTION_PAUSE,
    ACTION_PLAY_SFX,
    ACTION_RESET_LEVEL,
    ACTION_SHOOT,
    ACTION_SWITCH_ANIM,
    BUTTON_BITS,
    KinoPixelProject,
    TILE_BOUNCE,
    TILE_COIN,
    TILE_GOAL,
    TILE_HAZARD,
    TILE_ONEWAY,
    TILE_SOLID,
    TRIGGER_HELD,
    TRIGGER_PRESSED,
    TRIGGER_RELEASED,
    hex_to_rgb,
)


@dataclass
class _LiveProj:
    active: bool = False
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0


@dataclass
class _LiveEnemy:
    active: bool = True
    x: float = 0.0
    y: float = 0.0
    min_x: float = 0.0
    max_x: float = 0.0
    direction: int = 1
    speed: int = 1
    sprite_index: int = 1


class GamePlaytestEngine:
    """Deterministic 60 FPS simulator matching the compiled .gba ROM engine 1:1."""

    def __init__(self, project: KinoPixelProject, on_sfx: Optional[Callable[[int], None]] = None) -> None:
        self.project = project
        self.on_sfx = on_sfx
        self.cells: List[List[int]] = []
        self.px: float = 0.0
        self.py: float = 0.0
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.facing: int = 0  # 0=right, 1=left
        self.on_ground: bool = False
        self.palette_idx: int = 0
        self.anim_name: str = "idle"
        self.anim_timer: int = 0
        self.anim_lock: int = 0
        self.score: int = 0
        self.coins: int = 0
        self.hp: int = 3
        self.invuln: int = 0
        self.paused: bool = False
        self.won: bool = False
        self.cam_x: int = 0
        self.cam_y: int = 0
        self.frame: int = 0
        self.dash_timer: int = 0
        self.melee_timer: int = 0
        self.shoot_cd: int = 0
        self.prev_keys: int = 0
        self.curr_keys: int = 0
        self.projs: List[_LiveProj] = []
        self.enemies: List[_LiveEnemy] = []
        self.reset()

    def set_project(self, project: KinoPixelProject) -> None:
        self.project = project
        self.reset()

    def reset(self) -> None:
        lvl = self.project.level
        self.cells = copy.deepcopy(lvl.cells)
        self.px = float(max(8, min((lvl.width - 2) * 8, lvl.spawn_x * 8)))
        self.py = float(max(8, min((lvl.height - 2) * 8, lvl.spawn_y * 8)))
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 0
        self.on_ground = False
        self.anim_name = "idle"
        self.anim_timer = 0
        self.anim_lock = 0
        self.score = 0
        self.coins = 0
        self.hp = 3
        self.invuln = 0
        self.paused = False
        self.won = False
        self.dash_timer = 0
        self.melee_timer = 0
        self.shoot_cd = 0
        self.projs = [_LiveProj() for _ in range(4)]
        self.enemies = []
        for e in lvl.entities[:16]:
            ex = float(max(8, min((lvl.width - 2) * 8, e.tile_x * 8)))
            ey = float(max(8, min((lvl.height - 2) * 8, e.tile_y * 8)))
            pr = max(1, e.patrol_range) * 8.0
            self.enemies.append(
                _LiveEnemy(
                    active=True,
                    x=ex,
                    y=ey,
                    min_x=max(8.0, ex - pr),
                    max_x=min((lvl.width - 2) * 8.0, ex + pr),
                    direction=1,
                    speed=max(1, min(4, e.speed)),
                    sprite_index=e.sprite_index,
                )
            )
        self._update_camera()

    def _emit_sfx(self, idx: int) -> None:
        if self.on_sfx and 0 <= idx < len(self.project.sfx_list):
            self.on_sfx(idx)

    def _find_sfx(self, keyword: str, fallback: int) -> int:
        for i, p in enumerate(self.project.sfx_list):
            if keyword in p.name.lower():
                return i
        return fallback if fallback < len(self.project.sfx_list) else -1

    def _tile_type_at_px(self, x: float, y: float) -> int:
        tx = int(x) // 8
        ty = int(y) // 8
        lvl = self.project.level
        if tx < 0 or tx >= lvl.width:
            return TILE_SOLID
        if ty < 0 or ty >= lvl.height:
            return 0
        ti = self.cells[ty][tx]
        if 0 <= ti < len(self.project.tiles):
            return self.project.tiles[ti].tile_type
        return 0

    def _damage_respawn(self) -> None:
        if self.invuln > 0:
            return
        self._emit_sfx(self._find_sfx("hurt", 4))
        self.hp -= 1
        if self.hp <= 0:
            self.reset()
            return
        self.invuln = 45
        lvl = self.project.level
        self.px = float(max(8, min((lvl.width - 2) * 8, lvl.spawn_x * 8)))
        self.py = float(max(8, min((lvl.height - 2) * 8, lvl.spawn_y * 8)))
        self.vx = 0.0
        self.vy = 0.0

    def step(self, pressed_buttons: Set[str]) -> None:
        """Advance simulation by one 60 Hz frame."""
        self.frame += 1
        self.prev_keys = self.curr_keys
        mask = 0
        for b in pressed_buttons:
            mask |= BUTTON_BITS.get(b.upper(), 0)
        self.curr_keys = mask
        just_pressed = self.curr_keys & ~self.prev_keys
        released = self.prev_keys & ~self.curr_keys

        if self.won:
            if just_pressed & (BUTTON_BITS["START"] | BUTTON_BITS["A"]):
                self.reset()
            return

        if self.invuln > 0:
            self.invuln -= 1
        if self.anim_lock > 0:
            self.anim_lock -= 1
        if self.dash_timer > 0:
            self.dash_timer -= 1
        if self.melee_timer > 0:
            self.melee_timer -= 1
        if self.shoot_cd > 0:
            self.shoot_cd -= 1

        moved = False
        if self.dash_timer == 0:
            self.vx = 0.0
            if self.project.physics_mode == "topdown":
                self.vy = 0.0

        # Evaluate user-wired button rules
        for rule in self.project.button_rules:
            if not rule.enabled:
                continue
            rmask = BUTTON_BITS.get(rule.button.upper(), 0)
            if rmask == 0:
                continue
            src = self.curr_keys if rule.trigger == TRIGGER_HELD else (just_pressed if rule.trigger == TRIGGER_PRESSED else released)
            if not (src & rmask):
                continue
            if self.paused and rule.action not in (ACTION_PAUSE, ACTION_RESET_LEVEL):
                continue

            triggered = True
            if rule.action == ACTION_MOVE_LEFT:
                self.vx = -rule.param * 0.5
                self.facing = 1
                moved = True
            elif rule.action == ACTION_MOVE_RIGHT:
                self.vx = rule.param * 0.5
                self.facing = 0
                moved = True
            elif rule.action == ACTION_MOVE_UP:
                self.vy = -rule.param * 0.5
                moved = True
            elif rule.action == ACTION_MOVE_DOWN:
                self.vy = rule.param * 0.5
                moved = True
            elif rule.action == ACTION_JUMP:
                if self.on_ground:
                    self.vy = -(rule.param * 0.5 + 0.75)
                    self.on_ground = False
                else:
                    triggered = False
            elif rule.action == ACTION_DASH:
                spd = rule.param * 0.5 + 0.5
                self.vx = -spd if self.facing else spd
                self.dash_timer = 10
            elif rule.action == ACTION_SHOOT:
                if self.shoot_cd == 0:
                    self.shoot_cd = 12
                    for pr in self.projs:
                        if not pr.active:
                            pr.active = True
                            pr.x = self.px + (-8 if self.facing else 8)
                            pr.y = self.py
                            spd = max(1, rule.param)
                            pr.vx = -float(spd) if self.facing else float(spd)
                            break
                else:
                    triggered = False
            elif rule.action == ACTION_MELEE:
                self.melee_timer = 14
            elif rule.action == ACTION_PALETTE_NEXT:
                self.palette_idx = (self.palette_idx + 1) % max(1, len(self.project.palettes))
            elif rule.action == ACTION_RESET_LEVEL:
                self.reset()
                return
            elif rule.action == ACTION_PAUSE:
                self.paused = not self.paused
            elif rule.action in (ACTION_PLAY_SFX, ACTION_SWITCH_ANIM):
                pass

            if triggered:
                if rule.anim_name and rule.trigger == TRIGGER_PRESSED:
                    self.anim_name = rule.anim_name
                    self.anim_lock = 14
                if rule.sfx_index >= 0:
                    self._emit_sfx(rule.sfx_index)

        if self.paused:
            return

        # Gravity in platformer mode
        if self.project.physics_mode == "platformer":
            self.vy = min(self.project.max_fall_speed / 256.0, self.vy + self.project.gravity / 256.0)

        lvl = self.project.level
        lvl_w_px = lvl.width * 8
        lvl_h_px = lvl.height * 8

        # Horizontal move + solid collision
        new_x = max(0.0, min(lvl_w_px - 16.0, self.px + self.vx))
        if self.vx > 0:
            if self._tile_type_at_px(new_x + 13, self.py + 2) == TILE_SOLID or self._tile_type_at_px(new_x + 13, self.py + 13) == TILE_SOLID:
                new_x = self.px
                self.vx = 0.0
        elif self.vx < 0:
            if self._tile_type_at_px(new_x + 2, self.py + 2) == TILE_SOLID or self._tile_type_at_px(new_x + 2, self.py + 13) == TILE_SOLID:
                new_x = self.px
                self.vx = 0.0
        self.px = new_x

        # Vertical move + solid / oneway collision
        self.on_ground = False
        new_y = max(0.0, self.py + self.vy)
        if new_y >= lvl_h_px - 14:
            self._damage_respawn()
            self._update_camera()
            return
        if self.vy >= 0:
            landed = False
            for ox in (3, 12):
                tt = self._tile_type_at_px(self.px + ox, new_y + 16)
                if tt == TILE_SOLID:
                    landed = True
                elif tt == TILE_ONEWAY:
                    tile_top = ((int(new_y + 16)) // 8) * 8
                    if int(self.py + 16) <= tile_top:
                        landed = True
            if landed:
                new_y = float((((int(new_y + 16)) // 8) * 8) - 16)
                self.vy = 0.0
                self.on_ground = True
        else:
            if self._tile_type_at_px(self.px + 3, new_y + 2) == TILE_SOLID or self._tile_type_at_px(self.px + 12, new_y + 2) == TILE_SOLID:
                new_y = self.py
                self.vy = 0.0
        self.py = new_y

        # Tile triggers: Coin, Hazard, Bounce, Goal
        for ox, oy in ((8, 8), (8, 13)):
            cx, cy = self.px + ox, self.py + oy
            tt = self._tile_type_at_px(cx, cy)
            if tt == TILE_COIN:
                tx, ty = int(cx) // 8, int(cy) // 8
                if 0 <= ty < lvl.height and 0 <= tx < lvl.width:
                    self.cells[ty][tx] = 0
                self.coins += 1
                self.score += 100
                self._emit_sfx(self._find_sfx("coin", 1))
            elif tt == TILE_HAZARD:
                self._damage_respawn()
                break
            elif tt == TILE_BOUNCE:
                self.vy = -4.25
                self.on_ground = False
                self._emit_sfx(self._find_sfx("jump", 0))
            elif tt == TILE_GOAL:
                self.won = True
                self._emit_sfx(self._find_sfx("clear", 5))
                break

        # Projectiles
        for pr in self.projs:
            if not pr.active:
                continue
            pr.x += pr.vx
            if pr.x < 0 or pr.x >= lvl_w_px or self._tile_type_at_px(pr.x + 8, pr.y + 8) == TILE_SOLID:
                pr.active = False

        # Enemies
        for en in self.enemies:
            if not en.active:
                continue
            if (self.frame & 1) == 0:
                en.x += en.direction * en.speed
                if en.x <= en.min_x:
                    en.x = en.min_x
                    en.direction = 1
                elif en.x >= en.max_x:
                    en.x = en.max_x
                    en.direction = -1
            # Projectile hit
            for pr in self.projs:
                if pr.active and abs(pr.x - en.x) <= 12 and abs(pr.y - en.y) <= 12:
                    pr.active = False
                    en.active = False
                    self.score += 200
                    self._emit_sfx(self._find_sfx("hurt", 4))
                    break
            if not en.active:
                continue
            # Player touch / melee
            reach = 20 if self.melee_timer > 0 else 12
            if abs(self.px - en.x) <= reach and abs(self.py - en.y) <= 12:
                if self.melee_timer > 0:
                    en.active = False
                    self.score += 200
                    self._emit_sfx(self._find_sfx("hurt", 4))
                else:
                    self._damage_respawn()

        # Animation state selection
        self.anim_timer += 1
        if self.anim_lock == 0:
            if self.project.physics_mode == "platformer" and not self.on_ground:
                self.anim_name = "jump"
            elif moved:
                self.anim_name = "walk"
            else:
                self.anim_name = "idle"

        self._update_camera()

    def _update_camera(self) -> None:
        prof = self.project.profile()
        vw, vh = int(prof["width"]), int(prof["height"])
        lvl_w_px = self.project.level.width * 8
        lvl_h_px = self.project.level.height * 8
        self.cam_x = int(max(0, min(max(0, lvl_w_px - vw), int(self.px) - vw // 2 + 8)))
        self.cam_y = int(max(0, min(max(0, lvl_h_px - vh), int(self.py) - vh // 2 + 8)))

    def render_rgb(self) -> np.ndarray:
        """Render exact hardware-resolution (H, W, 3) uint8 framebuffer."""
        prof = self.project.profile()
        vw, vh = int(prof["width"]), int(prof["height"])
        fb = np.empty((vh, vw, 3), dtype=np.uint8)
        bg_r, bg_g, bg_b = hex_to_rgb(self.project.bg_color_hex)
        fb[:, :, 0] = bg_r
        fb[:, :, 1] = bg_g
        fb[:, :, 2] = bg_b

        # Precompute palette RGB lookup tables
        pal_rgbs: List[np.ndarray] = []
        for pi in range(max(1, len(self.project.palettes))):
            cols = self.project.get_palette_colors(pi)
            arr = np.array([hex_to_rgb(c) for c in cols[:16]], dtype=np.uint8)
            pal_rgbs.append(arr)

        # Draw visible BG tiles
        lvl = self.project.level
        tx0 = max(0, self.cam_x // 8)
        tx1 = min(lvl.width, (self.cam_x + vw) // 8 + 1)
        ty0 = max(0, self.cam_y // 8)
        ty1 = min(lvl.height, (self.cam_y + vh) // 8 + 1)

        for ty in range(ty0, ty1):
            row = self.cells[ty]
            sy0 = ty * 8 - self.cam_y
            for tx in range(tx0, tx1):
                ti = row[tx]
                if ti <= 0 or ti >= len(self.project.tiles):
                    continue
                tile = self.project.tiles[ti]
                pal = pal_rgbs[tile.palette_index % len(pal_rgbs)]
                sx0 = tx * 8 - self.cam_x
                pix = np.array(tile.pixels, dtype=np.uint8)
                # Clip to screen
                y_start = max(0, -sy0)
                y_end = min(8, vh - sy0)
                x_start = max(0, -sx0)
                x_end = min(8, vw - sx0)
                if y_start >= y_end or x_start >= x_end:
                    continue
                sub = pix[y_start:y_end, x_start:x_end]
                mask = sub > 0
                if np.any(mask):
                    dst = fb[sy0 + y_start: sy0 + y_end, sx0 + x_start: sx0 + x_end]
                    dst[mask] = pal[sub[mask]]

        def blit_sprite(frame_grid: List[List[int]], sx: int, sy: int, pal_idx: int, hflip: bool = False) -> None:
            pal = pal_rgbs[pal_idx % len(pal_rgbs)]
            pix = np.array(frame_grid, dtype=np.uint8)
            if hflip:
                pix = pix[:, ::-1]
            sh, sw = pix.shape
            y0 = max(0, -sy)
            y1 = min(sh, vh - sy)
            x0 = max(0, -sx)
            x1 = min(sw, vw - sx)
            if y0 >= y1 or x0 >= x1:
                return
            sub = pix[y0:y1, x0:x1]
            mask = sub > 0
            if np.any(mask):
                dst = fb[sy + y0: sy + y1, sx + x0: sx + x1]
                dst[mask] = pal[sub[mask]]

        # Draw Enemies
        for en in self.enemies:
            if not en.active:
                continue
            sp_i = en.sprite_index if en.sprite_index < len(self.project.sprites) else 0
            if sp_i < len(self.project.sprites) and self.project.sprites[sp_i].frames:
                sp = self.project.sprites[sp_i]
                fidx = ((self.frame >> 4) % len(sp.frames))
                blit_sprite(sp.frames[fidx], int(en.x) - self.cam_x, int(en.y) - self.cam_y, sp.palette_index, en.direction < 0)

        # Draw Projectiles
        proj_sp = self.project.sprites[2] if len(self.project.sprites) > 2 else (self.project.sprites[0] if self.project.sprites else None)
        if proj_sp and proj_sp.frames:
            pf = proj_sp.frames[(self.frame >> 2) % len(proj_sp.frames)]
            for pr in self.projs:
                if pr.active:
                    blit_sprite(pf, int(pr.x) - self.cam_x, int(pr.y) - self.cam_y, proj_sp.palette_index, pr.vx < 0)

        # Draw Hero (blinks during invuln)
        if self.project.sprites and (self.invuln == 0 or (self.invuln & 4) == 0):
            hero = self.project.sprites[0]
            clip = hero.get_clip(self.anim_name)
            fids = clip.frame_indices or [0]
            ticks = max(2, int(round(60.0 / max(1, clip.fps))))
            f_pos = (self.anim_timer // ticks) % len(fids)
            fi = max(0, min(len(hero.frames) - 1, fids[f_pos]))
            blit_sprite(hero.frames[fi], int(self.px) - self.cam_x, int(self.py) - self.cam_y, self.palette_idx, self.facing == 1)

        return fb
