"""Live 60fps Hardware-Faithful Playtest Engine for KinoPixel v3.0.

Mirrors the exact compiled GBA ARM7TDMI v3.0 kernel 1:1 across all genres:
- 4 Physics Modes: Platformer (45° slopes, water swim, ladders, wall-jump),
  Top-Down 4-Way RPG, 8-Way Free-Flight Space Action, and Tactical Grid (16px tile-step)
- Up to 128 interconnected rooms, warp doors, switches, SRAM checkpoints & auto-minimap
- Conditional Variable/Flag Button Wiring (VAR[0..7], World Flags 0..31, var_delta)
- Multi-size metasprites (16x16, 16x32, 32x16, 32x32, 64x64) & Alt-Form hitbox swap
- Universal AI: Patrol, Chaser, Turret, Multi-Phase Boss (Phase 2 3-way spread + 2x speed),
  Sine-Wave Swooper, and Friendly NPCs with 2-page dialogue
- Super Burst (3-way heavy spread + camera screen shake + DMA), Heal, and BG2 Parallax
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, List, Optional, Set

import numpy as np

from .kinoscript import KinoScriptLiveRuntime
from .models import (
    ABIL_HIGH_JUMP,
    ABIL_MORPH_BALL,
    ABIL_WALL_JUMP,
    ACTION_AIM_UP,
    ACTION_BOMB,
    ACTION_DASH,
    ACTION_HEAL,
    ACTION_INTERACT,
    ACTION_JUMP,
    ACTION_MELEE,
    ACTION_MORPH_BALL,
    ACTION_MOVE_DOWN,
    ACTION_MOVE_LEFT,
    ACTION_MOVE_RIGHT,
    ACTION_MOVE_UP,
    ACTION_PALETTE_NEXT,
    ACTION_PAUSE,
    ACTION_PLAY_SFX,
    ACTION_RESET_LEVEL,
    ACTION_SHOOT,
    ACTION_SUPER_BURST,
    ACTION_SWITCH_ANIM,
    AI_BOSS,
    AI_CHASER,
    AI_NPC,
    AI_SINE,
    AI_TURRET,
    BUTTON_BITS,
    COND_ABIL_OWNED,
    COND_ALWAYS,
    COND_FLAG_SET,
    COND_VAR_POS,
    KinoPixelProject,
    TILE_BOUNCE,
    TILE_BREAKABLE,
    TILE_COIN,
    TILE_DOOR,
    TILE_GOAL,
    TILE_HAZARD,
    TILE_LADDER,
    TILE_ONEWAY,
    TILE_SAVE,
    TILE_SLOPE_L,
    TILE_SLOPE_R,
    TILE_SOLID,
    TILE_SWITCH,
    TILE_TERMINAL,
    TILE_UPGRADE,
    TILE_WATER,
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
    vy: float = 0.0
    heavy: bool = False
    is_enemy: bool = False


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
    ai_type: int = 0
    hp: int = 1
    phase2_hp: int = 6
    defeat_flag: int = 0
    is_32: bool = False


class GamePlaytestEngine:
    """Deterministic 60 FPS universal GBA/GBC/GB simulator matching the compiled .gba ROM kernel 1:1."""

    def __init__(
        self,
        project: KinoPixelProject,
        on_sfx: Optional[Callable[[int], None]] = None,
        on_dma: Optional[Callable[[], None]] = None,
    ) -> None:
        self.project = project
        self.on_sfx = on_sfx
        self.on_dma = on_dma
        self.room_idx: int = 0
        self.cells: List[List[int]] = []
        self.px: float = 0.0
        self.py: float = 0.0
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.facing: int = 0
        self.on_ground: bool = False
        self.in_water: bool = False
        self.on_ladder: bool = False
        self.palette_idx: int = 0
        self.anim_name: str = "idle"
        self.anim_timer: int = 0
        self.anim_lock: int = 0
        self.score: int = 0
        self.coins: int = 0
        self.hp: int = 5
        self.invuln: int = 0
        self.paused: bool = False
        self.won: bool = False
        self.cam_x: int = 0
        self.cam_y: int = 0
        self.frame: int = 0
        self.dash_timer: int = 0
        self.melee_timer: int = 0
        self.shoot_cd: int = 0
        self.tact_cd: int = 0
        self.shake_timer: int = 0
        self.abilities: int = 0
        self.world_flags: int = 0
        self.vars: List[int] = [10, 0, 0, 0, 0, 0, 0, 0]
        self.visited_rooms: Set[int] = set()
        self.morphed: bool = False
        self.aim_y: int = 0
        self.dialog_text: str = ""
        self.dialog_page: int = 0
        self.banner_msg: str = ""
        self.banner_timer: int = 0
        self.door_cd: int = 0
        self.term_cd: int = 0
        self.boss_hp: int = 0
        self.prev_keys: int = 0
        self.curr_keys: int = 0
        self.projs: List[_LiveProj] = []
        self.enemies: List[_LiveEnemy] = []
        self.ks_runtime: Optional[KinoScriptLiveRuntime] = None
        self.reset()

    def is_script_mode(self) -> bool:
        return bool(self.project.script_enabled and self.project.script_code.strip())

    def set_project(self, project: KinoPixelProject) -> None:
        self.project = project
        self.reset()

    def _active_room(self):
        rooms = self.project.rooms or [self.project.level]
        return rooms[max(0, min(len(rooms) - 1, self.room_idx))]

    def _hero_h(self) -> int:
        if self.morphed:
            return 16
        return self.project.sprites[0].height if self.project.sprites else 16

    def reset(self) -> None:
        self.score = 0
        self.coins = 0
        self.hp = 5
        self.invuln = 0
        self.paused = False
        self.won = False
        self.abilities = self.project.starting_abilities
        self.world_flags = 0
        sv = list(self.project.starting_vars or [10, 0, 0, 0, 0, 0, 0, 0])[:8]
        while len(sv) < 8:
            sv.append(0)
        self.vars = sv
        self.visited_rooms = set()
        self.morphed = False
        self.in_water = False
        self.on_ladder = False
        self.tact_cd = 0
        self.shake_timer = 0
        self.dialog_text = ""
        self.dialog_page = 0
        self.banner_msg = ""
        self.banner_timer = 0
        self.door_cd = 0
        self.term_cd = 0
        if self.is_script_mode():
            self.ks_runtime = KinoScriptLiveRuntime(
                self.project, self.project.script_code, on_sfx=self.on_sfx, on_dma=self.on_dma
            )
            if self.ks_runtime.error:
                self.banner_msg = f"SCRIPT ERR: {self.ks_runtime.error[:28]}"
            return
        self.ks_runtime = None
        self.load_room(0)

    def load_room(self, r_idx: int, tx: Optional[int] = None, ty: Optional[int] = None) -> None:
        rooms = self.project.rooms or [self.project.level]
        self.room_idx = max(0, min(len(rooms) - 1, r_idx))
        self.visited_rooms.add(self.room_idx)
        lvl = rooms[self.room_idx]
        self.cells = copy.deepcopy(lvl.cells)
        sx = lvl.spawn_x if tx is None else tx
        sy = lvl.spawn_y if ty is None else ty
        self.px = float(max(8, min((lvl.width - 2) * 8, sx * 8)))
        self.py = float(max(8, min((lvl.height - 2) * 8, sy * 8)))
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.projs = [_LiveProj() for _ in range(8)]
        self.enemies = []
        for e in lvl.entities[:16]:
            sp = self.project.sprites[e.sprite_index] if e.sprite_index < len(self.project.sprites) else None
            is_32 = bool((sp and sp.width >= 32) or e.ai_type == AI_BOSS)
            ex = float(max(8, min((lvl.width - (4 if is_32 else 2)) * 8, e.tile_x * 8)))
            ey = float(max(8, min((lvl.height - (4 if is_32 else 2)) * 8, e.tile_y * 8)))
            pr = max(1, e.patrol_range) * 8.0
            self.enemies.append(_LiveEnemy(
                active=True, x=ex, y=ey, min_x=max(8.0, ex - pr),
                max_x=min((lvl.width - (4 if is_32 else 2)) * 8.0, ex + pr),
                direction=1, speed=max(1, min(4, e.speed)),
                sprite_index=e.sprite_index, ai_type=e.ai_type,
                hp=max(1, e.hp), phase2_hp=max(0, e.phase2_hp),
                defeat_flag=max(0, min(31, e.defeat_flag)), is_32=is_32,
            ))
        self._update_camera()

    def _emit_sfx(self, idx: int) -> None:
        if self.on_sfx and 0 <= idx < len(self.project.sfx_list):
            self.on_sfx(idx)

    def _emit_dma(self) -> None:
        if self.on_dma and self.project.direct_sound.enabled:
            self.on_dma()

    def _find_sfx(self, keyword: str, fallback: int) -> int:
        for i, p in enumerate(self.project.sfx_list):
            if keyword in p.name.lower():
                return i
        return fallback if fallback < len(self.project.sfx_list) else -1

    def _tile_type_at_px(self, x: float, y: float) -> int:
        tx, ty = int(x) // 8, int(y) // 8
        lvl = self._active_room()
        if tx < 0 or tx >= lvl.width:
            return TILE_SOLID
        if ty < 0 or ty >= lvl.height:
            return 0
        ti = self.cells[ty][tx]
        return self.project.tiles[ti].tile_type if 0 <= ti < len(self.project.tiles) else 0

    def _is_solid_px(self, x: float, y: float) -> bool:
        return self._tile_type_at_px(x, y) in (TILE_SOLID, TILE_BREAKABLE)

    def _damage_respawn(self) -> None:
        if self.invuln > 0:
            return
        self._emit_sfx(self._find_sfx("hurt", 4))
        self.hp -= 1
        if self.hp <= 0:
            self.reset()
            return
        self.invuln = 45
        lvl = self._active_room()
        self.px = float(max(8, lvl.spawn_x * 8))
        self.py = float(max(8, lvl.spawn_y * 8))
        self.vx = self.vy = 0.0

    def _spawn_player_proj(self, speed: int, heavy: bool, force_vy: Optional[float] = None) -> None:
        spd = max(1, speed)
        for pr in self.projs[:4]:
            if not pr.active:
                pr.active = True
                pr.is_enemy = False
                pr.heavy = heavy
                pr.x = self.px + (-8 if self.facing else 8)
                pr.y = self.py + 4
                if force_vy is not None:
                    pr.vx = float(-spd if self.facing else spd)
                    pr.vy = float(force_vy)
                elif self.project.physics_mode == "shmup":
                    pr.vx = float(-spd if self.facing else spd)
                    pr.vy = 0.0
                elif self.aim_y != 0:
                    horiz = bool(self.curr_keys & (BUTTON_BITS["LEFT"] | BUTTON_BITS["RIGHT"]))
                    pr.vx = (-spd if self.facing else spd) if horiz else 0.0
                    pr.vy = float(spd * self.aim_y)
                else:
                    pr.vx = float(-spd if self.facing else spd)
                    pr.vy = 0.0
                return

    def _spawn_enemy_proj(self, x: float, y: float, vx: float, vy: float) -> None:
        for ep in self.projs[4:]:
            if not ep.active:
                ep.active = True
                ep.is_enemy = True
                ep.heavy = False
                ep.x = x
                ep.y = y
                ep.vx = vx
                ep.vy = vy
                return

    def _open_dialogue(self) -> None:
        lvl = self._active_room()
        self.dialog_page = 0
        self.dialog_text = lvl.dialogue_text
        self._emit_sfx(self._find_sfx("coin", 1))

    def step(self, pressed_buttons: Set[str]) -> None:
        if self.ks_runtime is not None:
            self.frame += 1
            self.ks_runtime.step(pressed_buttons)
            if self.ks_runtime.error:
                self.banner_msg = f"ERR: {self.ks_runtime.error[:32]}"
            return
        self.frame += 1
        self.prev_keys = self.curr_keys
        mask = 0
        for b in pressed_buttons:
            mask |= BUTTON_BITS.get(b.upper(), 0)
        self.curr_keys = mask
        just_pressed = self.curr_keys & ~self.prev_keys
        released = self.prev_keys & ~self.curr_keys

        # Multi-Page Dialogue Box: Page 0 -> Page 1 (if present) -> Close!
        if self.dialog_text:
            if just_pressed & (BUTTON_BITS["A"] | BUTTON_BITS["B"]):
                lvl = self._active_room()
                if self.dialog_page == 0 and lvl.dialogue_page2.strip():
                    self.dialog_page = 1
                    self.dialog_text = lvl.dialogue_page2.strip()
                else:
                    self.dialog_text = ""
                    self.dialog_page = 0
                    self.term_cd = 35
            return

        if self.won:
            if just_pressed & (BUTTON_BITS["START"] | BUTTON_BITS["A"]):
                self.reset()
            return

        for attr in ("invuln", "anim_lock", "dash_timer", "melee_timer", "shoot_cd",
                     "banner_timer", "door_cd", "term_cd", "tact_cd", "shake_timer"):
            v = getattr(self, attr)
            if v > 0:
                setattr(self, attr, v - 1)
        if self.banner_timer == 0:
            self.banner_msg = ""

        moved = False
        self.aim_y = -1 if (self.curr_keys & BUTTON_BITS["UP"]) else 0
        if self.dash_timer == 0:
            self.vx = 0.0
            if self.project.physics_mode != "platformer" or self.on_ladder:
                self.vy = 0.0

        # Evaluate Conditional Button Wiring Rules
        for rule in self.project.button_rules:
            if not rule.enabled:
                continue
            rmask = BUTTON_BITS.get(rule.button.upper(), 0)
            if not rmask:
                continue
            src = self.curr_keys if rule.trigger == TRIGGER_HELD else (just_pressed if rule.trigger == TRIGGER_PRESSED else released)
            if not (src & rmask):
                continue
            if self.paused and rule.action not in (ACTION_PAUSE, ACTION_RESET_LEVEL):
                continue

            # Conditional Gate Check
            if rule.cond_type == COND_VAR_POS:
                if self.vars[rule.cond_idx & 7] <= 0:
                    continue
            elif rule.cond_type == COND_FLAG_SET:
                if not (self.world_flags & (1 << (rule.cond_idx & 31))):
                    continue
            elif rule.cond_type == COND_ABIL_OWNED:
                if not (self.abilities & rule.cond_idx):
                    continue

            triggered = True
            pmode = self.project.physics_mode
            if rule.action == ACTION_MOVE_LEFT:
                if pmode == "tactical":
                    if self.tact_cd > 0:
                        triggered = False
                    else:
                        self.tact_cd = 10; self.vx = -16.0; self.facing = 1; moved = True
                else:
                    self.vx = -rule.param * 0.5; self.facing = 1; moved = True
            elif rule.action == ACTION_MOVE_RIGHT:
                if pmode == "tactical":
                    if self.tact_cd > 0:
                        triggered = False
                    else:
                        self.tact_cd = 10; self.vx = 16.0; self.facing = 0; moved = True
                else:
                    self.vx = rule.param * 0.5; self.facing = 0; moved = True
            elif rule.action == ACTION_MOVE_UP:
                if pmode == "tactical":
                    if self.tact_cd > 0:
                        triggered = False
                    else:
                        self.tact_cd = 10; self.vy = -16.0; moved = True
                elif pmode != "platformer" or self.on_ladder:
                    self.vy = -rule.param * 0.5; moved = True
                else:
                    self.aim_y = -1
            elif rule.action == ACTION_MOVE_DOWN:
                if pmode == "tactical":
                    if self.tact_cd > 0:
                        triggered = False
                    else:
                        self.tact_cd = 10; self.vy = 16.0; moved = True
                elif pmode != "platformer" or self.on_ladder:
                    self.vy = rule.param * 0.5; moved = True
                else:
                    self.aim_y = 1
            elif rule.action == ACTION_AIM_UP:
                self.aim_y = -1
            elif rule.action == ACTION_JUMP:
                bonus = 0.75 if (self.abilities & ABIL_HIGH_JUMP) else 0.0
                scale = 0.5 if self.in_water else 1.0
                if self.on_ground or self.in_water or self.on_ladder:
                    self.vy = -(rule.param * 0.5 + 0.75 + bonus) * scale
                    self.on_ground = False
                elif self.abilities & ABIL_WALL_JUMP:
                    if self._is_solid_px(self.px - 2, self.py + 8):
                        self.vx = 2.0; self.facing = 0; self.dash_timer = 7
                        self.vy = -(rule.param * 0.5 + 0.75 + bonus)
                    elif self._is_solid_px(self.px + 17, self.py + 8):
                        self.vx = -2.0; self.facing = 1; self.dash_timer = 7
                        self.vy = -(rule.param * 0.5 + 0.75 + bonus)
                    else:
                        triggered = False
                else:
                    triggered = False
            elif rule.action == ACTION_DASH:
                spd = rule.param * 0.5 + 0.5
                self.vx = -spd if self.facing else spd
                self.dash_timer = 10
            elif rule.action == ACTION_SHOOT:
                if self.shoot_cd == 0:
                    self.shoot_cd = 10
                    self._spawn_player_proj(rule.param, heavy=False)
                else:
                    triggered = False
            elif rule.action == ACTION_BOMB:
                if self.shoot_cd == 0:
                    self.shoot_cd = 14
                    self._spawn_player_proj(rule.param, heavy=True)
                else:
                    triggered = False
            elif rule.action == ACTION_SUPER_BURST:
                if self.shoot_cd == 0:
                    self.shoot_cd = 18
                    self.shake_timer = 12
                    spd = max(1, rule.param)
                    self._spawn_player_proj(spd, heavy=True, force_vy=0.0)
                    self._spawn_player_proj(spd, heavy=True, force_vy=-spd * 0.5)
                    self._spawn_player_proj(spd, heavy=True, force_vy=spd * 0.5)
                    self._emit_dma()
                else:
                    triggered = False
            elif rule.action == ACTION_HEAL:
                if self.hp < 5:
                    self.hp += 1
                else:
                    triggered = False
            elif rule.action == ACTION_MELEE:
                self.melee_timer = 14
            elif rule.action == ACTION_MORPH_BALL:
                if self.abilities & ABIL_MORPH_BALL:
                    base_h = self.project.sprites[0].height if self.project.sprites else 16
                    if not self.morphed:
                        self.morphed = True
                        self.py += max(0, base_h - 16)
                    else:
                        if base_h <= 16 or not self._is_solid_px(self.px + 8, self.py - 14):
                            self.morphed = False
                            self.py = max(0.0, self.py - max(0, base_h - 16))
                        else:
                            triggered = False
                else:
                    triggered = False
            elif rule.action == ACTION_INTERACT:
                self.term_cd = 0
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
                if rule.var_delta != 0:
                    vi = rule.cond_idx & 7
                    self.vars[vi] = max(0, self.vars[vi] + rule.var_delta)
                if rule.anim_name and rule.trigger == TRIGGER_PRESSED:
                    self.anim_name = rule.anim_name
                    self.anim_lock = 14
                if rule.sfx_index >= 0:
                    self._emit_sfx(rule.sfx_index)

        if self.paused:
            return

        lvl = self._active_room()
        lvl_w_px, lvl_h_px = lvl.width * 8, lvl.height * 8
        hh = self._hero_h()

        # Probe Water & Ladder overlap at hero center
        center_tt = self._tile_type_at_px(self.px + 8, self.py + hh / 2.0)
        self.in_water = center_tt == TILE_WATER
        self.on_ladder = center_tt == TILE_LADDER

        if self.project.physics_mode == "platformer" and not self.on_ladder:
            g = (self.project.gravity / 256.0) * (0.5 if self.in_water else 1.0)
            mf = (self.project.max_fall_speed / 256.0) * (0.5 if self.in_water else 1.0)
            self.vy = min(mf, self.vy + g)

        # Horizontal move
        new_x = max(0.0, min(lvl_w_px - 16.0, self.px + self.vx))
        if self.vx > 0:
            if any(self._is_solid_px(new_x + 13, self.py + oy) for oy in (2, hh // 2, hh - 3)):
                new_x = self.px; self.vx = 0.0
        elif self.vx < 0:
            if any(self._is_solid_px(new_x + 2, self.py + oy) for oy in (2, hh // 2, hh - 3)):
                new_x = self.px; self.vx = 0.0
        self.px = new_x

        # Vertical move + 45° Slope Snapping
        self.on_ground = False
        new_y = max(0.0, self.py + self.vy)
        if new_y >= lvl_h_px - hh + 2:
            if self.project.physics_mode == "platformer":
                self._damage_respawn(); self._update_camera(); return
            new_y = float(lvl_h_px - hh)
        if self.vy >= 0:
            slope_hit = False
            st = self._tile_type_at_px(self.px + 8, new_y + hh - 1)
            if st in (TILE_SLOPE_L, TILE_SLOPE_R):
                rx = int(self.px + 8) & 7
                tile_top = ((int(new_y + hh - 1)) // 8) * 8
                floor_y = tile_top + ((7 - rx) if st == TILE_SLOPE_L else rx)
                if new_y + hh >= floor_y:
                    new_y = float(floor_y - hh)
                    self.vy = 0.0
                    self.on_ground = True
                    slope_hit = True
            if not slope_hit:
                landed = False
                for ox in (3, 12):
                    tt = self._tile_type_at_px(self.px + ox, new_y + hh)
                    if tt in (TILE_SOLID, TILE_BREAKABLE):
                        landed = True
                    elif tt == TILE_ONEWAY:
                        tile_top = ((int(new_y + hh)) // 8) * 8
                        if int(self.py + hh) <= tile_top:
                            landed = True
                if landed:
                    new_y = float((((int(new_y + hh)) // 8) * 8) - hh)
                    self.vy = 0.0
                    self.on_ground = True
        else:
            if self._is_solid_px(self.px + 3, new_y + 2) or self._is_solid_px(self.px + 12, new_y + 2):
                new_y = self.py; self.vy = 0.0
        self.py = new_y

        # Tile Triggers
        for oy in (8, hh - 3):
            cx, cy = self.px + 8, self.py + oy
            tt = self._tile_type_at_px(cx, cy)
            tx, ty = int(cx) // 8, int(cy) // 8
            if tt == TILE_COIN:
                self.cells[ty][tx] = 0; self.coins += 1; self.score += 100
                self._emit_sfx(self._find_sfx("coin", 1))
            elif tt == TILE_HAZARD:
                self._damage_respawn(); break
            elif tt == TILE_BOUNCE:
                self.vy = -4.25; self.on_ground = False; self._emit_sfx(self._find_sfx("jump", 0))
            elif tt == TILE_GOAL:
                self.won = True; self._emit_sfx(self._find_sfx("clear", 5)); self._emit_dma(); break
            elif tt == TILE_UPGRADE:
                self.cells[ty][tx] = 0
                self.abilities |= lvl.upgrade_ability
                self.vars[0] += 5
                self.banner_msg = "SKILL UNLOCKED!"; self.banner_timer = 75
                self._emit_sfx(self._find_sfx("clear", 5)); self._emit_dma()
            elif tt == TILE_SWITCH:
                bit = 1 << (lvl.switch_flag & 31)
                if not (self.world_flags & bit):
                    self.world_flags |= bit
                    self.banner_msg = "SWITCH TRIGGERED!"; self.banner_timer = 70
                    self._emit_sfx(self._find_sfx("coin", 1))
            elif tt == TILE_SAVE and self.banner_timer == 0:
                self.hp = 5
                self.banner_msg = "SRAM SAVED!"; self.banner_timer = 75
                self._emit_sfx(self._find_sfx("coin", 1))
            elif tt == TILE_TERMINAL and self.term_cd == 0:
                self._open_dialogue(); break
            elif tt == TILE_DOOR and self.door_cd == 0:
                dr = lvl.find_door_near(tx, ty)
                if dr:
                    if dr.req_ability and not (self.abilities & dr.req_ability):
                        self.banner_msg = "LOCKED!"; self.banner_timer = 45; self.door_cd = 30
                        self._emit_sfx(self._find_sfx("hurt", 4))
                    else:
                        self.door_cd = 35
                        self.load_room(dr.target_room, dr.target_x, dr.target_y)
                break

        # Projectiles + Destructible Blocks
        for pr in self.projs:
            if not pr.active:
                continue
            pr.x += pr.vx; pr.y += pr.vy
            if pr.x < 0 or pr.x >= lvl_w_px or pr.y < 0 or pr.y >= lvl_h_px:
                pr.active = False; continue
            if pr.is_enemy and abs(pr.x - self.px) <= 10 and abs(pr.y - self.py) <= hh // 2 + 8:
                pr.active = False; self._damage_respawn(); continue
            tt = self._tile_type_at_px(pr.x + 8, pr.y + 8)
            if tt == TILE_BREAKABLE:
                bx, by = int(pr.x + 8) // 8, int(pr.y + 8) // 8
                if 0 <= by < lvl.height and 0 <= bx < lvl.width:
                    self.cells[by][bx] = 0
                pr.active = False; self._emit_sfx(self._find_sfx("hurt", 4))
            elif tt == TILE_SOLID:
                pr.active = False

        # Enemies, Friendly NPCs & Multi-Phase Bosses
        self.boss_hp = 0
        for en in self.enemies:
            if not en.active:
                continue
            if en.ai_type == AI_NPC:
                if abs(self.px - en.x) <= 14 and abs(self.py - en.y) <= 16 and self.term_cd == 0:
                    self._open_dialogue()
                continue
            if en.ai_type == AI_BOSS:
                self.boss_hp = en.hp
            if (self.frame & 1) == 0:
                if en.ai_type == AI_CHASER:
                    if en.x < self.px:
                        en.x += en.speed; en.direction = 1
                    elif en.x > self.px:
                        en.x -= en.speed; en.direction = -1
                elif en.ai_type == AI_TURRET:
                    if (self.frame & 63) == 0:
                        self._spawn_enemy_proj(en.x, en.y, 2.0 if self.px >= en.x else -2.0, 0.0)
                else:
                    if en.ai_type == AI_SINE:
                        en.y += 1.0 if (self.frame & 32) == 0 else -1.0
                    spd = en.speed * (2 if (en.ai_type == AI_BOSS and en.hp <= en.phase2_hp) else 1)
                    en.x += en.direction * spd
                    if en.x <= en.min_x:
                        en.x = en.min_x; en.direction = 1
                    elif en.x >= en.max_x:
                        en.x = en.max_x; en.direction = -1
                    if en.ai_type == AI_BOSS and (self.frame & 63) == 32:
                        vx = 3.0 if self.px >= en.x else -3.0
                        self._spawn_enemy_proj(en.x + 8, en.y + 12, vx, 0.0)
                        if en.hp <= en.phase2_hp:
                            self._spawn_enemy_proj(en.x + 8, en.y + 12, vx, -1.0)
                            self._spawn_enemy_proj(en.x + 8, en.y + 12, vx, 1.0)

            rad = 22 if en.is_32 else 12
            for pr in self.projs[:4]:
                if pr.active and abs(pr.x - en.x) <= rad and abs(pr.y - en.y) <= rad:
                    dmg = 3 if pr.heavy else 1
                    pr.active = False
                    en.hp -= dmg
                    if en.hp <= 0:
                        en.active = False; self.score += 200
                        if en.defeat_flag > 0:
                            self.world_flags |= 1 << (en.defeat_flag & 31)
                        if en.ai_type == AI_BOSS:
                            self.won = True; self.shake_timer = 16; self._emit_dma(); self._emit_sfx(self._find_sfx("clear", 5))
                        else:
                            self._emit_sfx(self._find_sfx("hurt", 4))
                    else:
                        self._emit_sfx(self._find_sfx("hurt", 4))
                    break
            if not en.active:
                continue
            if abs(self.px - en.x) <= rad and abs(self.py - en.y) <= rad:
                if self.melee_timer > 0:
                    en.active = False; self.score += 200; self._emit_sfx(self._find_sfx("hurt", 4))
                else:
                    self._damage_respawn()

        self.anim_timer += 1
        if self.anim_lock == 0:
            if self.project.physics_mode == "platformer" and not self.on_ground and not self.on_ladder:
                self.anim_name = "jump"
            elif moved:
                self.anim_name = "walk"
            else:
                self.anim_name = "idle"
        self._update_camera()

    def _update_camera(self) -> None:
        prof = self.project.profile()
        vw, vh = int(prof["width"]), int(prof["height"])
        lvl = self._active_room()
        cx = int(max(0, min(max(0, lvl.width * 8 - vw), int(self.px) - vw // 2 + 8)))
        cy = int(max(0, min(max(0, lvl.height * 8 - vh), int(self.py) - vh // 2 + 8)))
        if self.shake_timer > 0:
            cx = max(0, cx + (2 if (self.shake_timer & 1) else -2))
            cy = max(0, cy + (2 if (self.shake_timer & 2) else -2))
        self.cam_x = cx
        self.cam_y = cy

    def render_rgb(self) -> np.ndarray:
        if self.ks_runtime is not None:
            return self._render_kinoscript_rgb()
        prof = self.project.profile()
        vw, vh = int(prof["width"]), int(prof["height"])
        fb = np.empty((vh, vw, 3), dtype=np.uint8)
        bg_r, bg_g, bg_b = hex_to_rgb(self.project.bg_color_hex)
        fb[:, :, 0] = bg_r; fb[:, :, 1] = bg_g; fb[:, :, 2] = bg_b

        pal_rgbs = [np.array([hex_to_rgb(c) for c in self.project.get_palette_colors(pi)[:16]], dtype=np.uint8)
                    for pi in range(max(1, len(self.project.palettes)))]
        lvl = self._active_room()

        # BG2 1/2-speed Parallax Backdrop (with optional hardware alpha blend!)
        if lvl.parallax_enabled and 0 < lvl.parallax_tile_idx < len(self.project.tiles):
            pt = self.project.tiles[lvl.parallax_tile_idx]
            ppal = pal_rgbs[pt.palette_index % len(pal_rgbs)]
            ppix = np.array(pt.pixels, dtype=np.uint8)
            px_off = (self.cam_x // 2) % 32
            py_off = (self.cam_y // 2) % 32
            for sy in range(-py_off, vh, 32):
                for sx in range(-px_off, vw, 32):
                    y0, y1 = max(0, -sy), min(8, vh - sy)
                    x0, x1 = max(0, -sx), min(8, vw - sx)
                    if y0 < y1 and x0 < x1:
                        sub = ppix[y0:y1, x0:x1]
                        m = sub > 0
                        if np.any(m):
                            dst = fb[sy + y0: sy + y1, sx + x0: sx + x1]
                            if self.project.alpha_blend_enabled:
                                dst[m] = ((dst[m].astype(np.uint16) + ppal[sub[m]].astype(np.uint16)) // 2).astype(np.uint8)
                            else:
                                dst[m] = ppal[sub[m]]

        # BG0 Visible Tiles
        tx0, tx1 = max(0, self.cam_x // 8), min(lvl.width, (self.cam_x + vw) // 8 + 1)
        ty0, ty1 = max(0, self.cam_y // 8), min(lvl.height, (self.cam_y + vh) // 8 + 1)
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
                y0, y1 = max(0, -sy0), min(8, vh - sy0)
                x0, x1 = max(0, -sx0), min(8, vw - sx0)
                if y0 < y1 and x0 < x1:
                    sub = pix[y0:y1, x0:x1]
                    m = sub > 0
                    if np.any(m):
                        fb[sy0 + y0: sy0 + y1, sx0 + x0: sx0 + x1][m] = pal[sub[m]]

        def blit_sprite(frame_grid, sx: int, sy: int, pal_idx: int, hflip: bool = False) -> None:
            pal = pal_rgbs[pal_idx % len(pal_rgbs)]
            pix = np.array(frame_grid, dtype=np.uint8)
            if hflip:
                pix = pix[:, ::-1]
            sh, sw = pix.shape
            y0, y1 = max(0, -sy), min(sh, vh - sy)
            x0, x1 = max(0, -sx), min(sw, vw - sx)
            if y0 < y1 and x0 < x1:
                sub = pix[y0:y1, x0:x1]
                m = sub > 0
                if np.any(m):
                    fb[sy + y0: sy + y1, sx + x0: sx + x1][m] = pal[sub[m]]

        for en in self.enemies:
            if not en.active:
                continue
            sp = self.project.sprites[en.sprite_index] if en.sprite_index < len(self.project.sprites) else self.project.sprites[0]
            if sp.frames:
                blit_sprite(sp.frames[(self.frame >> 4) % len(sp.frames)], int(en.x) - self.cam_x, int(en.y) - self.cam_y, sp.palette_index, en.direction < 0)

        proj_sp = next((s for s in self.project.sprites if s.role == "projectile"), self.project.sprites[0] if self.project.sprites else None)
        if proj_sp and proj_sp.frames:
            pf = proj_sp.frames[(self.frame >> 2) % len(proj_sp.frames)]
            for pr in self.projs:
                if pr.active:
                    blit_sprite(pf, int(pr.x) - self.cam_x, int(pr.y) - self.cam_y, proj_sp.palette_index, pr.vx < 0)

        if self.project.sprites and (self.invuln == 0 or (self.invuln & 4) == 0):
            if self.morphed:
                mi = self.project.morph_sprite_index
                msp = self.project.sprites[mi] if 0 <= mi < len(self.project.sprites) else self.project.sprites[0]
                fr = msp.frames[(self.frame >> 2) % len(msp.frames)]
                blit_sprite(fr, int(self.px) - self.cam_x, int(self.py) - self.cam_y, self.palette_idx, False)
            else:
                hero = self.project.sprites[0]
                clip = hero.get_clip(self.anim_name)
                fids = clip.frame_indices or [0]
                ticks = max(2, int(round(60.0 / max(1, clip.fps))))
                fi = max(0, min(len(hero.frames) - 1, fids[(self.anim_timer // ticks) % len(fids)]))
                blit_sprite(hero.frames[fi], int(self.px) - self.cam_x, int(self.py) - self.cam_y, self.palette_idx, self.facing == 1)

        return fb

    def _render_kinoscript_rgb(self) -> np.ndarray:
        """Render BG2 + BG0 + 128 OAM Sprites + BG1 Hardware Font/UI Layer for KinoScript mode."""
        from .gba_compiler import FONT_ORDER, _FONT_BITMAPS
        ks = self.ks_runtime
        assert ks is not None
        prof = self.project.profile()
        vw, vh = int(prof["width"]), int(prof["height"])
        fb = np.empty((vh, vw, 3), dtype=np.uint8)
        bg_r, bg_g, bg_b = hex_to_rgb(self.project.bg_color_hex)
        fb[:, :, 0] = bg_r; fb[:, :, 1] = bg_g; fb[:, :, 2] = bg_b

        pal_rgbs = [np.array([hex_to_rgb(c) for c in self.project.get_palette_colors(pi)[:16]], dtype=np.uint8)
                    for pi in range(max(1, len(self.project.palettes)))]
        hud_pal = np.array([
            (0, 0, 0), hex_to_rgb("#0D1322"), hex_to_rgb("#F8FAFC"), hex_to_rgb("#FDE047"),
            hex_to_rgb("#F43F5E"), hex_to_rgb("#161A26"), hex_to_rgb("#34D399"),
        ], dtype=np.uint8)

        # BG0 Room Tilemap with bg_scroll[0]
        sx_bg0, sy_bg0 = ks.bg_scroll[0]
        rows = ks.cells
        rh = len(rows)
        rw = len(rows[0]) if rh else 0
        tx0, tx1 = max(0, sx_bg0 // 8), min(rw, (sx_bg0 + vw) // 8 + 1)
        ty0, ty1 = max(0, sy_bg0 // 8), min(rh, (sy_bg0 + vh) // 8 + 1)
        for ty in range(ty0, ty1):
            row = rows[ty]
            sy0 = ty * 8 - sy_bg0
            for tx in range(tx0, tx1):
                ti = row[tx]
                if ti <= 0 or ti >= len(self.project.tiles):
                    continue
                tile = self.project.tiles[ti]
                pal = pal_rgbs[tile.palette_index % len(pal_rgbs)]
                sx0 = tx * 8 - sx_bg0
                pix = np.array(tile.pixels, dtype=np.uint8)
                y0, y1 = max(0, -sy0), min(8, vh - sy0)
                x0, x1 = max(0, -sx0), min(8, vw - sx0)
                if y0 < y1 and x0 < x1:
                    sub = pix[y0:y1, x0:x1]
                    m = sub > 0
                    if np.any(m):
                        fb[sy0 + y0: sy0 + y1, sx0 + x0: sx0 + x1][m] = pal[sub[m]]

        # 128 OAM Sprites (render slot 127..0 so slot 0 has highest priority!)
        for slot in range(127, -1, -1):
            ent = ks.oam[slot]
            if ent is None:
                continue
            sx, sy, sp_idx, fr_idx, pal_idx, hflip = ent
            if not (0 <= sp_idx < len(self.project.sprites)):
                continue
            sp = self.project.sprites[sp_idx]
            if not sp.frames:
                continue
            pix = np.array(sp.frames[fr_idx % len(sp.frames)], dtype=np.uint8)
            if hflip:
                pix = pix[:, ::-1]
            pal = pal_rgbs[pal_idx % len(pal_rgbs)]
            sh, sw = pix.shape
            y0, y1 = max(0, -sy), min(sh, vh - sy)
            x0, x1 = max(0, -sx), min(sw, vw - sx)
            if y0 < y1 and x0 < x1:
                sub = pix[y0:y1, x0:x1]
                m = sub > 0
                if np.any(m):
                    fb[sy + y0: sy + y1, sx + x0: sx + x1][m] = pal[sub[m]]

        # BG1 Crisp Font / UI Box / Highlight Layer (exact parity with GBA BG1 VRAM!)
        for ty in range(min(20, vh // 8)):
            for tx in range(min(30, vw // 8)):
                tid, pslot = ks.ui_tiles[ty][tx]
                if tid <= 0 or tid >= len(FONT_ORDER):
                    continue
                key = FONT_ORDER[tid]
                bmp = _FONT_BITMAPS[key]
                c_idx = 2
                if key == "HEART": c_idx = 4
                elif key == "COIN": c_idx = 3
                elif key == "BEZEL": c_idx = 5
                elif key == "BOX": c_idx = 1
                elif key == "BAR": c_idx = 6
                col = hud_pal[c_idx]
                sy0, sx0 = ty * 8, tx * 8
                for py in range(8):
                    brow = bmp[py]
                    for px in range(8):
                        if brow[px] == "#":
                            fb[sy0 + py, sx0 + px] = col
        return fb
