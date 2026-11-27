"""Core data models for KinoPixel v2.0 (.kpx projects, multi-room worlds, metasprites,
doors, SRAM saves, abilities, bosses, visual button wiring, PSG SFX, Direct Sound PCM & Sequence Genie)."""
from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .sequence_genie import SequenceGenieData

# ---------------------------------------------------------------------------
# Hardware Target Specifications (GB DMG / GBC / GBA)
# ---------------------------------------------------------------------------
HARDWARE_PROFILES: Dict[str, Dict[str, Any]] = {
    "GBA": {
        "name": "Game Boy Advance (GBA)",
        "width": 240,
        "height": 160,
        "colors_per_palette": 16,
        "max_bg_tiles": 512,
        "max_obj_tiles": 1024,
        "max_sprites": 128,
        "buttons": ["LEFT", "RIGHT", "UP", "DOWN", "A", "B", "L", "R", "START", "SELECT"],
        "color_depth": "15-bit BGR555 (4bpp, 16 colors/palette)",
    },
    "GBC": {
        "name": "Game Boy Color (GBC)",
        "width": 160,
        "height": 144,
        "colors_per_palette": 4,
        "max_bg_tiles": 384,
        "max_obj_tiles": 256,
        "max_sprites": 40,
        "buttons": ["LEFT", "RIGHT", "UP", "DOWN", "A", "B", "START", "SELECT"],
        "color_depth": "15-bit RGB555 (2bpp, 4 colors/palette)",
    },
    "GB": {
        "name": "Game Boy Classic (DMG)",
        "width": 160,
        "height": 144,
        "colors_per_palette": 4,
        "max_bg_tiles": 256,
        "max_obj_tiles": 128,
        "max_sprites": 40,
        "buttons": ["LEFT", "RIGHT", "UP", "DOWN", "A", "B", "START", "SELECT"],
        "color_depth": "2-bit 4-Shade Olive LCD",
    },
}

# Hardware button bitmasks matching GBA REG_KEYINPUT (~key & 0x03FF)
BUTTON_BITS: Dict[str, int] = {
    "A": 0x0001,
    "B": 0x0002,
    "SELECT": 0x0004,
    "START": 0x0008,
    "RIGHT": 0x0010,
    "LEFT": 0x0020,
    "UP": 0x0040,
    "DOWN": 0x0080,
    "R": 0x0100,
    "L": 0x0200,
}

BUTTON_ORDER: List[str] = ["LEFT", "RIGHT", "UP", "DOWN", "A", "B", "L", "R", "START", "SELECT"]

# Tile collision & behavior types (compiled 1:1 into ARM7TDMI ROM!)
TILE_EMPTY = 0
TILE_SOLID = 1
TILE_ONEWAY = 2
TILE_HAZARD = 3
TILE_COIN = 4
TILE_GOAL = 5
TILE_BOUNCE = 6
TILE_BREAKABLE = 7
TILE_DOOR = 8
TILE_SAVE = 9
TILE_UPGRADE = 10
TILE_TERMINAL = 11
TILE_SLOPE_L = 12     # 45-degree Up-Right Slope (/)
TILE_SLOPE_R = 13     # 45-degree Down-Right Slope (\)
TILE_WATER = 14       # Water / Low-Gravity Swim Zone
TILE_LADDER = 15      # Climbable Ladder / Vine
TILE_SWITCH = 16      # Trigger Switch (Sets World Flag!)

TILE_TYPE_NAMES: Dict[int, str] = {
    TILE_EMPTY: "Empty / Passable",
    TILE_SOLID: "Solid Wall / Ground",
    TILE_ONEWAY: "One-Way Platform",
    TILE_HAZARD: "Hazard / Damage",
    TILE_COIN: "Collectible / Pickup",
    TILE_GOAL: "Stage Goal / Objective",
    TILE_BOUNCE: "Spring / Boost Pad",
    TILE_BREAKABLE: "Destructible Block",
    TILE_DOOR: "Map Warp / Door / Portal",
    TILE_SAVE: "Checkpoint / SRAM Save",
    TILE_UPGRADE: "Key / Skill Unlock",
    TILE_TERMINAL: "Dialogue Trigger / Sign",
    TILE_SLOPE_L: "45° Slope Up-Right (/)",
    TILE_SLOPE_R: "45° Slope Down-Right (\\)",
    TILE_WATER: "Water / Low-Gravity Zone",
    TILE_LADDER: "Climbable Ladder / Vine",
    TILE_SWITCH: "World Switch (Sets Flag)",
}

TILE_TYPE_COLORS: Dict[int, str] = {
    TILE_EMPTY: "#00000000",
    TILE_SOLID: "#38BDF855",
    TILE_ONEWAY: "#34D39955",
    TILE_HAZARD: "#F43F5E88",
    TILE_COIN: "#F59E0B77",
    TILE_GOAL: "#A78BFA99",
    TILE_BOUNCE: "#EC489988",
    TILE_BREAKABLE: "#FB923C88",
    TILE_DOOR: "#22D3EE99",
    TILE_SAVE: "#10B98199",
    TILE_UPGRADE: "#FDE04799",
    TILE_TERMINAL: "#818CF899",
    TILE_SLOPE_L: "#60A5FA77",
    TILE_SLOPE_R: "#60A5FA77",
    TILE_WATER: "#0EA5E966",
    TILE_LADDER: "#D9770677",
    TILE_SWITCH: "#E879F988",
}

# Universal Game Genre / Physics Modes (compiled 1:1 into GBA ROM!)
PHYSICS_MODES: Dict[str, int] = {
    "platformer": 0,   # Side-view gravity, slopes, water swim, ladders, wall-jump
    "topdown": 1,      # 4-way Zelda / Pokémon Adventure RPG
    "shmup": 2,        # 8-way Space Shooter / Gradius free-flight
    "tactical": 3,     # Tile-snapped Turn-Based / Grid Tactics
}

# Universal Entity / Boss AI Archetypes & Attack Patterns (compiled into Behavior VM!)
AI_PATROL = 0
AI_CHASER = 1   # Stalker / Chaser pursues player X & Y!
AI_TURRET = 2   # Fires plasma shots at player!
AI_BOSS = 3     # 32x32 Multi-Phase Boss (switches to Phase 2 Spread/Dash under 50% HP!)
AI_SINE = 4     # Sine-wave Hover / Medusa Head / Shmup Squadron!
AI_NPC = 5      # Friendly RPG NPC (non-hostile, triggers Dialogue on contact/interact!)

AI_TYPE_NAMES: Dict[int, str] = {
    AI_PATROL: "Patrol (Walks L/R)",
    AI_CHASER: "Stalker / Chaser (Pursues Hero)",
    AI_TURRET: "Plasma Turret (Aimed Shots)",
    AI_BOSS: "32×32 Multi-Phase Boss (Spread + Leap)",
    AI_SINE: "Sine Hover / Swooper (Medusa / Shmup)",
    AI_NPC: "Friendly NPC (Triggers Dialogue)",
}

# Universal Button Rule Condition Types (compiled into GBA ROM!)
COND_ALWAYS = 0
COND_VAR_POS = 1      # Only triggers if VAR[cond_idx] > 0 (e.g., Missiles > 0, MP > 0!)
COND_FLAG_SET = 2     # Only triggers if World Flag[cond_idx] is set!
COND_ABIL_OWNED = 3   # Only triggers if Ability bitmask is unlocked!

COND_NAMES: Dict[int, str] = {
    COND_ALWAYS: "Always",
    COND_VAR_POS: "If Var > 0 (Ammo/MP)",
    COND_FLAG_SET: "If World Flag Set",
    COND_ABIL_OWNED: "If Ability Unlocked",
}

# Universal Unlockable Capability / Key Bitmasks (compiled 1:1 into GBA IWRAM ST_ABILITIES!)
ABIL_NONE = 0x00
ABIL_MORPH_BALL = 0x01  # Alias for Alt Form / Compact Hitbox
ABIL_MISSILES = 0x02    # Alias for Key / Heavy Skill Flag 2
ABIL_HIGH_JUMP = 0x04   # Alias for High Boost Flag 3
ABIL_WALL_JUMP = 0x08   # Alias for Wall Grip Flag 4
ABIL_SPEED_DASH = 0x10  # Alias for Dash Boost Flag 5

ABILITY_NAMES: Dict[int, str] = {
    ABIL_NONE: "None (Always Open)",
    ABIL_MORPH_BALL: "Skill 1 — Alt Form / Compact Hitbox",
    ABIL_MISSILES: "Skill 2 — Heavy Weapon / Key",
    ABIL_HIGH_JUMP: "Skill 3 — High Jump / Boost",
    ABIL_WALL_JUMP: "Skill 4 — Wall-Jump Grip",
    ABIL_SPEED_DASH: "Skill 5 — Dash / Speed Boost",
}

# Supported GBA hardware metasprite sizes (Square, Tall, Wide, Giant Boss!)
SPRITE_SIZES: List[Tuple[int, int]] = [(16, 16), (16, 32), (32, 16), (32, 32), (64, 64)]

# Button wiring triggers & actions (numeric codes compile 1:1 into GBA ROM!)
TRIGGER_HELD = 0
TRIGGER_PRESSED = 1
TRIGGER_RELEASED = 2

TRIGGER_NAMES: Dict[int, str] = {
    TRIGGER_HELD: "While Held",
    TRIGGER_PRESSED: "When Pressed",
    TRIGGER_RELEASED: "When Released",
}

ACTION_MOVE_LEFT = 1
ACTION_MOVE_RIGHT = 2
ACTION_MOVE_UP = 3
ACTION_MOVE_DOWN = 4
ACTION_JUMP = 5
ACTION_DASH = 6
ACTION_SHOOT = 7
ACTION_MELEE = 8
ACTION_PALETTE_NEXT = 9
ACTION_PLAY_SFX = 10
ACTION_SWITCH_ANIM = 11
ACTION_RESET_LEVEL = 12
ACTION_PAUSE = 13
ACTION_MORPH_BALL = 14
ACTION_AIM_UP = 15
ACTION_BOMB = 16
ACTION_INTERACT = 17
ACTION_SUPER_BURST = 18  # 3-Way Heavy Spread + Screen Shake + DMA (Energy Wave / Finger Lasers / CO Power!)
ACTION_HEAL = 19         # Restore +1 HP (Senzu / Potion / Repair / Energy Tank!)

ACTION_NAMES: Dict[int, str] = {
    ACTION_MOVE_LEFT: "Move Left",
    ACTION_MOVE_RIGHT: "Move Right",
    ACTION_MOVE_UP: "Move Up / Aim Up / Climb",
    ACTION_MOVE_DOWN: "Move Down / Crouch / Climb",
    ACTION_JUMP: "Jump / Swim / Wall-Jump",
    ACTION_DASH: "Speed Dash / Dodge Burst",
    ACTION_SHOOT: "Fire Projectile (8-Way Aim)",
    ACTION_MELEE: "Melee Slash / Strike",
    ACTION_PALETTE_NEXT: "Cycle Sprite Palette",
    ACTION_PLAY_SFX: "Play Chiptune SFX",
    ACTION_SWITCH_ANIM: "Play Sprite Animation",
    ACTION_RESET_LEVEL: "Restart Stage",
    ACTION_PAUSE: "Pause & Auto-Minimap",
    ACTION_MORPH_BALL: "Toggle Alt Form (Swap Sprite & Hitbox)",
    ACTION_AIM_UP: "Hold Aim Up / Diagonal 45°",
    ACTION_BOMB: "Fire Heavy Shot / Blast",
    ACTION_INTERACT: "Interact / Talk / Examine",
    ACTION_SUPER_BURST: "Super Burst (3-Way + Shake + DMA)",
    ACTION_HEAL: "Heal / Repair (+1 HP)",
}

# Built-in authentic palettes (16 colors each; index 0 is transparent for sprites / backdrop for BG)
PRESET_PALETTES: Dict[str, List[str]] = {
    "GBA Starbit Retro": [
        "#101424", "#1B2238", "#F8FAFC", "#CBD5E1",
        "#64748B", "#8B5CF6", "#C4B5FD", "#34D399",
        "#059669", "#F59E0B", "#FDE047", "#F43F5E",
        "#FB7185", "#38BDF8", "#0284C7", "#92400E",
    ],
    "BSL Fusion Station": [
        "#0A101E", "#131D33", "#F0F9FF", "#94A3B8",
        "#475569", "#0EA5E9", "#38BDF8", "#FACC15",
        "#D97706", "#22C55E", "#86EFAC", "#EF4444",
        "#FB7185", "#A855F7", "#1E3A5F", "#334155",
    ],
    "GBC Pastel Quest": [
        "#181828", "#2B3A67", "#F8F8F8", "#A8DADC",
        "#457B9D", "#E63946", "#F4A261", "#E9C46A",
        "#2A9D8F", "#264653", "#F1FAEE", "#B5838D",
        "#6D6875", "#FFB4A2", "#8ECAE6", "#582F0E",
    ],
    "DMG Classic Olive": [
        "#9BBC0F", "#8BAC0F", "#306230", "#0F380F",
        "#9BBC0F", "#8BAC0F", "#306230", "#0F380F",
        "#9BBC0F", "#8BAC0F", "#306230", "#0F380F",
        "#9BBC0F", "#8BAC0F", "#306230", "#0F380F",
    ],
    "Game Boy Pocket": [
        "#E0F0E0", "#A8B8A8", "#586858", "#182018",
        "#E0F0E0", "#A8B8A8", "#586858", "#182018",
        "#E0F0E0", "#A8B8A8", "#586858", "#182018",
        "#E0F0E0", "#A8B8A8", "#586858", "#182018",
    ],
    "GBA Crimson Hero": [
        "#101424", "#1E1B2E", "#FFFFFF", "#FED7AA",
        "#94A3B8", "#EF4444", "#FCA5A5", "#F59E0B",
        "#B45309", "#38BDF8", "#E0F2FE", "#10B981",
        "#6EE7B7", "#A855F7", "#6B21A8", "#451A03",
    ],
    "GBA Emerald Knight": [
        "#101424", "#102420", "#FFFFFF", "#D1FAE5",
        "#64748B", "#10B981", "#6EE7B7", "#06B6D4",
        "#0E7490", "#FBBF24", "#FEF08A", "#F43F5E",
        "#FDA4AF", "#818CF8", "#4338CA", "#78350F",
    ],
}


def hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) < 6:
        return (0, 0, 0)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_bgr555(r: int, g: int, b: int) -> int:
    r5 = (r >> 3) & 0x1F
    g5 = (g >> 3) & 0x1F
    b5 = (b >> 3) & 0x1F
    return r5 | (g5 << 5) | (b5 << 10)


def hex_to_bgr555(h: str) -> int:
    return rgb_to_bgr555(*hex_to_rgb(h))


def bgr555_to_hex(val: int) -> str:
    r = ((val & 0x1F) << 3) | ((val & 0x1F) >> 2)
    g = (((val >> 5) & 0x1F) << 3) | (((val >> 5) & 0x1F) >> 2)
    b = (((val >> 10) & 0x1F) << 3) | (((val >> 10) & 0x1F) >> 2)
    return f"#{r:02X}{g:02X}{b:02X}"


def quantize_hex_bgr555(h: str) -> str:
    return bgr555_to_hex(hex_to_bgr555(h))


def empty_grid(w: int, h: int, fill: int = 0) -> List[List[int]]:
    return [[fill for _ in range(w)] for _ in range(h)]


# ---------------------------------------------------------------------------
# Assets: Metasprites, Animations, Tiles, Entities, Doors, Rules, SFX, DMA PCM
# ---------------------------------------------------------------------------
@dataclass
class AnimationClip:
    name: str
    frame_indices: List[int] = field(default_factory=lambda: [0])
    fps: int = 8
    loop: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "frame_indices": list(self.frame_indices),
            "fps": int(self.fps),
            "loop": bool(self.loop),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AnimationClip":
        return cls(
            name=str(d.get("name", "idle")),
            frame_indices=[int(x) for x in d.get("frame_indices", [0])],
            fps=max(1, min(30, int(d.get("fps", 8)))),
            loop=bool(d.get("loop", True)),
        )


@dataclass
class SpriteAsset:
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "Hero"
    role: str = "player"  # player | morph | enemy | boss | projectile | prop
    width: int = 16       # 16 or 32
    height: int = 16      # 16 or 32 (supports 16x16, 16x32 tall hero, 32x32 boss!)
    palette_index: int = 0
    frames: List[List[List[int]]] = field(default_factory=lambda: [empty_grid(16, 16, 0)])
    animations: List[AnimationClip] = field(default_factory=lambda: [AnimationClip("idle", [0], 6, True)])

    def get_clip(self, clip_name: str) -> AnimationClip:
        for a in self.animations:
            if a.name.lower() == clip_name.lower():
                return a
        return self.animations[0] if self.animations else AnimationClip("idle", [0], 6, True)

    def resize_frames(self, new_w: int, new_h: int) -> None:
        """Resize all frames cleanly to (16,16), (16,32), or (32,32) preserving existing pixels."""
        new_frames = []
        for fr in self.frames:
            g = empty_grid(new_w, new_h, 0)
            oh = len(fr)
            ow = len(fr[0]) if oh else 0
            for y in range(min(oh, new_h)):
                for x in range(min(ow, new_w)):
                    g[y][x] = fr[y][x]
            new_frames.append(g)
        self.width = new_w
        self.height = new_h
        self.frames = new_frames or [empty_grid(new_w, new_h, 0)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "role": self.role,
            "width": int(self.width),
            "height": int(self.height),
            "palette_index": int(self.palette_index),
            "frames": self.frames,
            "animations": [a.to_dict() for a in self.animations],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SpriteAsset":
        w = int(d.get("width", 16))
        h = int(d.get("height", 16))
        frames = d.get("frames") or [empty_grid(w, h, 0)]
        anims = [AnimationClip.from_dict(a) for a in d.get("animations", [])] or [AnimationClip("idle", [0], 6, True)]
        return cls(
            uid=str(d.get("uid", uuid.uuid4().hex[:8])),
            name=str(d.get("name", "Sprite")),
            role=str(d.get("role", "prop")),
            width=w,
            height=h,
            palette_index=int(d.get("palette_index", 0)),
            frames=frames,
            animations=anims,
        )


@dataclass
class TileAsset:
    name: str = "Tile"
    tile_type: int = TILE_EMPTY
    palette_index: int = 0
    pixels: List[List[int]] = field(default_factory=lambda: empty_grid(8, 8, 0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "tile_type": int(self.tile_type),
            "palette_index": int(self.palette_index),
            "pixels": self.pixels,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TileAsset":
        return cls(
            name=str(d.get("name", "Tile")),
            tile_type=int(d.get("tile_type", TILE_EMPTY)),
            palette_index=int(d.get("palette_index", 0)),
            pixels=d.get("pixels") or empty_grid(8, 8, 0),
        )


@dataclass
class EntityPlacement:
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    kind: str = "enemy"     # enemy | boss | npc
    ai_type: int = AI_PATROL
    sprite_index: int = 1
    tile_x: int = 10
    tile_y: int = 12
    patrol_range: int = 4   # tiles
    speed: int = 1          # px per 2 frames
    hp: int = 1             # >1 for tough enemies & multi-phase bosses!
    phase2_hp: int = 6      # HP threshold where Boss enters Phase 2 (3-way spread + fast dash!)
    defeat_flag: int = 0    # World Flag bit (0..31) set upon defeat (unlocks doors/events!)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "kind": self.kind,
            "ai_type": int(self.ai_type),
            "sprite_index": int(self.sprite_index),
            "tile_x": int(self.tile_x),
            "tile_y": int(self.tile_y),
            "patrol_range": int(self.patrol_range),
            "speed": int(self.speed),
            "hp": int(self.hp),
            "phase2_hp": int(self.phase2_hp),
            "defeat_flag": int(self.defeat_flag),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EntityPlacement":
        return cls(
            uid=str(d.get("uid", uuid.uuid4().hex[:8])),
            kind=str(d.get("kind", "enemy")),
            ai_type=int(d.get("ai_type", AI_PATROL)),
            sprite_index=int(d.get("sprite_index", 1)),
            tile_x=int(d.get("tile_x", 10)),
            tile_y=int(d.get("tile_y", 12)),
            patrol_range=int(d.get("patrol_range", 4)),
            speed=int(d.get("speed", 1)),
            hp=max(1, int(d.get("hp", 1))),
            phase2_hp=max(0, int(d.get("phase2_hp", 6))),
            defeat_flag=max(0, min(31, int(d.get("defeat_flag", 0)))),
        )


@dataclass
class DoorLink:
    """Interconnected room hatch/door warp (with optional Metroidvania ability gate!)."""
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    tile_x: int = 44
    tile_y: int = 15
    target_room: int = 0
    target_x: int = 3
    target_y: int = 14
    req_ability: int = ABIL_NONE  # 0 = unlocked, or ABIL_MORPH_BALL / ABIL_MISSILES / etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "tile_x": int(self.tile_x),
            "tile_y": int(self.tile_y),
            "target_room": int(self.target_room),
            "target_x": int(self.target_x),
            "target_y": int(self.target_y),
            "req_ability": int(self.req_ability),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DoorLink":
        return cls(
            uid=str(d.get("uid", uuid.uuid4().hex[:8])),
            tile_x=int(d.get("tile_x", 0)),
            tile_y=int(d.get("tile_y", 0)),
            target_room=int(d.get("target_room", 0)),
            target_x=int(d.get("target_x", 3)),
            target_y=int(d.get("target_y", 14)),
            req_ability=int(d.get("req_ability", ABIL_NONE)),
        )


@dataclass
class LevelMap:
    name: str = "Stage 1 — Starbit Meadow"
    width: int = 48   # tiles (max 64)
    height: int = 20  # tiles (max 32)
    world_x: int = 0  # Minimap grid X (0..15)
    world_y: int = 0  # Minimap grid Y (0..7)
    spawn_x: int = 3
    spawn_y: int = 14
    cells: List[List[int]] = field(default_factory=lambda: empty_grid(48, 20, 0))
    entities: List[EntityPlacement] = field(default_factory=list)
    doors: List[DoorLink] = field(default_factory=list)
    dialogue_text: str = "ADAM: SCAN SECTOR AND FIND UPGRADES!"
    dialogue_page2: str = "PRESS START ANYTIME FOR SECTOR MINIMAP."
    upgrade_ability: int = ABIL_MORPH_BALL
    switch_flag: int = 1        # World Flag bit (0..31) toggled by TILE_SWITCH in this room
    parallax_enabled: bool = True
    parallax_tile_idx: int = 8  # BG tile tiled onto BG2 at 1/2 camera speed!

    def get_tile(self, tx: int, ty: int) -> int:
        if 0 <= ty < self.height and 0 <= tx < self.width:
            return self.cells[ty][tx]
        return 0

    def set_tile(self, tx: int, ty: int, tile_idx: int) -> None:
        if 0 <= ty < self.height and 0 <= tx < self.width:
            self.cells[ty][tx] = tile_idx

    def find_door_near(self, tx: int, ty: int) -> Optional[DoorLink]:
        for d in self.doors:
            if abs(d.tile_x - tx) <= 1 and abs(d.tile_y - ty) <= 2:
                return d
        return self.doors[0] if self.doors else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "width": int(self.width),
            "height": int(self.height),
            "world_x": int(self.world_x),
            "world_y": int(self.world_y),
            "spawn_x": int(self.spawn_x),
            "spawn_y": int(self.spawn_y),
            "cells": self.cells,
            "entities": [e.to_dict() for e in self.entities],
            "doors": [d.to_dict() for d in self.doors],
            "dialogue_text": self.dialogue_text[:48],
            "dialogue_page2": self.dialogue_page2[:48],
            "upgrade_ability": int(self.upgrade_ability),
            "switch_flag": int(self.switch_flag),
            "parallax_enabled": bool(self.parallax_enabled),
            "parallax_tile_idx": int(self.parallax_tile_idx),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LevelMap":
        w = max(20, min(64, int(d.get("width", 48))))
        h = max(18, min(32, int(d.get("height", 20))))
        cells = d.get("cells") or empty_grid(w, h, 0)
        return cls(
            name=str(d.get("name", "Stage 1")),
            width=w,
            height=h,
            world_x=max(0, min(15, int(d.get("world_x", 0)))),
            world_y=max(0, min(7, int(d.get("world_y", 0)))),
            spawn_x=int(d.get("spawn_x", 3)),
            spawn_y=int(d.get("spawn_y", 14)),
            cells=cells,
            entities=[EntityPlacement.from_dict(e) for e in d.get("entities", [])],
            doors=[DoorLink.from_dict(dr) for dr in d.get("doors", [])],
            dialogue_text=str(d.get("dialogue_text", "ADAM: SCAN SECTOR AND FIND UPGRADES!"))[:48],
            dialogue_page2=str(d.get("dialogue_page2", "PRESS START ANYTIME FOR SECTOR MINIMAP."))[:48],
            upgrade_ability=int(d.get("upgrade_ability", ABIL_MORPH_BALL)),
            switch_flag=max(0, min(31, int(d.get("switch_flag", 1)))),
            parallax_enabled=bool(d.get("parallax_enabled", True)),
            parallax_tile_idx=int(d.get("parallax_tile_idx", 8)),
        )


@dataclass
class ButtonRule:
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    button: str = "A"
    trigger: int = TRIGGER_PRESSED
    action: int = ACTION_JUMP
    param: int = 5
    anim_name: str = "jump"
    sfx_index: int = 0
    enabled: bool = True
    # v3.0 Universal Conditional & Variable Wiring (Ammo / MP / Keys / Flags!)
    cond_type: int = COND_ALWAYS  # COND_ALWAYS | COND_VAR_POS | COND_FLAG_SET | COND_ABIL_OWNED
    cond_idx: int = 0             # Var index (0..15) / Flag bit (0..31) / Ability bit
    var_delta: int = 0            # Signed change to VAR[cond_idx] on trigger (e.g., -1 missile!)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "button": self.button,
            "trigger": int(self.trigger),
            "action": int(self.action),
            "param": int(self.param),
            "anim_name": self.anim_name,
            "sfx_index": int(self.sfx_index),
            "enabled": bool(self.enabled),
            "cond_type": int(self.cond_type),
            "cond_idx": int(self.cond_idx),
            "var_delta": int(self.var_delta),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ButtonRule":
        return cls(
            uid=str(d.get("uid", uuid.uuid4().hex[:8])),
            button=str(d.get("button", "A")),
            trigger=int(d.get("trigger", TRIGGER_PRESSED)),
            action=int(d.get("action", ACTION_JUMP)),
            param=int(d.get("param", 5)),
            anim_name=str(d.get("anim_name", "")),
            sfx_index=int(d.get("sfx_index", -1)),
            enabled=bool(d.get("enabled", True)),
            cond_type=int(d.get("cond_type", COND_ALWAYS)),
            cond_idx=int(d.get("cond_idx", 0)),
            var_delta=int(d.get("var_delta", 0)),
        )


@dataclass
class SfxPatch:
    """Hardware-accurate GB/GBC/GBA PSG Sound Patch (Channel 1 Square+Sweep or Channel 4 Noise)."""
    name: str = "Jump"
    channel: int = 1
    freq_hz: int = 440
    duty: int = 2
    volume: int = 13
    env_step: int = 2
    sweep_time: int = 2
    sweep_dir: int = 0
    sweep_shift: int = 3
    noise_div: int = 3
    noise_shift: int = 4
    noise_short: bool = False
    duration_ms: int = 180

    def to_gba_regs(self) -> Tuple[int, int, int, int]:
        if self.channel == 4:
            cnt_l = ((self.volume & 0xF) << 12) | ((self.env_step & 0x7) << 8)
            cnt_h = 0x8000 | ((self.noise_shift & 0xF) << 4) | ((1 if self.noise_short else 0) << 3) | (self.noise_div & 0x7)
            return (4, cnt_l, cnt_h, 0)
        else:
            hz = max(65, min(4000, int(self.freq_hz)))
            rate = max(0, min(2047, int(round(2048 - 131072.0 / hz))))
            cnt_l = ((self.sweep_time & 0x7) << 4) | ((self.sweep_dir & 0x1) << 3) | (self.sweep_shift & 0x7)
            cnt_h = ((self.volume & 0xF) << 12) | ((self.env_step & 0x7) << 8) | ((self.duty & 0x3) << 6)
            cnt_x = 0x8000 | rate
            return (1, cnt_l, cnt_h, cnt_x)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "channel": int(self.channel),
            "freq_hz": int(self.freq_hz),
            "duty": int(self.duty),
            "volume": int(self.volume),
            "env_step": int(self.env_step),
            "sweep_time": int(self.sweep_time),
            "sweep_dir": int(self.sweep_dir),
            "sweep_shift": int(self.sweep_shift),
            "noise_div": int(self.noise_div),
            "noise_shift": int(self.noise_shift),
            "noise_short": bool(self.noise_short),
            "duration_ms": int(self.duration_ms),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SfxPatch":
        return cls(
            name=str(d.get("name", "SFX")),
            channel=int(d.get("channel", 1)),
            freq_hz=int(d.get("freq_hz", 440)),
            duty=int(d.get("duty", 2)),
            volume=int(d.get("volume", 12)),
            env_step=int(d.get("env_step", 2)),
            sweep_time=int(d.get("sweep_time", 2)),
            sweep_dir=int(d.get("sweep_dir", 0)),
            sweep_shift=int(d.get("sweep_shift", 3)),
            noise_div=int(d.get("noise_div", 3)),
            noise_shift=int(d.get("noise_shift", 4)),
            noise_short=bool(d.get("noise_short", False)),
            duration_ms=int(d.get("duration_ms", 180)),
        )


@dataclass
class DirectSoundConfig:
    """GBA Direct Sound DMA Channel A (8-bit signed PCM sample played via DMA1 + Timer 0 + FIFO_A)."""
    enabled: bool = True
    preset: str = "Boss Explosion"  # "Boss Explosion" | "BSL Alarm" | "Item Fanfare" | "Laser Charge"
    sample_rate: int = 8192

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "preset": self.preset,
            "sample_rate": int(self.sample_rate),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DirectSoundConfig":
        return cls(
            enabled=bool(d.get("enabled", True)),
            preset=str(d.get("preset", "Boss Explosion")),
            sample_rate=max(4096, min(16384, int(d.get("sample_rate", 8192)))),
        )


# ---------------------------------------------------------------------------
# KinoPixel Project Container (.kpx) — Multi-Room Metroidvania + Undo/Redo
# ---------------------------------------------------------------------------
@dataclass
class KinoPixelProject:
    title: str = "STARBIT GBA"
    game_code: str = "KPIX"
    maker_code: str = "KP"
    target_system: str = "GBA"          # "GBA" | "GBC" | "GB"
    physics_mode: str = "platformer"    # "platformer" | "topdown"
    gravity: int = 44
    max_fall_speed: int = 768
    bg_color_hex: str = "#101424"
    alpha_blend_enabled: bool = True    # Hardware REG_BLDCNT / REG_BLDALPHA on BG2 parallax
    sram_save_enabled: bool = True      # Real GBA Cartridge SRAM (0x0E000000 + SRAM_V113)
    starting_abilities: int = ABIL_WALL_JUMP
    starting_vars: List[int] = field(default_factory=lambda: [10, 0, 0, 0, 0, 0, 0, 0])  # VAR[0]=Ammo/MP, VAR[1]=Gold/Keys, etc.
    morph_sprite_index: int = -1        # Optional dedicated 16x16 Morph Ball sprite index
    palettes: List[List[str]] = field(default_factory=list)
    sprites: List[SpriteAsset] = field(default_factory=list)
    tiles: List[TileAsset] = field(default_factory=list)
    rooms: List[LevelMap] = field(default_factory=lambda: [LevelMap()])
    active_room_idx: int = 0
    button_rules: List[ButtonRule] = field(default_factory=list)
    sfx_list: List[SfxPatch] = field(default_factory=list)
    sequence_genie: SequenceGenieData = field(default_factory=SequenceGenieData)
    direct_sound: DirectSoundConfig = field(default_factory=DirectSoundConfig)
    file_path: Optional[str] = None
    dirty: bool = False

    _history: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list, repr=False)
    _history_idx: int = field(default=-1, repr=False)

    # Backward-compatible .level property always pointing to active room!
    @property
    def level(self) -> LevelMap:
        if not self.rooms:
            self.rooms = [LevelMap()]
        idx = max(0, min(len(self.rooms) - 1, self.active_room_idx))
        return self.rooms[idx]

    @level.setter
    def level(self, lvl: LevelMap) -> None:
        if not self.rooms:
            self.rooms = [lvl]
            self.active_room_idx = 0
        else:
            idx = max(0, min(len(self.rooms) - 1, self.active_room_idx))
            self.rooms[idx] = lvl

    def profile(self) -> Dict[str, Any]:
        return HARDWARE_PROFILES.get(self.target_system, HARDWARE_PROFILES["GBA"])

    def active_palette_size(self) -> int:
        return int(self.profile()["colors_per_palette"])

    def get_palette_colors(self, idx: int) -> List[str]:
        if not self.palettes:
            return list(PRESET_PALETTES["GBA Starbit Retro"])
        return self.palettes[idx % len(self.palettes)]

    def snapshot_push(self, label: str) -> None:
        snap = self.to_dict()
        if self._history_idx < len(self._history) - 1:
            self._history = self._history[: self._history_idx + 1]
        self._history.append((label, snap))
        if len(self._history) > 40:
            self._history.pop(0)
        self._history_idx = len(self._history) - 1
        self.dirty = True

    def can_undo(self) -> bool:
        return self._history_idx > 0

    def can_redo(self) -> bool:
        return 0 <= self._history_idx < len(self._history) - 1

    def undo(self) -> Optional[str]:
        if not self.can_undo():
            return None
        self._history_idx -= 1
        lbl, snap = self._history[self._history_idx]
        self._restore_dict(snap)
        return lbl

    def redo(self) -> Optional[str]:
        if not self.can_redo():
            return None
        self._history_idx += 1
        lbl, snap = self._history[self._history_idx]
        self._restore_dict(snap)
        return lbl

    def history_labels(self) -> Tuple[List[str], int]:
        return ([h[0] for h in self._history], self._history_idx)

    def restore_history_index(self, idx: int) -> bool:
        if 0 <= idx < len(self._history):
            self._history_idx = idx
            self._restore_dict(self._history[idx][1])
            return True
        return False

    def _restore_dict(self, d: Dict[str, Any]) -> None:
        fresh = KinoPixelProject.from_dict(copy.deepcopy(d))
        self.title = fresh.title
        self.game_code = fresh.game_code
        self.maker_code = fresh.maker_code
        self.target_system = fresh.target_system
        self.physics_mode = fresh.physics_mode
        self.gravity = fresh.gravity
        self.max_fall_speed = fresh.max_fall_speed
        self.bg_color_hex = fresh.bg_color_hex
        self.alpha_blend_enabled = fresh.alpha_blend_enabled
        self.sram_save_enabled = fresh.sram_save_enabled
        self.starting_abilities = fresh.starting_abilities
        self.starting_vars = list(fresh.starting_vars)
        self.morph_sprite_index = fresh.morph_sprite_index
        self.palettes = fresh.palettes
        self.sprites = fresh.sprites
        self.tiles = fresh.tiles
        self.rooms = fresh.rooms
        self.active_room_idx = fresh.active_room_idx
        self.button_rules = fresh.button_rules
        self.sfx_list = fresh.sfx_list
        self.sequence_genie = fresh.sequence_genie
        self.direct_sound = fresh.direct_sound

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": "KinoPixelProject",
            "version": 2,
            "title": self.title,
            "game_code": self.game_code,
            "maker_code": self.maker_code,
            "target_system": self.target_system,
            "physics_mode": self.physics_mode,
            "gravity": int(self.gravity),
            "max_fall_speed": int(self.max_fall_speed),
            "bg_color_hex": self.bg_color_hex,
            "alpha_blend_enabled": bool(self.alpha_blend_enabled),
            "sram_save_enabled": bool(self.sram_save_enabled),
            "starting_abilities": int(self.starting_abilities),
            "starting_vars": [int(v) for v in self.starting_vars[:8]],
            "morph_sprite_index": int(self.morph_sprite_index),
            "palettes": [list(p) for p in self.palettes],
            "sprites": [s.to_dict() for s in self.sprites],
            "tiles": [t.to_dict() for t in self.tiles],
            "rooms": [r.to_dict() for r in self.rooms],
            "active_room_idx": int(self.active_room_idx),
            "button_rules": [r.to_dict() for r in self.button_rules],
            "sfx_list": [x.to_dict() for x in self.sfx_list],
            "sequence_genie": self.sequence_genie.to_dict(),
            "direct_sound": self.direct_sound.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KinoPixelProject":
        # Support both v2 multi-room 'rooms' and legacy v1 single 'level'
        if "rooms" in d and d["rooms"]:
            rooms = [LevelMap.from_dict(r) for r in d["rooms"]]
        elif "level" in d:
            rooms = [LevelMap.from_dict(d["level"])]
        else:
            rooms = [LevelMap()]
        proj = cls(
            title=str(d.get("title", "UNTITLED"))[:12],
            game_code=str(d.get("game_code", "KPIX"))[:4],
            maker_code=str(d.get("maker_code", "KP"))[:2],
            target_system=str(d.get("target_system", "GBA")),
            physics_mode=str(d.get("physics_mode", "platformer")),
            gravity=int(d.get("gravity", 44)),
            max_fall_speed=int(d.get("max_fall_speed", 768)),
            bg_color_hex=str(d.get("bg_color_hex", "#101424")),
            alpha_blend_enabled=bool(d.get("alpha_blend_enabled", True)),
            sram_save_enabled=bool(d.get("sram_save_enabled", True)),
            starting_abilities=int(d.get("starting_abilities", ABIL_WALL_JUMP)),
            starting_vars=[int(v) for v in d.get("starting_vars", [10, 0, 0, 0, 0, 0, 0, 0])][:8],
            morph_sprite_index=int(d.get("morph_sprite_index", -1)),
            palettes=[list(p) for p in d.get("palettes", [list(PRESET_PALETTES["GBA Starbit Retro"])])],
            sprites=[SpriteAsset.from_dict(s) for s in d.get("sprites", [])],
            tiles=[TileAsset.from_dict(t) for t in d.get("tiles", [])],
            rooms=rooms,
            active_room_idx=max(0, min(len(rooms) - 1, int(d.get("active_room_idx", 0)))),
            button_rules=[ButtonRule.from_dict(r) for r in d.get("button_rules", [])],
            sfx_list=[SfxPatch.from_dict(x) for x in d.get("sfx_list", [])],
            sequence_genie=SequenceGenieData.from_dict(d["sequence_genie"]) if "sequence_genie" in d else SequenceGenieData(),
            direct_sound=DirectSoundConfig.from_dict(d["direct_sound"]) if "direct_sound" in d else DirectSoundConfig(),
        )
        proj.sequence_genie.ensure_initialized()
        return proj

    def save_kpx(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        self.file_path = path
        self.dirty = False

    @classmethod
    def load_kpx(cls, path: str) -> "KinoPixelProject":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        proj = cls.from_dict(data)
        proj.file_path = path
        proj.dirty = False
        proj.snapshot_push("Opened Project")
        proj.dirty = False
        return proj

    def hardware_stats(self) -> Dict[str, int]:
        bg_tiles = len(self.tiles)
        obj_tiles = 0
        for sp in self.sprites:
            tiles_per_frame = max(1, (sp.width // 8) * (sp.height // 8))
            obj_tiles += len(sp.frames) * tiles_per_frame
        max_ent = max((len(r.entities) for r in self.rooms), default=0)
        oam_sprites = 1 + 6 + max_ent  # hero + 4 player projs + 2 enemy projs + enemies/boss
        return {
            "bg_tiles": bg_tiles,
            "bg_tiles_max": int(self.profile()["max_bg_tiles"]),
            "obj_tiles": obj_tiles,
            "obj_tiles_max": int(self.profile()["max_obj_tiles"]),
            "oam_sprites": oam_sprites,
            "oam_sprites_max": int(self.profile()["max_sprites"]),
            "rules_count": sum(1 for r in self.button_rules if r.enabled),
            "rooms_count": len(self.rooms),
        }
