"""KinoPixel v2.0 Native ARM7TDMI GBA Metroidvania ROM Compiler (+ .gb/.gbc & C Export).

Compiles any KinoPixelProject directly into a bootable, playable .gba ROM with:
- Multi-room interconnected world & ability-gated Doors/Hatches
- Real GBA Cartridge SRAM battery saves (0x0E000000 + 'SRAM_V113')
- Multi-size hardware metasprites (16x16, 16x32 tall hero, 32x32 bosses)
- Morph Ball hitbox & sprite swap (fits through low tunnels!)
- 8-way / diagonal Arm Cannon aiming, Wall-Jump, Bombs/Missiles & Destructible Blocks
- Enemy AI: Patrol, Stalker/Chaser (SA-X), Plasma Turret, and 32x32 Multi-HP Bosses
- Hardware Parallax BG2 (1/2 speed) + Hardware Alpha Blending (REG_BLDCNT / REG_BLDALPHA)
- GBA PSG Channels 1 & 4 (SFX) + Channel 2 (Sequence Genie BGM) + Direct Sound DMA Channel A (8-bit PCM!)
- BG1 Hardware HUD + Navigation Terminal Dialogue Box
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .arm_asm import (
    ArmAssembler,
    LR,
    PC,
    R0, R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12,
    SP,
)
from .audio_sfx import generate_direct_sound_pcm
from .models import (
    ABIL_HIGH_JUMP,
    ABIL_MISSILES,
    ABIL_MORPH_BALL,
    ABIL_WALL_JUMP,
    ACTION_AIM_UP,
    ACTION_BOMB,
    ACTION_DASH,
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
    ACTION_SWITCH_ANIM,
    AI_BOSS,
    AI_CHASER,
    AI_TURRET,
    BUTTON_BITS,
    KinoPixelProject,
    SpriteAsset,
    TILE_BOUNCE,
    TILE_BREAKABLE,
    TILE_COIN,
    TILE_DOOR,
    TILE_GOAL,
    TILE_HAZARD,
    TILE_ONEWAY,
    TILE_SAVE,
    TILE_SOLID,
    TILE_TERMINAL,
    TILE_UPGRADE,
    TRIGGER_HELD,
    TRIGGER_PRESSED,
    TRIGGER_RELEASED,
    hex_to_bgr555,
)
from .sequence_genie import compile_genie_to_gba_bgm

# ---------------------------------------------------------------------------
# Authentic Verified Hardware Cartridge Logo Bytes
# ---------------------------------------------------------------------------
GBA_NINTENDO_LOGO = bytes.fromhex(
    "24 FF AE 51 69 9A A2 21 3D 84 82 0A 84 E4 09 AD"
    "11 24 8B 98 C0 81 7F 21 A3 52 BE 19 93 09 CE 20"
    "10 46 4A 4A F8 27 31 EC 58 C7 E8 33 82 E3 CE BF"
    "85 F4 DF 94 CE 4B 09 C1 94 56 8A C0 13 72 A7 FC"
    "9F 84 4D 73 A3 CA 9A 61 58 97 A3 27 FC 03 98 76"
    "23 1D C7 61 03 04 AE 56 BF 38 84 00 40 A7 0E FD"
    "FF 52 FE 03 6F 95 30 F1 97 FB C0 85 60 D6 80 25"
    "A9 63 BE 03 01 4E 38 E2 F9 A2 34 FF BB 3E 03 44"
    "78 00 90 CB 88 11 3A 94 65 C0 7C 63 87 F0 3C AF"
    "D6 25 E4 8B 38 0A AC 72 21 D4 F8 07"
)
assert len(GBA_NINTENDO_LOGO) == 156

GB_NINTENDO_LOGO = bytes.fromhex(
    "CE ED 66 66 CC 0D 00 0B 03 73 00 83 00 0C 00 0D"
    "00 08 11 1F 88 89 00 0E DC CC 6E E6 DD DD D9 99"
    "BB BB 67 63 6E 0E EC CC DD DC 99 9F BB B9 33 3E"
)
assert len(GB_NINTENDO_LOGO) == 48

# ---------------------------------------------------------------------------
# Crisp 8x8 Pixel Font for BG1 HUD & Navigation Terminal Dialogue Box
# ---------------------------------------------------------------------------
_FONT_BITMAPS: Dict[str, List[str]] = {
    " ": ["........", "........", "........", "........", "........", "........", "........", "........"],
    "0": [".#####..", "##...##.", "##..###.", "##.#.##.", "###..##.", "##...##.", ".#####..", "........"],
    "1": ["..###...", ".####...", "...##...", "...##...", "...##...", "...##...", ".######.", "........"],
    "2": [".#####..", "##...##.", ".....##.", "..####..", ".##.....", "##......", "#######.", "........"],
    "3": [".#####..", "##...##.", ".....##.", "..####..", ".....##.", "##...##.", ".#####..", "........"],
    "4": ["...###..", "..####..", ".##.##..", "##..##..", "#######.", "....##..", "....##..", "........"],
    "5": ["#######.", "##......", "######..", ".....##.", ".....##.", "##...##.", ".#####..", "........"],
    "6": [".#####..", "##......", "######..", "##...##.", "##...##.", "##...##.", ".#####..", "........"],
    "7": ["#######.", ".....##.", "....##..", "...##...", "..##....", "..##....", "..##....", "........"],
    "8": [".#####..", "##...##.", "##...##.", ".#####..", "##...##.", "##...##.", ".#####..", "........"],
    "9": [".#####..", "##...##.", "##...##.", ".######.", ".....##.", "....##..", ".####...", "........"],
    "A": ["..###...", ".##.##..", "##...##.", "#######.", "##...##.", "##...##.", "##...##.", "........"],
    "B": ["######..", "##...##.", "##...##.", "######..", "##...##.", "##...##.", "######..", "........"],
    "C": [".#####..", "##...##.", "##......", "##......", "##......", "##...##.", ".#####..", "........"],
    "D": ["#####...", "##..##..", "##...##.", "##...##.", "##...##.", "##..##..", "#####...", "........"],
    "E": ["#######.", "##......", "##......", "#####...", "##......", "##......", "#######.", "........"],
    "F": ["#######.", "##......", "##......", "#####...", "##......", "##......", "##......", "........"],
    "G": [".#####..", "##...##.", "##......", "##..###.", "##...##.", "##...##.", ".#####..", "........"],
    "H": ["##...##.", "##...##.", "##...##.", "#######.", "##...##.", "##...##.", "##...##.", "........"],
    "I": [".#####..", "...##...", "...##...", "...##...", "...##...", "...##...", ".#####..", "........"],
    "J": ["..#####.", "....##..", "....##..", "....##..", "##..##..", "##..##..", ".####...", "........"],
    "K": ["##...##.", "##..##..", "##.##...", "####....", "##.##...", "##..##..", "##...##.", "........"],
    "L": ["##......", "##......", "##......", "##......", "##......", "##......", "#######.", "........"],
    "M": ["##...##.", "###.###.", "#######.", "##.#.##.", "##...##.", "##...##.", "##...##.", "........"],
    "N": ["##...##.", "###..##.", "####.##.", "##.####.", "##..###.", "##...##.", "##...##.", "........"],
    "O": [".#####..", "##...##.", "##...##.", "##...##.", "##...##.", "##...##.", ".#####..", "........"],
    "P": ["######..", "##...##.", "##...##.", "######..", "##......", "##......", "##......", "........"],
    "Q": [".#####..", "##...##.", "##...##.", "##...##.", "##.#.##.", "##..##..", ".####.#.", "........"],
    "R": ["######..", "##...##.", "##...##.", "######..", "##.##...", "##..##..", "##...##.", "........"],
    "S": [".#####..", "##...##.", "##......", ".#####..", ".....##.", "##...##.", ".#####..", "........"],
    "T": ["######..", "..##....", "..##....", "..##....", "..##....", "..##....", "..##....", "........"],
    "U": ["##...##.", "##...##.", "##...##.", "##...##.", "##...##.", "##...##.", ".#####..", "........"],
    "V": ["##...##.", "##...##.", "##...##.", "##...##.", ".##.##..", "..###...", "...#....", "........"],
    "W": ["##...##.", "##...##.", "##...##.", "##.#.##.", "#######.", "###.###.", "##...##.", "........"],
    "X": ["##...##.", ".##.##..", "..###...", "..###...", ".##.##..", "##...##.", "##...##.", "........"],
    "Y": ["##...##.", ".##.##..", "..###...", "...##...", "...##...", "...##...", "...##...", "........"],
    "Z": ["#######.", "....##..", "...##...", "..##....", ".##.....", "##......", "#######.", "........"],
    ":": ["........", "...##...", "...##...", "........", "...##...", "...##...", "........", "........"],
    "!": ["...##...", "...##...", "...##...", "...##...", "...##...", "........", "...##...", "........"],
    ".": ["........", "........", "........", "........", "........", "..##....", "..##....", "........"],
    "-": ["........", "........", "........", ".#####..", "........", "........", "........", "........"],
    "HEART": ["........", ".##.##..", "#######.", "#######.", ".#####..", "..###...", "...#....", "........"],
    "COIN": ["..###...", ".#####..", "##.#.##.", "##.#.##.", "##.#.##.", ".#####..", "..###...", "........"],
    "BEZEL": ["########", "########", "########", "########", "########", "########", "########", "########"],
    "BOX": ["########", "########", "########", "########", "########", "########", "########", "########"],
    "BAR": ["........", "########", "########", "########", "########", "########", "........", "........"],
}

FONT_ORDER = (
    [" "] + [str(d) for d in range(10)] + [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    + [":", "!", ".", "-", "HEART", "COIN", "BEZEL", "BOX", "BAR"]
)
FONT_INDEX: Dict[str, int] = {ch: i for i, ch in enumerate(FONT_ORDER)}


def _pack_tile_4bpp(grid_8x8: List[List[int]]) -> bytes:
    out = bytearray(32)
    idx = 0
    for y in range(8):
        row = grid_8x8[y] if y < len(grid_8x8) else [0] * 8
        for x in range(0, 8, 2):
            p0 = (row[x] & 0xF) if x < len(row) else 0
            p1 = (row[x + 1] & 0xF) if (x + 1) < len(row) else 0
            out[idx] = p0 | (p1 << 4)
            idx += 1
    return bytes(out)


def _pack_metasprite_4bpp(frame: List[List[int]], w: int, h: int) -> bytes:
    """Pack a 16x16, 16x32, or 32x32 metasprite frame into sequential GBA 1D OBJ 4bpp tiles."""
    chunks = bytearray()
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            sub = [
                [frame[ty + y][tx + x] if (ty + y < len(frame) and tx + x < len(frame[ty + y])) else 0 for x in range(8)]
                for y in range(8)
            ]
            chunks.extend(_pack_tile_4bpp(sub))
    return bytes(chunks)


def _oam_shape_size_flags(w: int, h: int) -> Tuple[int, int]:
    """Return (attr0_shape_bits, attr1_size_bits) for GBA OAM 16x16, 16x32, or 32x32."""
    if w == 16 and h == 32:
        return (0x8000, 0x8000)  # Tall shape (2), size 2 -> 16x32
    if w == 32 and h == 32:
        return (0x0000, 0x8000)  # Square shape (0), size 2 -> 32x32
    return (0x0000, 0x4000)      # Square shape (0), size 1 -> 16x16


def _build_hud_font_tiles() -> bytes:
    out = bytearray()
    for key in FONT_ORDER:
        bmp = _FONT_BITMAPS[key]
        color_idx = 2
        if key == "HEART":
            color_idx = 4
        elif key == "COIN":
            color_idx = 3
        elif key == "BEZEL":
            color_idx = 5
        elif key == "BOX":
            color_idx = 1
        elif key == "BAR":
            color_idx = 6
        grid = [[color_idx if ch == "#" else 0 for ch in row] for row in bmp]
        out.extend(_pack_tile_4bpp(grid))
    return bytes(out)


def _encode_dialogue_indices(text: str) -> bytes:
    """Encode up to 48 chars as FONT_INDEX bytes (2 lines x 24 chars inside BG1 dialogue box)."""
    clean = "".join(c if c in FONT_INDEX else " " for c in text.upper())[:48].ljust(48, " ")
    return bytes(FONT_INDEX[c] for c in clean)


def compute_gba_header_checksum(header: bytes) -> int:
    chk = 0
    for b in header[0xA0:0xBD]:
        chk = (chk - b) & 0xFF
    chk = (chk - 0x19) & 0xFF
    return chk


@dataclass
class BuildReport:
    output_path: str
    rom_size: int
    format_name: str
    title: str
    checksum_hex: str
    bg_tiles: int
    obj_tiles: int
    rules_compiled: int
    enemies_compiled: int
    sfx_compiled: int
    rooms_compiled: int = 1
    warnings: List[str] = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


# ---------------------------------------------------------------------------
# IWRAM State Offsets (Base R11 = 0x03000000)
# ---------------------------------------------------------------------------
ST_PX = 0x00          # player x (8.8 fixed)
ST_PY = 0x04          # player y (8.8 fixed)
ST_VX = 0x08          # player vx (8.8 fixed)
ST_VY = 0x0C          # player vy (8.8 fixed)
ST_FACING = 0x10      # 0=right, 1=left
ST_GROUND = 0x14      # 0 or 1
ST_PAL = 0x18         # active player palette 0..N-1
ST_ANIM = 0x1C        # 0=idle, 1=walk, 2=jump, 3=attack
ST_ATIMER = 0x20      # anim tick counter
ST_ALOCK = 0x24       # forced anim lock ticks
ST_PREV_K = 0x28      # previous frame keys
ST_CURR_K = 0x2C      # current frame keys
ST_PRESS_K = 0x30     # just pressed keys
ST_REL_K = 0x34       # just released keys
ST_SCORE = 0x38       # integer score
ST_COINS = 0x3C       # collected coin/energy count
ST_HP = 0x40          # health (default 5)
ST_INVULN = 0x44      # invulnerability frames
ST_PAUSED = 0x48      # 0 or 1
ST_WON = 0x4C         # 0 or 1
ST_CAMX = 0x50        # camera x (int px)
ST_CAMY = 0x54        # camera y (int px)
ST_FRAME = 0x58       # global frame counter
ST_DASH = 0x5C        # dash / wall-jump momentum frames
ST_MELEE = 0x60       # melee active frames
ST_SHOOT_CD = 0x64    # projectile cooldown
ST_MOVED = 0x68       # moved this frame flag
ST_BGM_TICK = 0x6C    # Sequence Genie BGM divider
ST_BGM_STEP = 0x70    # Sequence Genie step 0..15
ST_ROOM_IDX = 0x74    # active room index 0..N-1
ST_ROOM_PTR = 0x78    # pointer to active ROM_ROOM descriptor
ST_ABILITIES = 0x7C   # unlocked ability bitmask
ST_MORPHED = 0x80     # 0=standing, 1=morph ball (16x16 hitbox!)
ST_AIM_Y = 0x84       # -1=up, 0=horiz, +1=down
ST_DIALOG_ON = 0x88   # 1 if Navigation Terminal dialogue box open
ST_MSG_TIMER = 0x8C   # HUD flash banner timer (SAVED! / LOCKED / UPGRD!)
ST_MSG_CODE = 0x90    # 1=SAVED!, 2=LOCKED, 3=UPGRD!
ST_DMA_TIMER = 0x94   # Direct Sound DMA Channel A active frames countdown
ST_DOOR_CD = 0x98     # door warp cooldown frames
ST_BOSS_DEAD = 0x9C   # boss defeated bitmask
ST_BOSS_HP = 0xA0     # active boss HP in current room (for HUD bar)
ST_TERM_CD = 0xA4     # terminal re-open cooldown

# Player & Enemy Projectiles: 6 slots (0..3 player, 4..5 enemy) * 20 bytes
# Each slot: [active, x_px, y_px, vx_px, vy_and_flags (lo16 signed vy | bit16 heavy_bomb | bit17 is_enemy)]
ST_PROJS = 0xC0       # 0xC0 .. 0x137 (120 bytes)

# Enemies: up to 16 slots * 40 bytes (0x140 .. 0x3BF)
# [0:active, 4:x, 8:y, 12:min_x, 16:max_x, 20:dir, 24:speed, 28:tile_base, 32:ai_type, 36:hp_and_size]
# hp_and_size: low 8 bits = hp, bit 8 = is_32x32, bits 16..23 = shoot_timer
ST_ENEMIES = 0x140

# Room Descriptor Offsets (64 bytes per room)
RM_LVL_W = 0x00
RM_LVL_H = 0x04
RM_SPAWN_X = 0x08
RM_SPAWN_Y = 0x0C
RM_MAP_PTR = 0x10
RM_EN_PTR = 0x14
RM_EN_CNT = 0x18
RM_DOOR_PTR = 0x1C
RM_DOOR_CNT = 0x20
RM_DLG_PTR = 0x24
RM_UPG_ABIL = 0x28
RM_PAR_EN = 0x2C
RM_PAR_TILE = 0x30

# Global Config Offsets (ROM_CONFIG)
CFG_PHYSICS = 0x00
CFG_GRAV = 0x04
CFG_MAXFALL = 0x08
CFG_NUM_PALS = 0x0C
CFG_ROOM_CNT = 0x10
CFG_RULE_CNT = 0x14
CFG_SFX_CNT = 0x18
CFG_VIEW_W = 0x1C
CFG_VIEW_H = 0x20
CFG_VIEW_OX = 0x24
CFG_VIEW_OY = 0x28
CFG_PROJ_TILE = 0x2C
CFG_SFX_COIN = 0x30
CFG_SFX_HURT = 0x34
CFG_SFX_WIN = 0x38
CFG_SFX_JUMP = 0x3C
CFG_BGM_EN = 0x40
CFG_BGM_FSTEP = 0x44
CFG_HERO_H = 0x48          # 16 or 32!
CFG_HERO_A0_SH = 0x4C      # OAM attr0 shape bits (0x0000 or 0x8000)
CFG_HERO_A1_SZ = 0x50      # OAM attr1 size bits (0x4000 or 0x8000)
CFG_MORPH_TILE = 0x54      # 16x16 Morph Ball OBJ tile ID
CFG_START_ABIL = 0x58      # starting abilities bitmask
CFG_SRAM_EN = 0x5C         # 1 if SRAM save/load enabled
CFG_ALPHA_EN = 0x60        # 1 if BG2 hardware alpha blend enabled
CFG_DMA_EN = 0x64          # 1 if Direct Sound DMA PCM enabled
CFG_DMA_TM0 = 0x68         # Timer 0 reload value for sample rate
CFG_DMA_FRAMES = 0x6C      # Sample duration in 60Hz frames


def compile_gba_rom(project: KinoPixelProject, output_path: str) -> BuildReport:
    """Compile a KinoPixelProject v2.0 into a self-contained, bootable, playable .gba ROM."""
    warnings: List[str] = []
    asm = ArmAssembler(base_addr=0x08000000)

    # ------------------------------------------------------------------
    # 1. GBA 192-Byte Hardware Cartridge Header (0x000..0x0BF)
    # ------------------------------------------------------------------
    asm.b("entry_start")
    asm.emit_bytes(GBA_NINTENDO_LOGO)
    clean_title = "".join(c if 32 <= ord(c) < 127 else " " for c in project.title.upper())[:12]
    clean_code = "".join(c if c.isalnum() else "X" for c in project.game_code.upper()).ljust(4, "X")[:4]
    clean_maker = "".join(c if c.isalnum() else "0" for c in project.maker_code.upper()).ljust(2, "0")[:2]

    header_tail = bytearray(32)
    header_tail[0:12] = clean_title.encode("ascii").ljust(12, b"\x00")
    header_tail[12:16] = clean_code.encode("ascii")
    header_tail[16:18] = clean_maker.encode("ascii")
    header_tail[18] = 0x96
    chk = 0
    for b in header_tail[0:29]:
        chk = (chk - b) & 0xFF
    chk = (chk - 0x19) & 0xFF
    header_tail[29] = chk
    asm.emit_bytes(bytes(header_tail))
    assert asm.offset == 0xC0

    # ------------------------------------------------------------------
    # 2. Pack Palettes, BG Tiles, Font, Multi-Size Metasprites, Rooms, Rules, Audio
    # ------------------------------------------------------------------
    bg_pal = [0] * 256
    obj_pal = [0] * 256
    num_pals = max(1, min(14, len(project.palettes)))
    for pi in range(num_pals):
        cols = project.get_palette_colors(pi)
        for ci in range(min(16, len(cols))):
            val = hex_to_bgr555(cols[ci])
            bg_pal[pi * 16 + ci] = val
            obj_pal[pi * 16 + ci] = val
    bg_pal[0] = hex_to_bgr555(project.bg_color_hex)
    # HUD Palette Slot 15
    bg_pal[240 + 0] = 0
    bg_pal[240 + 1] = hex_to_bgr555("#0D1322")  # Dialogue Box dark backdrop
    bg_pal[240 + 2] = hex_to_bgr555("#F8FAFC")  # Crisp white text
    bg_pal[240 + 3] = hex_to_bgr555("#FDE047")  # Gold coin/upgrade
    bg_pal[240 + 4] = hex_to_bgr555("#F43F5E")  # Crimson heart
    bg_pal[240 + 5] = hex_to_bgr555("#161A26")  # GB/GBC Bezel
    bg_pal[240 + 6] = hex_to_bgr555("#34D399")  # Boss / Energy Bar mint

    bg_tiles_bytes = bytearray()
    tile_types = bytearray(256)
    for ti, tile in enumerate(project.tiles[:256]):
        bg_tiles_bytes.extend(_pack_tile_4bpp(tile.pixels))
        tile_types[ti] = tile.tile_type & 0xFF
    if not bg_tiles_bytes:
        bg_tiles_bytes.extend(bytes(32))

    hud_font_bytes = _build_hud_font_tiles()

    # Pack all multi-size OBJ metasprites (16x16 = 4 tiles, 16x32 = 8 tiles, 32x32 = 16 tiles)
    obj_tiles_bytes = bytearray()
    next_obj_tile = 0
    sprite_bases: Dict[int, Tuple[int, int, int, int]] = {}  # idx -> (tile_base, fcount, w, h)

    for si, sp in enumerate(project.sprites):
        w = 32 if sp.width >= 32 else 16
        h = 32 if sp.height >= 32 else 16
        tpf = (w // 8) * (h // 8)
        base = next_obj_tile
        frames = sp.frames or [[[0] * w for _ in range(h)]]
        for fr in frames:
            obj_tiles_bytes.extend(_pack_metasprite_4bpp(fr, w, h))
            next_obj_tile += tpf
        sprite_bases[si] = (base, len(frames), w, h)

    if 0 not in sprite_bases:
        obj_tiles_bytes.extend(bytes(128))
        sprite_bases[0] = (0, 1, 16, 16)
        next_obj_tile = 4

    hero_base, hero_fcount, hero_w, hero_h = sprite_bases[0]
    hero_tpf = (hero_w // 8) * (hero_h // 8)
    hero_a0_sh, hero_a1_sz = _oam_shape_size_flags(hero_w, hero_h)

    # Identify Morph Ball, Projectile, Default Enemy, and Boss sprite tile bases
    morph_idx = project.morph_sprite_index
    if morph_idx < 0 or morph_idx not in sprite_bases:
        morph_idx = next((i for i, s in enumerate(project.sprites) if s.role == "morph"), 0)
    morph_tile_base = sprite_bases.get(morph_idx, sprite_bases[0])[0]

    proj_idx = next((i for i, s in enumerate(project.sprites) if s.role == "projectile"), 2 if 2 in sprite_bases else 0)
    proj_tile_base = sprite_bases.get(proj_idx, sprite_bases[0])[0]
    default_enemy_tile = sprite_bases.get(1, sprite_bases[0])[0]

    # Hero animation table: 4 slots (idle, walk, jump, attack), 6 words each
    anim_order = ["idle", "walk", "jump", "attack"]
    anim_name_to_id = {n: i for i, n in enumerate(anim_order)}
    hero_sprite = project.sprites[0] if project.sprites else None
    anim_table_words: List[int] = []
    for aname in anim_order:
        if hero_sprite:
            clip = hero_sprite.get_clip(aname)
            fids = [max(0, min(hero_fcount - 1, fi)) for fi in clip.frame_indices[:4]] or [0]
            ticks = max(2, min(60, int(round(60.0 / max(1, clip.fps)))))
        else:
            fids, ticks = [0], 10
        fcnt = len(fids)
        while len(fids) < 4:
            fids.append(fids[-1])
        anim_table_words.extend([fcnt, ticks] + [hero_base + fi * hero_tpf for fi in fids])

    # Rooms data preparation (up to 16 rooms!)
    rooms = project.rooms[:16] if project.rooms else [project.level]
    total_enemies_compiled = 0
    room_blobs = []
    for ri, rm in enumerate(rooms):
        rw = max(20, min(64, rm.width))
        rh = max(18, min(32, rm.height))
        map_hw = [0] * (64 * 32)
        for y in range(rh):
            for x in range(rw):
                ti = rm.get_tile(x, y)
                if 0 <= ti < len(project.tiles):
                    pal_slot = project.tiles[ti].palette_index & 0xF
                    map_hw[y * 64 + x] = (ti & 0x3FF) | (pal_slot << 12)

        en_words: List[int] = []
        for ent in rm.entities[:16]:
            sb = sprite_bases.get(ent.sprite_index, (default_enemy_tile, 1, 16, 16))
            is_32 = 1 if (sb[2] == 32 or ent.ai_type == AI_BOSS) else 0
            ex = max(8, min((rw - (4 if is_32 else 2)) * 8, ent.tile_x * 8))
            ey = max(8, min((rh - (4 if is_32 else 2)) * 8, ent.tile_y * 8))
            pr = max(1, ent.patrol_range) * 8
            min_x = max(8, ex - pr)
            max_x = min((rw - (4 if is_32 else 2)) * 8, ex + pr)
            spd = max(1, min(4, ent.speed))
            hp = max(1, min(60, ent.hp))
            hp_sz = (hp & 0xFF) | (is_32 << 8)
            en_words.extend([1, ex, ey, min_x, max_x, 1, spd, sb[0], ent.ai_type & 3, hp_sz])
        total_enemies_compiled += len(rm.entities[:16])

        # Doors: 6 words each [tile_x, tile_y, target_room, target_x_px, target_y_px, req_ability]
        door_words: List[int] = []
        for dr in rm.doors[:8]:
            tr = max(0, min(len(rooms) - 1, dr.target_room))
            door_words.extend([
                dr.tile_x, dr.tile_y, tr,
                max(8, dr.target_x * 8), max(8, dr.target_y * 8),
                dr.req_ability & 0xFF,
            ])

        dlg_bytes = _encode_dialogue_indices(rm.dialogue_text)
        room_blobs.append((ri, rw * 8, rh * 8, max(8, rm.spawn_x * 8), max(8, rm.spawn_y * 8),
                           map_hw, en_words, len(rm.entities[:16]), door_words, len(rm.doors[:8]),
                           dlg_bytes, rm.upgrade_ability & 0xFF, 1 if rm.parallax_enabled else 0,
                           rm.parallax_tile_idx & 0xFF))

    # Button Rules
    rules_words: List[int] = []
    for r in [x for x in project.button_rules if x.enabled][:32]:
        mask = BUTTON_BITS.get(r.button.upper(), 0)
        if mask == 0:
            continue
        anim_id = anim_name_to_id.get(r.anim_name.lower(), 0xFF) if r.anim_name else 0xFF
        sfx_byte = (r.sfx_index & 0xFF) if (0 <= r.sfx_index < len(project.sfx_list)) else 0xFF
        packed = max(0, min(255, int(r.param))) | (anim_id << 8) | (sfx_byte << 16)
        rules_words.extend([mask, int(r.trigger) & 3, int(r.action) & 0xFF, packed])
    rules_count = len(rules_words) // 4

    # PSG SFX & Sequence Genie BGM & Direct Sound DMA PCM
    sfx_words: List[int] = []
    for patch in project.sfx_list[:16]:
        ch, cl, ch_reg, cx = patch.to_gba_regs()
        sfx_words.extend([ch, cl, ch_reg, cx])
    sfx_count = len(sfx_words) // 4

    def find_sfx_idx(keyword: str, fallback: int) -> int:
        for idx, p in enumerate(project.sfx_list):
            if keyword in p.name.lower():
                return idx
        return fallback if fallback < sfx_count else 0xFF

    bgm_fstep, bgm_steps = compile_genie_to_gba_bgm(project.sequence_genie)
    bgm_words: List[int] = []
    for c2l, c2h, dflag in bgm_steps:
        bgm_words.extend([c2l, c2h, dflag])

    dma_pcm_bytes = generate_direct_sound_pcm(project.direct_sound)
    dma_sr = max(4096, min(16384, int(project.direct_sound.sample_rate)))
    dma_tm0_reload = (65536 - int(round(16777216.0 / dma_sr))) & 0xFFFF
    dma_dur_frames = max(8, min(90, int(round((len(dma_pcm_bytes) / float(dma_sr)) * 60.0))))

    is_gb_frame = project.target_system in ("GB", "GBC")
    view_w, view_h = (160, 144) if is_gb_frame else (240, 160)
    view_ox, view_oy = (40, 8) if is_gb_frame else (0, 0)

    config_words = [
        1 if project.physics_mode == "topdown" else 0,     # CFG_PHYSICS
        max(8, min(128, int(project.gravity))),            # CFG_GRAV
        max(256, min(1536, int(project.max_fall_speed))),  # CFG_MAXFALL
        num_pals,                                          # CFG_NUM_PALS
        len(rooms),                                        # CFG_ROOM_CNT
        rules_count,                                       # CFG_RULE_CNT
        sfx_count,                                         # CFG_SFX_CNT
        view_w,                                            # CFG_VIEW_W
        view_h,                                            # CFG_VIEW_H
        view_ox,                                           # CFG_VIEW_OX
        view_oy,                                           # CFG_VIEW_OY
        proj_tile_base,                                    # CFG_PROJ_TILE
        find_sfx_idx("coin", 1),                           # CFG_SFX_COIN
        find_sfx_idx("hurt", 4),                           # CFG_SFX_HURT
        find_sfx_idx("clear", 5),                          # CFG_SFX_WIN
        find_sfx_idx("jump", 0),                           # CFG_SFX_JUMP
        1 if project.sequence_genie.enabled_in_rom else 0, # CFG_BGM_EN
        bgm_fstep,                                         # CFG_BGM_FSTEP
        hero_h,                                            # CFG_HERO_H (16 or 32)
        hero_a0_sh,                                        # CFG_HERO_A0_SH
        hero_a1_sz,                                        # CFG_HERO_A1_SZ
        morph_tile_base,                                   # CFG_MORPH_TILE
        project.starting_abilities & 0xFF,                 # CFG_START_ABIL
        1 if project.sram_save_enabled else 0,             # CFG_SRAM_EN
        1 if project.alpha_blend_enabled else 0,           # CFG_ALPHA_EN
        1 if project.direct_sound.enabled else 0,          # CFG_DMA_EN
        dma_tm0_reload,                                    # CFG_DMA_TM0
        dma_dur_frames,                                    # CFG_DMA_FRAMES
    ]

    # ------------------------------------------------------------------
    # 3. Emit ARM7TDMI Game Engine Kernel
    # ------------------------------------------------------------------
    asm.label("entry_start")
    asm.ldr_lit(SP, 0x03007F00)
    asm.ldr_lit(R11, 0x03000000)
    asm.ldr_lit(R10, "ROM_CONFIG")

    # Zero-clear IWRAM state struct (0x03000000..0x03000400)
    asm.mov_reg(R0, R11)
    asm.mov_imm(R1, 0)
    asm.mov_imm(R2, 256)
    asm.label("zero_iwram_loop")
    asm.str(R1, R0, 0)
    asm.add_imm(R0, R0, 4)
    asm.sub_imm(R2, R2, 1, s=True)
    asm.b("zero_iwram_loop", "NE")

    # Init Hardware PSG + Direct Sound A (REG_SOUNDCNT_X/L/H)
    asm.ldr_lit(R0, 0x04000084)     # REG_SOUNDCNT_X
    asm.mov_imm(R1, 0x80)
    asm.strh(R1, R0, 0)
    asm.ldr_lit(R0, 0x04000080)     # REG_SOUNDCNT_L
    asm.ldr_lit(R1, 0xFF77)
    asm.strh(R1, R0, 0)
    asm.ldr_lit(R0, 0x04000082)     # REG_SOUNDCNT_H: PSG 100% + Direct Sound A L/R + Timer 0 + FIFO Reset
    asm.ldr_lit(R1, 0x0B06)
    asm.strh(R1, R0, 0)

    # Copy BG Palette, OBJ Palette, BG Tiles, HUD Font, OBJ Metasprites
    asm.ldr_lit(R0, "ROM_PAL_BG")
    asm.ldr_lit(R1, 0x05000000)
    asm.mov_imm(R2, 256)
    asm.bl("copy_halfwords")

    asm.ldr_lit(R0, "ROM_PAL_OBJ")
    asm.ldr_lit(R1, 0x05000200)
    asm.mov_imm(R2, 256)
    asm.bl("copy_halfwords")

    asm.ldr_lit(R0, "ROM_BG_TILES")
    asm.ldr_lit(R1, 0x06000000)
    asm.ldr_lit(R2, len(bg_tiles_bytes) // 2)
    asm.bl("copy_halfwords")

    asm.ldr_lit(R0, "ROM_HUD_FONT")
    asm.ldr_lit(R1, 0x06004000)
    asm.ldr_lit(R2, len(hud_font_bytes) // 2)
    asm.bl("copy_halfwords")

    asm.ldr_lit(R0, "ROM_OBJ_TILES")
    asm.ldr_lit(R1, 0x06010000)
    asm.ldr_lit(R2, len(obj_tiles_bytes) // 2)
    asm.bl("copy_halfwords")

    asm.bl("hide_all_oam")

    # Initialize fresh game state, then auto-load valid SRAM save if enabled
    asm.bl("reset_new_game")
    asm.ldr(R0, R10, CFG_SRAM_EN)
    asm.cmp_imm(R0, 0)
    asm.bl("load_from_sram", "NE")

    # Configure Display: Mode 0 | 1D OBJ (0x40) | BG0 (0x100) | BG1 (0x200) | BG2 (0x400) | OBJ (0x1000) = 0x1740
    # BG0CNT = 0x5C01 (64x32 SBB 28, prio 1), BG1CNT = 0x1E04 (32x32 CBB 1 SBB 30, prio 0), BG2CNT = 0x1A02 (32x32 SBB 26, prio 2)
    asm.ldr_lit(R0, 0x04000008)
    asm.ldr_lit(R1, 0x5C01)
    asm.strh(R1, R0, 0)
    asm.ldr_lit(R1, 0x1E04)
    asm.strh(R1, R0, 2)
    asm.ldr_lit(R1, 0x1A02)
    asm.strh(R1, R0, 4)

    # Optional Hardware Alpha Blending for BG2 atmospheric parallax (REG_BLDCNT 0x04000050, REG_BLDALPHA 0x04000052)
    asm.ldr(R0, R10, CFG_ALPHA_EN)
    asm.cmp_imm(R0, 0)
    asm.b("skip_alpha_init", "EQ")
    asm.ldr_lit(R0, 0x04000050)
    asm.ldr_lit(R1, 0x2044)  # BG2 alpha blend over Backdrop
    asm.strh(R1, R0, 0)
    asm.ldr_lit(R1, 0x0A08)  # EVA=8, EVB=10
    asm.strh(R1, R0, 2)
    asm.label("skip_alpha_init")

    asm.ldr_lit(R0, 0x04000000)
    asm.ldr_lit(R1, 0x1740)
    asm.strh(R1, R0, 0)

    # ==================================================================
    # Main 60 FPS Game Loop
    # ==================================================================
    asm.label("main_loop")
    asm.ldr_lit(R0, 0x04000006)
    asm.label("wait_vdraw")
    asm.ldrh(R1, R0, 0)
    asm.cmp_imm(R1, 160)
    asm.b("wait_vdraw", "GE")
    asm.label("wait_vblank")
    asm.ldrh(R1, R0, 0)
    asm.cmp_imm(R1, 160)
    asm.b("wait_vblank", "LT")

    # Global frame tick & Direct Sound DMA stop countdown
    asm.ldr(R0, R11, ST_FRAME)
    asm.add_imm(R0, R0, 1)
    asm.str(R0, R11, ST_FRAME)

    asm.ldr(R0, R11, ST_DMA_TIMER)
    asm.cmp_imm(R0, 0)
    asm.b("dma_not_active", "LE")
    asm.sub_imm(R0, R0, 1, s=True)
    asm.str(R0, R11, ST_DMA_TIMER)
    asm.b("dma_not_active", "GT")
    # Stop DMA1 & Timer 0 cleanly when sample finishes
    asm.mov_imm(R1, 0)
    asm.ldr_lit(R2, 0x040000C6)
    asm.strh(R1, R2, 0)
    asm.ldr_lit(R2, 0x04000102)
    asm.strh(R1, R2, 0)
    asm.label("dma_not_active")

    # Read REG_KEYINPUT (0x04000130)
    asm.ldr(R2, R11, ST_CURR_K)
    asm.str(R2, R11, ST_PREV_K)
    asm.ldr_lit(R0, 0x04000130)
    asm.ldrh(R1, R0, 0)
    asm.mvn_reg(R1, R1)
    asm.ldr_lit(R3, 0x03FF)
    asm.and_reg(R1, R1, R3)
    asm.str(R1, R11, ST_CURR_K)
    asm.bic_reg(R3, R1, R2)
    asm.str(R3, R11, ST_PRESS_K)
    asm.bic_reg(R3, R2, R1)
    asm.str(R3, R11, ST_REL_K)

    # If Dialogue Box is open -> dismiss on A or B press!
    asm.ldr(R0, R11, ST_DIALOG_ON)
    asm.cmp_imm(R0, 0)
    asm.b("not_dialog", "EQ")
    asm.ldr(R1, R11, ST_PRESS_K)
    asm.tst_imm(R1, 0x03)  # A or B
    asm.b("after_gameplay", "EQ")
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_DIALOG_ON)
    asm.mov_imm(R0, 35)
    asm.str(R0, R11, ST_TERM_CD)
    asm.bl("clear_dialogue_box")
    asm.b("after_gameplay")
    asm.label("not_dialog")

    # If Won -> press START or A to restart fresh
    asm.ldr(R0, R11, ST_WON)
    asm.cmp_imm(R0, 0)
    asm.b("not_won", "EQ")
    asm.ldr(R1, R11, ST_PRESS_K)
    asm.tst_imm(R1, 0x09)
    asm.b("after_gameplay", "EQ")
    asm.bl("reset_new_game")
    asm.b("after_gameplay")
    asm.label("not_won")

    # Decrement timers
    for st_off in (ST_INVULN, ST_ALOCK, ST_DASH, ST_MELEE, ST_SHOOT_CD, ST_MSG_TIMER, ST_DOOR_CD, ST_TERM_CD):
        asm.ldr(R0, R11, st_off)
        asm.cmp_imm(R0, 0)
        asm.sub_imm(R0, R0, 1, cond="GT")
        asm.str(R0, R11, st_off, cond="GT")

    # Per-frame defaults: ST_MOVED=0, ST_AIM_Y=0 (unless UP held -> -1)
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_MOVED)
    asm.str(R0, R11, ST_AIM_Y)
    asm.ldr(R1, R11, ST_CURR_K)
    asm.tst_imm(R1, BUTTON_BITS["UP"])
    asm.mvn_imm(R2, 0, cond="NE")  # -1 = aim UP!
    asm.str(R2, R11, ST_AIM_Y, cond="NE")

    asm.ldr(R1, R11, ST_DASH)
    asm.cmp_imm(R1, 0)
    asm.b("skip_vx_clear", "GT")
    asm.str(R0, R11, ST_VX)
    asm.ldr(R2, R10, CFG_PHYSICS)
    asm.cmp_imm(R2, 1)
    asm.str(R0, R11, ST_VY, cond="EQ")
    asm.label("skip_vx_clear")

    asm.bl("process_button_rules")

    asm.ldr(R0, R11, ST_PAUSED)
    asm.cmp_imm(R0, 0)
    asm.b("after_gameplay", "NE")

    asm.bl("update_player_physics")
    asm.bl("check_tile_triggers")
    asm.bl("update_projectiles")
    asm.bl("update_enemies")
    asm.bl("update_player_anim")
    asm.bl("update_bgm_genie")

    asm.label("after_gameplay")
    asm.bl("update_camera")
    asm.bl("render_oam")
    asm.bl("render_hud")
    asm.b("main_loop")
    asm.pool()

    # ==================================================================
    # Helper: hero_height -> R0 (16 if morphed else CFG_HERO_H)
    # ==================================================================
    asm.label("get_hero_h")
    asm.ldr(R0, R11, ST_MORPHED)
    asm.cmp_imm(R0, 0)
    asm.mov_imm(R0, 16, cond="NE")
    asm.ldr(R0, R10, CFG_HERO_H, cond="EQ")
    asm.bx(LR)

    # ==================================================================
    # Subroutine: process_button_rules (all 17 actions incl. Morph, AimUp, Bomb, WallJump!)
    # ==================================================================
    asm.label("process_button_rules")
    asm.push([R4, R5, R6, R7, R8, R9, LR])
    asm.ldr(R4, R10, CFG_RULE_CNT)
    asm.cmp_imm(R4, 0)
    asm.b("pbr_done", "LE")
    asm.ldr_lit(R5, "ROM_RULES")

    asm.label("pbr_loop")
    asm.ldr(R6, R5, 0)
    asm.ldr(R7, R5, 4)
    asm.ldr(R8, R5, 8)
    asm.ldr(R9, R5, 12)

    asm.cmp_imm(R7, TRIGGER_HELD)
    asm.ldr(R0, R11, ST_CURR_K, cond="EQ")
    asm.cmp_imm(R7, TRIGGER_PRESSED)
    asm.ldr(R0, R11, ST_PRESS_K, cond="EQ")
    asm.cmp_imm(R7, TRIGGER_RELEASED)
    asm.ldr(R0, R11, ST_REL_K, cond="EQ")

    asm.tst_reg(R0, R6)
    asm.b("pbr_next", "EQ")

    asm.ldr(R0, R11, ST_PAUSED)
    asm.cmp_imm(R0, 0)
    asm.b("pbr_not_paused", "EQ")
    asm.cmp_imm(R8, ACTION_PAUSE)
    asm.b("pbr_not_paused", "EQ")
    asm.cmp_imm(R8, ACTION_RESET_LEVEL)
    asm.b("pbr_next", "NE")
    asm.label("pbr_not_paused")

    asm.and_imm(R1, R9, 0xFF)
    asm.mov_reg(R2, R9, "LSR", 8)
    asm.and_imm(R2, R2, 0xFF)
    asm.mov_reg(R3, R9, "LSR", 16)
    asm.and_imm(R3, R3, 0xFF)

    # ACTION_MOVE_LEFT (1)
    asm.cmp_imm(R8, ACTION_MOVE_LEFT)
    asm.b("act_not_left", "NE")
    asm.mov_reg(R0, R1, "LSL", 7)
    asm.rsb_imm(R0, R0, 0)
    asm.str(R0, R11, ST_VX)
    asm.mov_imm(R0, 1)
    asm.str(R0, R11, ST_FACING)
    asm.str(R0, R11, ST_MOVED)
    asm.b("pbr_post_fx")
    asm.label("act_not_left")

    # ACTION_MOVE_RIGHT (2)
    asm.cmp_imm(R8, ACTION_MOVE_RIGHT)
    asm.b("act_not_right", "NE")
    asm.mov_reg(R0, R1, "LSL", 7)
    asm.str(R0, R11, ST_VX)
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_FACING)
    asm.mov_imm(R0, 1)
    asm.str(R0, R11, ST_MOVED)
    asm.b("pbr_post_fx")
    asm.label("act_not_right")

    # ACTION_MOVE_UP (3)
    asm.cmp_imm(R8, ACTION_MOVE_UP)
    asm.b("act_not_up", "NE")
    asm.ldr(R6, R10, CFG_PHYSICS)
    asm.cmp_imm(R6, 1)
    asm.b("act_up_aim", "NE")
    asm.mov_reg(R0, R1, "LSL", 7)
    asm.rsb_imm(R0, R0, 0)
    asm.str(R0, R11, ST_VY)
    asm.mov_imm(R0, 1)
    asm.str(R0, R11, ST_MOVED)
    asm.b("pbr_post_fx")
    asm.label("act_up_aim")
    asm.mvn_imm(R0, 0)  # -1 aim up
    asm.str(R0, R11, ST_AIM_Y)
    asm.b("pbr_post_fx")
    asm.label("act_not_up")

    # ACTION_MOVE_DOWN (4)
    asm.cmp_imm(R8, ACTION_MOVE_DOWN)
    asm.b("act_not_down", "NE")
    asm.ldr(R6, R10, CFG_PHYSICS)
    asm.cmp_imm(R6, 1)
    asm.b("act_down_aim", "NE")
    asm.mov_reg(R0, R1, "LSL", 7)
    asm.str(R0, R11, ST_VY)
    asm.mov_imm(R0, 1)
    asm.str(R0, R11, ST_MOVED)
    asm.b("pbr_post_fx")
    asm.label("act_down_aim")
    asm.mov_imm(R0, 1)  # +1 aim down in air
    asm.str(R0, R11, ST_AIM_Y)
    asm.b("pbr_post_fx")
    asm.label("act_not_down")

    # ACTION_JUMP (5) — supports High Jump Boots AND Wall-Jump!
    asm.cmp_imm(R8, ACTION_JUMP)
    asm.b("act_not_jump", "NE")
    asm.ldr(R0, R11, ST_GROUND)
    asm.cmp_imm(R0, 0)
    asm.b("act_do_jump", "NE")
    # Airborne: check Wall-Jump if ABIL_WALL_JUMP unlocked!
    asm.ldr(R0, R11, ST_ABILITIES)
    asm.tst_imm(R0, ABIL_WALL_JUMP)
    asm.b("pbr_next", "EQ")
    asm.push([R1, R2, R3])
    asm.ldr(R0, R11, ST_PX)
    asm.mov_reg(R0, R0, "ASR", 8)
    asm.sub_imm(R0, R0, 2)            # test left wall
    asm.ldr(R1, R11, ST_PY)
    asm.mov_reg(R1, R1, "ASR", 8)
    asm.add_imm(R1, R1, 8)
    asm.bl("tile_type_at_px")
    asm.cmp_imm(R0, TILE_SOLID)
    asm.b("act_wj_right", "EQ")
    asm.ldr(R0, R11, ST_PX)
    asm.mov_reg(R0, R0, "ASR", 8)
    asm.add_imm(R0, R0, 17)           # test right wall
    asm.ldr(R1, R11, ST_PY)
    asm.mov_reg(R1, R1, "ASR", 8)
    asm.add_imm(R1, R1, 8)
    asm.bl("tile_type_at_px")
    asm.cmp_imm(R0, TILE_SOLID)
    asm.b("act_wj_left", "EQ")
    asm.pop([R1, R2, R3])
    asm.b("pbr_next")

    asm.label("act_wj_right")
    asm.pop([R1, R2, R3])
    asm.ldr_lit(R0, 512)
    asm.str(R0, R11, ST_VX)
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_FACING)
    asm.mov_imm(R0, 7)
    asm.str(R0, R11, ST_DASH)
    asm.b("act_do_jump")

    asm.label("act_wj_left")
    asm.pop([R1, R2, R3])
    asm.ldr_lit(R0, (-512) & 0xFFFFFFFF)
    asm.str(R0, R11, ST_VX)
    asm.mov_imm(R0, 1)
    asm.str(R0, R11, ST_FACING)
    asm.mov_imm(R0, 7)
    asm.str(R0, R11, ST_DASH)

    asm.label("act_do_jump")
    asm.mov_reg(R0, R1, "LSL", 7)
    asm.add_imm(R0, R0, 192)
    # High Jump Boots bonus (+192)
    asm.ldr(R6, R11, ST_ABILITIES)
    asm.tst_imm(R6, ABIL_HIGH_JUMP)
    asm.add_imm(R0, R0, 192, cond="NE")
    asm.rsb_imm(R0, R0, 0)
    asm.str(R0, R11, ST_VY)
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_GROUND)
    asm.b("pbr_post_fx")
    asm.label("act_not_jump")

    # ACTION_DASH (6)
    asm.cmp_imm(R8, ACTION_DASH)
    asm.b("act_not_dash", "NE")
    asm.mov_reg(R0, R1, "LSL", 7)
    asm.add_imm(R0, R0, 128)
    asm.ldr(R6, R11, ST_FACING)
    asm.cmp_imm(R6, 0)
    asm.rsb_imm(R0, R0, 0, cond="NE")
    asm.str(R0, R11, ST_VX)
    asm.mov_imm(R0, 10)
    asm.str(R0, R11, ST_DASH)
    asm.b("pbr_post_fx")
    asm.label("act_not_dash")

    # ACTION_SHOOT (7) — 8-Way / Diagonal Aim Arm Cannon!
    asm.cmp_imm(R8, ACTION_SHOOT)
    asm.b("act_not_shoot", "NE")
    asm.ldr(R0, R11, ST_SHOOT_CD)
    asm.cmp_imm(R0, 0)
    asm.b("pbr_next", "GT")
    asm.mov_imm(R0, 10)
    asm.str(R0, R11, ST_SHOOT_CD)
    asm.push([R1, R2, R3])
    asm.mov_reg(R0, R1)
    asm.mov_imm(R1, 0)                # normal shot (0)
    asm.bl("spawn_projectile")
    asm.pop([R1, R2, R3])
    asm.b("pbr_post_fx")
    asm.label("act_not_shoot")

    # ACTION_MELEE (8)
    asm.cmp_imm(R8, ACTION_MELEE)
    asm.b("act_not_melee", "NE")
    asm.mov_imm(R0, 14)
    asm.str(R0, R11, ST_MELEE)
    asm.b("pbr_post_fx")
    asm.label("act_not_melee")

    # ACTION_PALETTE_NEXT (9)
    asm.cmp_imm(R8, ACTION_PALETTE_NEXT)
    asm.b("act_not_pal", "NE")
    asm.ldr(R0, R11, ST_PAL)
    asm.add_imm(R0, R0, 1)
    asm.ldr(R6, R10, CFG_NUM_PALS)
    asm.cmp_reg(R0, R6)
    asm.mov_imm(R0, 0, cond="GE")
    asm.str(R0, R11, ST_PAL)
    asm.b("pbr_post_fx")
    asm.label("act_not_pal")

    # ACTION_RESET_LEVEL (12)
    asm.cmp_imm(R8, ACTION_RESET_LEVEL)
    asm.b("act_not_reset", "NE")
    asm.push([R2, R3])
    asm.bl("reset_new_game")
    asm.pop([R2, R3])
    asm.b("pbr_post_fx")
    asm.label("act_not_reset")

    # ACTION_PAUSE (13)
    asm.cmp_imm(R8, ACTION_PAUSE)
    asm.b("act_not_pause", "NE")
    asm.ldr(R0, R11, ST_PAUSED)
    asm.eor_imm(R0, R0, 1)
    asm.str(R0, R11, ST_PAUSED)
    asm.b("pbr_post_fx")
    asm.label("act_not_pause")

    # ACTION_MORPH_BALL (14) — Toggles 16x32 Standing <-> 16x16 Morph Ball!
    asm.cmp_imm(R8, ACTION_MORPH_BALL)
    asm.b("act_not_morph", "NE")
    asm.ldr(R0, R11, ST_ABILITIES)
    asm.tst_imm(R0, ABIL_MORPH_BALL)
    asm.b("pbr_next", "EQ")
    asm.ldr(R0, R11, ST_MORPHED)
    asm.cmp_imm(R0, 0)
    asm.b("act_unmorph", "NE")
    # Enter Morph Ball: shift py down by (CFG_HERO_H - 16) << 8 so feet stay planted!
    asm.mov_imm(R0, 1)
    asm.str(R0, R11, ST_MORPHED)
    asm.ldr(R6, R10, CFG_HERO_H)
    asm.sub_imm(R6, R6, 16)
    asm.ldr(R0, R11, ST_PY)
    asm.add_reg(R0, R0, R6, "LSL", 8)
    asm.str(R0, R11, ST_PY)
    asm.b("pbr_post_fx")
    asm.label("act_unmorph")
    # Check ceiling clearance before unmorphing (if hero is 32px tall)
    asm.ldr(R6, R10, CFG_HERO_H)
    asm.cmp_imm(R6, 16)
    asm.b("act_unmorph_ok", "LE")
    asm.push([R1, R2, R3])
    asm.ldr(R0, R11, ST_PX)
    asm.mov_reg(R0, R0, "ASR", 8)
    asm.add_imm(R0, R0, 8)
    asm.ldr(R1, R11, ST_PY)
    asm.mov_reg(R1, R1, "ASR", 8)
    asm.sub_imm(R1, R1, 14)
    asm.bl("tile_type_at_px")
    asm.cmp_imm(R0, TILE_SOLID)
    asm.pop([R1, R2, R3])
    asm.b("pbr_next", "EQ")  # Ceiling blocked! Stay morphed!
    asm.ldr(R6, R10, CFG_HERO_H)
    asm.sub_imm(R6, R6, 16)
    asm.ldr(R0, R11, ST_PY)
    asm.sub_reg(R0, R0, R6, "LSL", 8)
    asm.str(R0, R11, ST_PY)
    asm.label("act_unmorph_ok")
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_MORPHED)
    asm.b("pbr_post_fx")
    asm.label("act_not_morph")

    # ACTION_AIM_UP (15) — Hold L to lock diagonal/upward aim!
    asm.cmp_imm(R8, ACTION_AIM_UP)
    asm.b("act_not_aimup", "NE")
    asm.mvn_imm(R0, 0)
    asm.str(R0, R11, ST_AIM_Y)
    asm.b("pbr_post_fx")
    asm.label("act_not_aimup")

    # ACTION_BOMB (16) — Heavy Missile / Morph Bomb (3x damage + shatters TILE_BREAKABLE + DMA!)
    asm.cmp_imm(R8, ACTION_BOMB)
    asm.b("act_not_bomb", "NE")
    asm.ldr(R0, R11, ST_SHOOT_CD)
    asm.cmp_imm(R0, 0)
    asm.b("pbr_next", "GT")
    asm.mov_imm(R0, 14)
    asm.str(R0, R11, ST_SHOOT_CD)
    asm.push([R1, R2, R3])
    asm.mov_reg(R0, R1)
    asm.mov_imm(R1, 1)  # heavy missile/bomb flag!
    asm.bl("spawn_projectile")
    asm.pop([R1, R2, R3])
    asm.b("pbr_post_fx")
    asm.label("act_not_bomb")

    # ACTION_INTERACT (17)
    asm.cmp_imm(R8, ACTION_INTERACT)
    asm.b("act_not_inter", "NE")
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_TERM_CD)
    asm.b("pbr_post_fx")
    asm.label("act_not_inter")

    asm.label("pbr_post_fx")
    asm.cmp_imm(R2, 4)
    asm.b("pbr_no_anim", "GE")
    asm.cmp_imm(R7, TRIGGER_PRESSED)
    asm.b("pbr_no_anim", "NE")
    asm.str(R2, R11, ST_ANIM)
    asm.mov_imm(R0, 14)
    asm.str(R0, R11, ST_ALOCK)
    asm.label("pbr_no_anim")

    asm.cmp_imm(R3, 0xFF)
    asm.b("pbr_next", "EQ")
    asm.mov_reg(R0, R3)
    asm.bl("play_sfx")

    asm.label("pbr_next")
    asm.add_imm(R5, R5, 16)
    asm.sub_imm(R4, R4, 1, s=True)
    asm.b("pbr_loop", "NE")

    asm.label("pbr_done")
    asm.pop([R4, R5, R6, R7, R8, R9, PC])
    asm.pool()

    # ==================================================================
    # Subroutine: update_player_physics (Supports 16x16 & 16x32 dynamic hitbox!)
    # ==================================================================
    asm.label("update_player_physics")
    asm.push([R4, R5, R6, R7, R8, R9, LR])
    asm.bl("get_hero_h")
    asm.mov_reg(R9, R0)               # R9 = active hero height (16 or 32)
    asm.ldr(R12, R11, ST_ROOM_PTR)

    # Gravity
    asm.ldr(R0, R10, CFG_PHYSICS)
    asm.cmp_imm(R0, 0)
    asm.b("phys_no_grav", "NE")
    asm.ldr(R1, R11, ST_VY)
    asm.ldr(R2, R10, CFG_GRAV)
    asm.add_reg(R1, R1, R2)
    asm.ldr(R3, R10, CFG_MAXFALL)
    asm.cmp_reg(R1, R3)
    asm.mov_reg(R1, R3, cond="GT")
    asm.str(R1, R11, ST_VY)
    asm.label("phys_no_grav")

    # Horizontal Move
    asm.ldr(R4, R11, ST_PX)
    asm.ldr(R5, R11, ST_VX)
    asm.add_reg(R6, R4, R5)
    asm.cmp_imm(R6, 0)
    asm.mov_imm(R6, 0, cond="LT")
    asm.ldr(R0, R12, RM_LVL_W)
    asm.sub_imm(R0, R0, 16)
    asm.mov_reg(R0, R0, "LSL", 8)
    asm.cmp_reg(R6, R0)
    asm.mov_reg(R6, R0, cond="GT")

    asm.mov_reg(R7, R6, "ASR", 8)
    asm.ldr(R8, R11, ST_PY)
    asm.mov_reg(R8, R8, "ASR", 8)
    asm.cmp_imm(R5, 0)
    asm.b("phys_x_ok", "EQ")
    asm.b("phys_x_left", "LT")

    # Right probe at y+2, y+(h/2), y+(h-3)
    asm.add_imm(R0, R7, 13)
    asm.add_imm(R1, R8, 2)
    asm.bl("is_solid_px")
    asm.cmp_imm(R0, 0)
    asm.b("phys_x_blocked", "NE")
    asm.add_imm(R0, R7, 13)
    asm.add_reg(R1, R8, R9, "ASR", 1)
    asm.bl("is_solid_px")
    asm.cmp_imm(R0, 0)
    asm.b("phys_x_blocked", "NE")
    asm.add_imm(R0, R7, 13)
    asm.add_reg(R1, R8, R9)
    asm.sub_imm(R1, R1, 3)
    asm.bl("is_solid_px")
    asm.cmp_imm(R0, 0)
    asm.b("phys_x_blocked", "NE")
    asm.b("phys_x_ok")

    asm.label("phys_x_left")
    asm.add_imm(R0, R7, 2)
    asm.add_imm(R1, R8, 2)
    asm.bl("is_solid_px")
    asm.cmp_imm(R0, 0)
    asm.b("phys_x_blocked", "NE")
    asm.add_imm(R0, R7, 2)
    asm.add_reg(R1, R8, R9, "ASR", 1)
    asm.bl("is_solid_px")
    asm.cmp_imm(R0, 0)
    asm.b("phys_x_blocked", "NE")
    asm.add_imm(R0, R7, 2)
    asm.add_reg(R1, R8, R9)
    asm.sub_imm(R1, R1, 3)
    asm.bl("is_solid_px")
    asm.cmp_imm(R0, 0)
    asm.b("phys_x_blocked", "NE")
    asm.b("phys_x_ok")

    asm.label("phys_x_blocked")
    asm.mov_reg(R6, R4)
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_VX)
    asm.label("phys_x_ok")
    asm.str(R6, R11, ST_PX)

    # Vertical Move
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_GROUND)
    asm.ldr(R4, R11, ST_PY)
    asm.ldr(R5, R11, ST_VY)
    asm.add_reg(R6, R4, R5)
    asm.cmp_imm(R6, 0)
    asm.mov_imm(R6, 0, cond="LT")

    asm.mov_reg(R8, R6, "ASR", 8)
    asm.ldr(R12, R11, ST_ROOM_PTR)
    asm.ldr(R0, R12, RM_LVL_H)
    asm.sub_reg(R0, R0, R9)
    asm.add_imm(R0, R0, 2)
    asm.cmp_reg(R8, R0)
    asm.b("phys_not_pit", "LT")
    asm.bl("damage_respawn")
    asm.b("phys_done")
    asm.label("phys_not_pit")

    asm.ldr(R7, R11, ST_PX)
    asm.mov_reg(R7, R7, "ASR", 8)
    asm.cmp_imm(R5, 0)
    asm.b("phys_y_up", "LT")

    # Moving down: feet at new_y + R9 (16 or 32)
    for ox, lbl_nxt in ((3, "phys_chk_r"), (12, "phys_y_ok")):
        asm.add_imm(R0, R7, ox)
        asm.add_reg(R1, R8, R9)
        asm.bl("tile_type_at_px")
        asm.cmp_imm(R0, TILE_SOLID)
        asm.b("phys_land", "EQ")
        asm.cmp_imm(R0, TILE_BREAKABLE)
        asm.b("phys_land", "EQ")
        asm.cmp_imm(R0, TILE_ONEWAY)
        asm.b(lbl_nxt, "NE")
        asm.mov_reg(R2, R4, "ASR", 8)
        asm.add_reg(R2, R2, R9)
        asm.add_reg(R3, R8, R9)
        asm.bic_imm(R3, R3, 7)
        asm.cmp_reg(R2, R3)
        asm.b("phys_land", "LE")
        if lbl_nxt != "phys_y_ok":
            asm.label(lbl_nxt)

    asm.label("phys_land")
    asm.add_reg(R0, R8, R9)
    asm.bic_imm(R0, R0, 7)
    asm.sub_reg(R0, R0, R9)
    asm.mov_reg(R6, R0, "LSL", 8)
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_VY)
    asm.mov_imm(R0, 1)
    asm.str(R0, R11, ST_GROUND)
    asm.b("phys_y_ok")

    asm.label("phys_y_up")
    asm.add_imm(R0, R7, 3)
    asm.add_imm(R1, R8, 2)
    asm.bl("is_solid_px")
    asm.cmp_imm(R0, 0)
    asm.b("phys_bonk", "NE")
    asm.add_imm(R0, R7, 12)
    asm.add_imm(R1, R8, 2)
    asm.bl("is_solid_px")
    asm.cmp_imm(R0, 0)
    asm.b("phys_y_ok", "EQ")
    asm.label("phys_bonk")
    asm.mov_reg(R6, R4)
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_VY)

    asm.label("phys_y_ok")
    asm.str(R6, R11, ST_PY)

    asm.label("phys_done")
    asm.pop([R4, R5, R6, R7, R8, R9, PC])

    # Helper: is_solid_px(R0=x, R1=y) -> R0=1 if SOLID or BREAKABLE else 0
    asm.label("is_solid_px")
    asm.push([LR])
    asm.bl("tile_type_at_px")
    asm.cmp_imm(R0, TILE_SOLID)
    asm.mov_imm(R0, 1, cond="EQ")
    asm.pop([PC], cond="EQ")
    asm.cmp_imm(R0, TILE_BREAKABLE)
    asm.mov_imm(R0, 1, cond="EQ")
    asm.mov_imm(R0, 0, cond="NE")
    asm.pop([PC])

    # ==================================================================
    # Subroutine: check_tile_triggers (COIN, HAZARD, BOUNCE, GOAL, DOOR, SAVE, UPGRADE, TERMINAL!)
    # ==================================================================
    asm.label("check_tile_triggers")
    asm.push([R4, R5, R6, R7, R8, LR])
    asm.ldr(R4, R11, ST_PX)
    asm.mov_reg(R4, R4, "ASR", 8)
    asm.ldr(R5, R11, ST_PY)
    asm.mov_reg(R5, R5, "ASR", 8)
    asm.bl("get_hero_h")
    asm.mov_reg(R8, R0)               # hero height (16 or 32)

    for tag, is_bottom in (("pt1", False), ("pt2", True)):
        asm.add_imm(R6, R4, 8)
        if is_bottom:
            asm.add_reg(R7, R5, R8)
            asm.sub_imm(R7, R7, 3)
        else:
            asm.add_imm(R7, R5, 8)
        asm.mov_reg(R0, R6)
        asm.mov_reg(R1, R7)
        asm.bl("tile_type_at_px")

        # COIN
        asm.cmp_imm(R0, TILE_COIN)
        asm.b(f"t_nc_{tag}", "NE")
        asm.mov_reg(R0, R6, "ASR", 3)
        asm.mov_reg(R1, R7, "ASR", 3)
        asm.mov_imm(R2, 0)
        asm.bl("set_bg0_tile")
        asm.ldr(R0, R11, ST_COINS)
        asm.add_imm(R0, R0, 1)
        asm.str(R0, R11, ST_COINS)
        asm.ldr(R0, R11, ST_SCORE)
        asm.add_imm(R0, R0, 100)
        asm.str(R0, R11, ST_SCORE)
        asm.ldr(R0, R10, CFG_SFX_COIN)
        asm.bl("play_sfx")
        asm.b(f"t_end_{tag}")
        asm.label(f"t_nc_{tag}")

        # HAZARD
        asm.cmp_imm(R0, TILE_HAZARD)
        asm.b(f"t_nh_{tag}", "NE")
        asm.bl("damage_respawn")
        asm.b("trig_exit")
        asm.label(f"t_nh_{tag}")

        # BOUNCE
        asm.cmp_imm(R0, TILE_BOUNCE)
        asm.b(f"t_nb_{tag}", "NE")
        asm.ldr_lit(R0, (-1088) & 0xFFFFFFFF)
        asm.str(R0, R11, ST_VY)
        asm.mov_imm(R0, 0)
        asm.str(R0, R11, ST_GROUND)
        asm.ldr(R0, R10, CFG_SFX_JUMP)
        asm.bl("play_sfx")
        asm.b(f"t_end_{tag}")
        asm.label(f"t_nb_{tag}")

        # GOAL
        asm.cmp_imm(R0, TILE_GOAL)
        asm.b(f"t_ng_{tag}", "NE")
        asm.mov_imm(R0, 1)
        asm.str(R0, R11, ST_WON)
        asm.ldr(R0, R10, CFG_SFX_WIN)
        asm.bl("play_sfx")
        asm.bl("play_dma_pcm")
        asm.b("trig_exit")
        asm.label(f"t_ng_{tag}")

        # UPGRADE ORB -> Unlocks room's Ability Flag + Direct Sound DMA fanfare!
        asm.cmp_imm(R0, TILE_UPGRADE)
        asm.b(f"t_nu_{tag}", "NE")
        asm.mov_reg(R0, R6, "ASR", 3)
        asm.mov_reg(R1, R7, "ASR", 3)
        asm.mov_imm(R2, 0)
        asm.bl("set_bg0_tile")
        asm.ldr(R1, R11, ST_ROOM_PTR)
        asm.ldr(R1, R1, RM_UPG_ABIL)
        asm.ldr(R0, R11, ST_ABILITIES)
        asm.orr_reg(R0, R0, R1)
        asm.str(R0, R11, ST_ABILITIES)
        asm.mov_imm(R0, 3)  # UPGRD!
        asm.str(R0, R11, ST_MSG_CODE)
        asm.mov_imm(R0, 75)
        asm.str(R0, R11, ST_MSG_TIMER)
        asm.ldr(R0, R10, CFG_SFX_WIN)
        asm.bl("play_sfx")
        asm.bl("play_dma_pcm")
        asm.b(f"t_end_{tag}")
        asm.label(f"t_nu_{tag}")

        # SAVE STATION -> Writes Real GBA Cartridge SRAM (0x0E000000) + full HP!
        asm.cmp_imm(R0, TILE_SAVE)
        asm.b(f"t_ns_{tag}", "NE")
        asm.ldr(R0, R11, ST_MSG_TIMER)
        asm.cmp_imm(R0, 0)
        asm.b(f"t_end_{tag}", "GT")
        asm.mov_imm(R0, 5)
        asm.str(R0, R11, ST_HP)
        asm.bl("save_to_sram")
        asm.mov_imm(R0, 1)  # SAVED!
        asm.str(R0, R11, ST_MSG_CODE)
        asm.mov_imm(R0, 75)
        asm.str(R0, R11, ST_MSG_TIMER)
        asm.ldr(R0, R10, CFG_SFX_COIN)
        asm.bl("play_sfx")
        asm.b(f"t_end_{tag}")
        asm.label(f"t_ns_{tag}")

        # NAVIGATION TERMINAL -> Opens BG1 Dialogue Box!
        asm.cmp_imm(R0, TILE_TERMINAL)
        asm.b(f"t_nt_{tag}", "NE")
        asm.ldr(R0, R11, ST_TERM_CD)
        asm.cmp_imm(R0, 0)
        asm.b(f"t_end_{tag}", "GT")
        asm.mov_imm(R0, 1)
        asm.str(R0, R11, ST_DIALOG_ON)
        asm.bl("draw_dialogue_box")
        asm.ldr(R0, R10, CFG_SFX_COIN)
        asm.bl("play_sfx")
        asm.b("trig_exit")
        asm.label(f"t_nt_{tag}")

        # DOOR / HATCH -> Interconnected Room Warp (with Ability Gate check!)
        asm.cmp_imm(R0, TILE_DOOR)
        asm.b(f"t_end_{tag}", "NE")
        asm.ldr(R0, R11, ST_DOOR_CD)
        asm.cmp_imm(R0, 0)
        asm.b(f"t_end_{tag}", "GT")
        asm.mov_reg(R0, R6, "ASR", 3)
        asm.mov_reg(R1, R7, "ASR", 3)
        asm.bl("try_room_door")
        asm.b("trig_exit")

        asm.label(f"t_end_{tag}")

    asm.label("trig_exit")
    asm.pop([R4, R5, R6, R7, R8, PC])
    asm.pool()

    # ==================================================================
    # Subroutine: try_room_door(R0=tx, R1=ty)
    # ==================================================================
    asm.label("try_room_door")
    asm.push([R4, R5, R6, R7, LR])
    asm.ldr(R4, R11, ST_ROOM_PTR)
    asm.ldr(R5, R4, RM_DOOR_CNT)
    asm.cmp_imm(R5, 0)
    asm.b("trd_done", "LE")
    asm.ldr(R6, R4, RM_DOOR_PTR)

    asm.label("trd_loop")
    asm.ldr(R2, R6, 0)                # door tile_x
    asm.sub_reg(R2, R2, R0)
    asm.cmp_imm(R2, 0)
    asm.rsb_imm(R2, R2, 0, cond="LT")
    asm.cmp_imm(R2, 2)
    asm.b("trd_next", "GT")
    asm.ldr(R3, R6, 4)                # door tile_y
    asm.sub_reg(R3, R3, R1)
    asm.cmp_imm(R3, 0)
    asm.rsb_imm(R3, R3, 0, cond="LT")
    asm.cmp_imm(R3, 3)
    asm.b("trd_next", "GT")

    # Matched door! Check ability requirement (offset 20)
    asm.ldr(R7, R6, 20)
    asm.cmp_imm(R7, 0)
    asm.b("trd_warp", "EQ")
    asm.ldr(R2, R11, ST_ABILITIES)
    asm.tst_reg(R2, R7)
    asm.b("trd_warp", "NE")
    # Locked hatch!
    asm.mov_imm(R0, 2)  # LOCKED
    asm.str(R0, R11, ST_MSG_CODE)
    asm.mov_imm(R0, 45)
    asm.str(R0, R11, ST_MSG_TIMER)
    asm.mov_imm(R0, 30)
    asm.str(R0, R11, ST_DOOR_CD)
    asm.ldr(R0, R10, CFG_SFX_HURT)
    asm.bl("play_sfx")
    asm.b("trd_done")

    asm.label("trd_warp")
    asm.ldr(R0, R6, 8)                # target_room
    asm.ldr(R1, R6, 12)               # target_x_px
    asm.ldr(R2, R6, 16)               # target_y_px
    asm.mov_imm(R3, 35)
    asm.str(R3, R11, ST_DOOR_CD)
    asm.bl("load_room")
    asm.b("trd_done")

    asm.label("trd_next")
    asm.add_imm(R6, R6, 24)
    asm.sub_imm(R5, R5, 1, s=True)
    asm.b("trd_loop", "NE")

    asm.label("trd_done")
    asm.pop([R4, R5, R6, R7, PC])

    # ==================================================================
    # Subroutine: save_to_sram / load_from_sram (8-bit STRB/LDRB at 0x0E000000)
    # ==================================================================
    asm.label("save_to_sram")
    asm.ldr(R0, R10, CFG_SRAM_EN)
    asm.cmp_imm(R0, 0)
    asm.bx(LR, "EQ")
    asm.ldr_lit(R3, 0x0E000000)
    # Magic 'K','P','S','2'
    for idx, ch in enumerate(b"KPS2"):
        asm.mov_imm(R0, ch)
        asm.strb(R0, R3, idx)
    asm.ldr(R0, R11, ST_ROOM_IDX)
    asm.strb(R0, R3, 4)
    asm.ldr(R0, R11, ST_PX)
    asm.mov_reg(R0, R0, "ASR", 11)    # tile_x
    asm.strb(R0, R3, 5)
    asm.ldr(R0, R11, ST_PY)
    asm.mov_reg(R0, R0, "ASR", 11)    # tile_y
    asm.strb(R0, R3, 6)
    asm.ldr(R0, R11, ST_HP)
    asm.strb(R0, R3, 7)
    asm.ldr(R0, R11, ST_ABILITIES)
    asm.strb(R0, R3, 8)
    asm.ldr(R0, R11, ST_COINS)
    asm.strb(R0, R3, 9)
    asm.ldr(R0, R11, ST_BOSS_DEAD)
    asm.strb(R0, R3, 10)
    # Compute XOR checksum of bytes 0..10 ^ 0xA5
    asm.mov_imm(R1, 0xA5)
    asm.mov_imm(R2, 0)
    asm.label("sram_chk_w")
    asm.ldrb_reg(R0, R3, R2)
    asm.eor_reg(R1, R1, R0)
    asm.add_imm(R2, R2, 1)
    asm.cmp_imm(R2, 11)
    asm.b("sram_chk_w", "LT")
    asm.strb(R1, R3, 11)
    asm.bx(LR)
    asm.pool()

    asm.label("load_from_sram")
    asm.push([R4, R5, LR])
    asm.ldr_lit(R3, 0x0E000000)
    for idx, ch in enumerate(b"KPS2"):
        asm.ldrb(R0, R3, idx)
        asm.cmp_imm(R0, ch)
        asm.b("sram_load_fail", "NE")
    asm.mov_imm(R1, 0xA5)
    asm.mov_imm(R2, 0)
    asm.label("sram_chk_r")
    asm.ldrb_reg(R0, R3, R2)
    asm.eor_reg(R1, R1, R0)
    asm.add_imm(R2, R2, 1)
    asm.cmp_imm(R2, 11)
    asm.b("sram_chk_r", "LT")
    asm.ldrb(R0, R3, 11)
    asm.cmp_reg(R0, R1)
    asm.b("sram_load_fail", "NE")

    # Valid SRAM! Restore abilities, hp, coins, boss_dead, and load saved room!
    asm.ldrb(R0, R3, 7)
    asm.cmp_imm(R0, 1)
    asm.mov_imm(R0, 5, cond="LT")
    asm.str(R0, R11, ST_HP)
    asm.ldrb(R0, R3, 8)
    asm.str(R0, R11, ST_ABILITIES)
    asm.ldrb(R0, R3, 9)
    asm.str(R0, R11, ST_COINS)
    asm.ldrb(R0, R3, 10)
    asm.str(R0, R11, ST_BOSS_DEAD)
    asm.ldrb(R0, R3, 4)               # room_idx
    asm.ldrb(R1, R3, 5)
    asm.mov_reg(R1, R1, "LSL", 3)     # px
    asm.ldrb(R2, R3, 6)
    asm.mov_reg(R2, R2, "LSL", 3)     # py
    asm.bl("load_room")
    asm.label("sram_load_fail")
    asm.pop([R4, R5, PC])
    asm.pool()

    # ==================================================================
    # Subroutine: play_dma_pcm (GBA Direct Sound Channel A via DMA1 + Timer 0!)
    # ==================================================================
    asm.label("play_dma_pcm")
    asm.ldr(R0, R10, CFG_DMA_EN)
    asm.cmp_imm(R0, 0)
    asm.bx(LR, "EQ")
    # Stop DMA1 & Timer 0
    asm.mov_imm(R0, 0)
    asm.ldr_lit(R1, 0x040000C6)
    asm.strh(R0, R1, 0)
    asm.ldr_lit(R1, 0x04000102)
    asm.strh(R0, R1, 0)
    # Reset FIFO A
    asm.ldr_lit(R1, 0x04000082)
    asm.ldr_lit(R0, 0x0B06)
    asm.strh(R0, R1, 0)
    # Configure DMA1: SAD = ROM_DMA_PCM, DAD = 0x040000A0 (FIFO_A), CNT_H = 0xB640
    asm.ldr_lit(R1, 0x040000BC)
    asm.ldr_lit(R0, "ROM_DMA_PCM")
    asm.str(R0, R1, 0)
    asm.ldr_lit(R0, 0x040000A0)
    asm.str(R0, R1, 4)
    asm.ldr_lit(R0, 0xB640)
    asm.strh(R0, R1, 10)
    # Start Timer 0 at exact sample rate
    asm.ldr_lit(R1, 0x04000100)
    asm.ldr(R0, R10, CFG_DMA_TM0)
    asm.strh(R0, R1, 0)
    asm.mov_imm(R0, 0x0080)
    asm.strh(R0, R1, 2)
    # Set frame countdown so sample stops cleanly
    asm.ldr(R0, R10, CFG_DMA_FRAMES)
    asm.str(R0, R11, ST_DMA_TIMER)
    asm.bx(LR)
    asm.pool()

    # ==================================================================
    # Subroutine: damage_respawn
    # ==================================================================
    asm.label("damage_respawn")
    asm.push([LR])
    asm.ldr(R0, R11, ST_INVULN)
    asm.cmp_imm(R0, 0)
    asm.b("dmg_ret", "GT")
    asm.ldr(R0, R10, CFG_SFX_HURT)
    asm.bl("play_sfx")
    asm.ldr(R0, R11, ST_HP)
    asm.sub_imm(R0, R0, 1, s=True)
    asm.b("dmg_alive", "GT")
    asm.bl("reset_new_game")
    asm.b("dmg_ret")
    asm.label("dmg_alive")
    asm.str(R0, R11, ST_HP)
    asm.mov_imm(R0, 45)
    asm.str(R0, R11, ST_INVULN)
    asm.ldr(R1, R11, ST_ROOM_PTR)
    asm.ldr(R0, R1, RM_SPAWN_X)
    asm.mov_reg(R0, R0, "LSL", 8)
    asm.str(R0, R11, ST_PX)
    asm.ldr(R0, R1, RM_SPAWN_Y)
    asm.mov_reg(R0, R0, "LSL", 8)
    asm.str(R0, R11, ST_PY)
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_VX)
    asm.str(R0, R11, ST_VY)
    asm.label("dmg_ret")
    asm.pop([PC])

    # ==================================================================
    # Subroutine: spawn_projectile (R0 = speed, R1 = is_heavy_bomb 0/1)
    # Supports 8-Way / Diagonal Aiming via ST_AIM_Y & ST_CURR_K!
    # ==================================================================
    asm.label("spawn_projectile")
    asm.push([R4, R5, R6, LR])
    asm.cmp_imm(R0, 1)
    asm.mov_imm(R0, 4, cond="LT")
    asm.add_imm(R4, R11, ST_PROJS)
    asm.mov_imm(R5, 4)
    asm.label("sp_loop")
    asm.ldr(R2, R4, 0)
    asm.cmp_imm(R2, 0)
    asm.b("sp_found", "EQ")
    asm.add_imm(R4, R4, 20)
    asm.sub_imm(R5, R5, 1, s=True)
    asm.b("sp_loop", "NE")
    asm.b("sp_done")

    asm.label("sp_found")
    asm.mov_imm(R2, 1)
    asm.str(R2, R4, 0)
    asm.ldr(R2, R11, ST_PX)
    asm.mov_reg(R2, R2, "ASR", 8)
    asm.ldr(R3, R11, ST_FACING)
    asm.cmp_imm(R3, 0)
    asm.add_imm(R2, R2, 8, cond="EQ")
    asm.sub_imm(R2, R2, 8, cond="NE")
    asm.str(R2, R4, 4)                # x_px
    asm.ldr(R2, R11, ST_PY)
    asm.mov_reg(R2, R2, "ASR", 8)
    asm.add_imm(R2, R2, 4)
    asm.str(R2, R4, 8)                # y_px

    # Compute vx and vy from ST_AIM_Y (-1=up, 0=horiz, +1=down) & LEFT/RIGHT held!
    asm.ldr(R6, R11, ST_AIM_Y)
    asm.cmp_imm(R6, 0)
    asm.b("sp_horiz", "EQ")
    # Aiming Up or Down: check if LEFT or RIGHT held -> diagonal 45 deg, else straight vertical!
    asm.ldr(R2, R11, ST_CURR_K)
    asm.tst_imm(R2, BUTTON_BITS["LEFT"] | BUTTON_BITS["RIGHT"])
    asm.mov_imm(R2, 0, cond="EQ")     # pure vertical vx=0
    asm.mov_reg(R2, R0, cond="NE")    # diagonal vx=+/-speed
    asm.cmp_imm(R3, 0)
    asm.rsb_imm(R2, R2, 0, cond="NE")
    asm.str(R2, R4, 12)               # vx
    asm.cmp_imm(R6, 0)
    asm.rsb_imm(R2, R0, 0, cond="LT") # vy = -speed if aiming up
    asm.mov_reg(R2, R0, cond="GT")    # vy = +speed if aiming down
    asm.b("sp_store_vy")

    asm.label("sp_horiz")
    asm.mov_reg(R2, R0)
    asm.cmp_imm(R3, 0)
    asm.rsb_imm(R2, R2, 0, cond="NE")
    asm.str(R2, R4, 12)
    asm.mov_imm(R2, 0)

    asm.label("sp_store_vy")
    asm.ldr_lit(R3, 0xFFFF)
    asm.and_reg(R2, R2, R3)
    asm.cmp_imm(R1, 0)
    asm.orr_imm(R2, R2, 0x10000, cond="NE")  # bit 16 = heavy bomb/missile
    asm.str(R2, R4, 16)
    asm.label("sp_done")
    asm.pop([R4, R5, R6, PC])
    asm.pool()

    # ==================================================================
    # Subroutine: update_projectiles (Player + Enemy shots + Destructible Blocks!)
    # ==================================================================
    asm.label("update_projectiles")
    asm.push([R4, R5, R6, R7, R8, LR])
    asm.add_imm(R4, R11, ST_PROJS)
    asm.mov_imm(R5, 6)                # 4 player + 2 enemy slots
    asm.ldr(R8, R11, ST_ROOM_PTR)

    asm.label("up_loop")
    asm.ldr(R0, R4, 0)
    asm.cmp_imm(R0, 0)
    asm.b("up_next", "EQ")
    asm.ldr(R6, R4, 4)                # x
    asm.ldr(R7, R4, 8)                # y
    asm.ldr(R0, R4, 12)               # vx
    asm.add_reg(R6, R6, R0)
    asm.str(R6, R4, 4)
    # Sign-extend lo16 vy from offset 16
    asm.ldr(R0, R4, 16)
    asm.mov_reg(R1, R0, "LSL", 16)
    asm.mov_reg(R1, R1, "ASR", 16)
    asm.add_reg(R7, R7, R1)
    asm.str(R7, R4, 8)

    # Bounds check
    asm.cmp_imm(R6, 0)
    asm.b("up_kill", "LT")
    asm.ldr(R2, R8, RM_LVL_W)
    asm.cmp_reg(R6, R2)
    asm.b("up_kill", "GE")
    asm.cmp_imm(R7, 0)
    asm.b("up_kill", "LT")
    asm.ldr(R2, R8, RM_LVL_H)
    asm.cmp_reg(R7, R2)
    asm.b("up_kill", "GE")

    # If enemy projectile (bit 17 set) -> check hit against player!
    asm.ldr(R0, R4, 16)
    asm.tst_imm(R0, 0x20000)
    asm.b("up_chk_tile", "EQ")
    asm.ldr(R1, R11, ST_PX)
    asm.mov_reg(R1, R1, "ASR", 8)
    asm.sub_reg(R1, R1, R6)
    asm.cmp_imm(R1, 0)
    asm.rsb_imm(R1, R1, 0, cond="LT")
    asm.cmp_imm(R1, 10)
    asm.b("up_chk_tile", "GT")
    asm.ldr(R2, R11, ST_PY)
    asm.mov_reg(R2, R2, "ASR", 8)
    asm.sub_reg(R2, R2, R7)
    asm.cmp_imm(R2, 0)
    asm.rsb_imm(R2, R2, 0, cond="LT")
    asm.cmp_imm(R2, 16)
    asm.b("up_chk_tile", "GT")
    asm.mov_imm(R0, 0)
    asm.str(R0, R4, 0)
    asm.bl("damage_respawn")
    asm.b("up_next")

    asm.label("up_chk_tile")
    asm.add_imm(R0, R6, 8)
    asm.add_imm(R1, R7, 8)
    asm.bl("tile_type_at_px")
    asm.cmp_imm(R0, TILE_BREAKABLE)
    asm.b("up_not_brk", "NE")
    # Shatter destructible block live in EWRAM & VRAM!
    asm.add_imm(R0, R6, 8)
    asm.mov_reg(R0, R0, "ASR", 3)
    asm.add_imm(R1, R7, 8)
    asm.mov_reg(R1, R1, "ASR", 3)
    asm.mov_imm(R2, 0)
    asm.bl("set_bg0_tile")
    asm.ldr(R0, R10, CFG_SFX_HURT)
    asm.bl("play_sfx")
    asm.b("up_kill")
    asm.label("up_not_brk")
    asm.cmp_imm(R0, TILE_SOLID)
    asm.b("up_next", "NE")

    asm.label("up_kill")
    asm.mov_imm(R0, 0)
    asm.str(R0, R4, 0)
    asm.label("up_next")
    asm.add_imm(R4, R4, 20)
    asm.sub_imm(R5, R5, 1, s=True)
    asm.b("up_loop", "NE")
    asm.pop([R4, R5, R6, R7, R8, PC])

    # ==================================================================
    # Subroutine: update_enemies (Patrol, Chaser/SA-X, Turret, 32x32 Multi-HP Boss!)
    # ==================================================================
    asm.label("update_enemies")
    asm.push([R4, R5, R6, R7, R8, R9, LR])
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_BOSS_HP)
    asm.ldr(R0, R11, ST_ROOM_PTR)
    asm.ldr(R5, R0, RM_EN_CNT)
    asm.cmp_imm(R5, 0)
    asm.b("ue_done", "LE")
    asm.add_imm(R4, R11, ST_ENEMIES)
    asm.ldr(R8, R11, ST_PX)
    asm.mov_reg(R8, R8, "ASR", 8)
    asm.ldr(R9, R11, ST_PY)
    asm.mov_reg(R9, R9, "ASR", 8)

    asm.label("ue_loop")
    asm.ldr(R0, R4, 0)
    asm.cmp_imm(R0, 0)
    asm.b("ue_next", "EQ")

    # Record boss HP for HUD if ai_type == AI_BOSS (3)
    asm.ldr(R1, R4, 32)               # ai_type
    asm.cmp_imm(R1, AI_BOSS)
    asm.b("ue_not_boss_hud", "NE")
    asm.ldr(R0, R4, 36)
    asm.and_imm(R0, R0, 0xFF)
    asm.str(R0, R11, ST_BOSS_HP)
    asm.label("ue_not_boss_hud")

    # Move every 2 frames
    asm.ldr(R0, R11, ST_FRAME)
    asm.tst_imm(R0, 1)
    asm.b("ue_after_ai", "NE")

    asm.ldr(R6, R4, 4)                # x
    asm.ldr(R7, R4, 8)                # y
    asm.ldr(R1, R4, 32)               # ai_type
    asm.ldr(R2, R4, 24)               # speed

    # AI_CHASER (1): pursues player X & Y!
    asm.cmp_imm(R1, AI_CHASER)
    asm.b("ue_not_chaser", "NE")
    asm.cmp_reg(R6, R8)
    asm.add_reg(R6, R6, R2, cond="LT")
    asm.mov_imm(R3, 1, cond="LT")
    asm.sub_reg(R6, R6, R2, cond="GT")
    asm.mvn_imm(R3, 0, cond="GT")
    asm.str(R3, R4, 20, cond="NE")
    asm.str(R6, R4, 4)
    asm.b("ue_after_ai")
    asm.label("ue_not_chaser")

    # AI_TURRET (2): stationary, fires plasma toward hero every 64 frames!
    asm.cmp_imm(R1, AI_TURRET)
    asm.b("ue_patrol_or_boss", "NE")
    asm.ldr(R0, R11, ST_FRAME)
    asm.and_imm(R0, R0, 63)
    asm.cmp_imm(R0, 0)
    asm.b("ue_after_ai", "NE")
    asm.mov_reg(R0, R6)
    asm.mov_reg(R1, R7)
    asm.cmp_reg(R8, R6)
    asm.mov_imm(R2, 2, cond="GE")
    asm.ldr_lit(R2, (-2) & 0xFFFFFFFF, cond="LT")
    asm.bl("spawn_enemy_shot")
    asm.b("ue_after_ai")

    # AI_PATROL (0) or AI_BOSS (3): patrol X between min_x..max_x (+ boss fires plasma!)
    asm.label("ue_patrol_or_boss")
    asm.ldr(R3, R4, 20)               # dir
    asm.cmp_imm(R3, 0)
    asm.add_reg(R6, R6, R2, cond="GT")
    asm.sub_reg(R6, R6, R2, cond="LE")
    asm.ldr(R0, R4, 12)               # min_x
    asm.cmp_reg(R6, R0)
    asm.b("ue_chk_max", "GT")
    asm.mov_reg(R6, R0)
    asm.mov_imm(R3, 1)
    asm.str(R3, R4, 20)
    asm.b("ue_save_x")
    asm.label("ue_chk_max")
    asm.ldr(R0, R4, 16)               # max_x
    asm.cmp_reg(R6, R0)
    asm.b("ue_save_x", "LT")
    asm.mov_reg(R6, R0)
    asm.mvn_imm(R3, 0)
    asm.str(R3, R4, 20)
    asm.label("ue_save_x")
    asm.str(R6, R4, 4)

    # Boss also fires aimed plasma every 64 frames!
    asm.cmp_imm(R1, AI_BOSS)
    asm.b("ue_after_ai", "NE")
    asm.ldr(R0, R11, ST_FRAME)
    asm.and_imm(R0, R0, 63)
    asm.cmp_imm(R0, 32)
    asm.b("ue_after_ai", "NE")
    asm.add_imm(R0, R6, 8)
    asm.add_imm(R1, R7, 12)
    asm.cmp_reg(R8, R6)
    asm.mov_imm(R2, 3, cond="GE")
    asm.ldr_lit(R2, (-3) & 0xFFFFFFFF, cond="LT")
    asm.bl("spawn_enemy_shot")

    asm.label("ue_after_ai")
    asm.ldr(R6, R4, 4)
    asm.ldr(R7, R4, 8)
    # Hitbox radius: 22 for 32x32 boss, 12 for 16x16 enemy
    asm.ldr(R12, R4, 36)
    asm.tst_imm(R12, 0x100)
    asm.mov_imm(R12, 22, cond="NE")
    asm.mov_imm(R12, 12, cond="EQ")

    # Check player projectiles [0..3]
    asm.add_imm(R0, R11, ST_PROJS)
    asm.mov_imm(R1, 4)
    asm.label("ue_proj_loop")
    asm.ldr(R2, R0, 0)
    asm.cmp_imm(R2, 0)
    asm.b("ue_proj_next", "EQ")
    asm.ldr(R2, R0, 4)
    asm.sub_reg(R2, R2, R6)
    asm.cmp_imm(R2, 0)
    asm.rsb_imm(R2, R2, 0, cond="LT")
    asm.cmp_reg(R2, R12)
    asm.b("ue_proj_next", "GT")
    asm.ldr(R3, R0, 8)
    asm.sub_reg(R3, R3, R7)
    asm.cmp_imm(R3, 0)
    asm.rsb_imm(R3, R3, 0, cond="LT")
    asm.cmp_reg(R3, R12)
    asm.b("ue_proj_next", "GT")

    # Hit! Heavy bomb/missile deals 3 dmg, normal shot deals 1 dmg
    asm.ldr(R3, R0, 16)
    asm.tst_imm(R3, 0x10000)
    asm.mov_imm(R3, 3, cond="NE")
    asm.mov_imm(R3, 1, cond="EQ")
    asm.mov_imm(R2, 0)
    asm.str(R2, R0, 0)                # consume projectile
    asm.ldr(R2, R4, 36)               # hp_and_size
    asm.and_imm(R1, R2, 0xFF)
    asm.sub_reg(R1, R1, R3, s=True)
    asm.b("ue_killed", "LE")
    # Survived (multi-HP boss!) -> store updated HP
    asm.bic_imm(R2, R2, 0xFF)
    asm.orr_reg(R2, R2, R1)
    asm.str(R2, R4, 36)
    asm.ldr(R0, R10, CFG_SFX_HURT)
    asm.bl("play_sfx")
    asm.b("ue_next")

    asm.label("ue_killed")
    asm.mov_imm(R2, 0)
    asm.str(R2, R4, 0)                # deactivate enemy
    asm.ldr(R2, R11, ST_SCORE)
    asm.add_imm(R2, R2, 200)
    asm.str(R2, R11, ST_SCORE)
    asm.ldr(R2, R4, 32)
    asm.cmp_imm(R2, AI_BOSS)
    asm.b("ue_normal_die", "NE")
    # Boss defeated! Trigger Direct Sound DMA explosion + mark boss dead + WIN!
    asm.mov_imm(R2, 1)
    asm.str(R2, R11, ST_BOSS_DEAD)
    asm.str(R2, R11, ST_WON)
    asm.bl("play_dma_pcm")
    asm.ldr(R0, R10, CFG_SFX_WIN)
    asm.bl("play_sfx")
    asm.b("ue_next")
    asm.label("ue_normal_die")
    asm.ldr(R0, R10, CFG_SFX_HURT)
    asm.bl("play_sfx")
    asm.b("ue_next")

    asm.label("ue_proj_next")
    asm.add_imm(R0, R0, 20)
    asm.sub_imm(R1, R1, 1, s=True)
    asm.b("ue_proj_loop", "NE")

    # Check player body collision / melee
    asm.sub_reg(R0, R8, R6)
    asm.cmp_imm(R0, 0)
    asm.rsb_imm(R0, R0, 0, cond="LT")
    asm.cmp_reg(R0, R12)
    asm.b("ue_next", "GT")
    asm.sub_reg(R1, R9, R7)
    asm.cmp_imm(R1, 0)
    asm.rsb_imm(R1, R1, 0, cond="LT")
    asm.cmp_reg(R1, R12)
    asm.b("ue_next", "GT")
    asm.ldr(R2, R11, ST_MELEE)
    asm.cmp_imm(R2, 0)
    asm.b("ue_hit_player", "LE")
    asm.mov_imm(R0, 0)
    asm.str(R0, R4, 0)
    asm.ldr(R0, R10, CFG_SFX_HURT)
    asm.bl("play_sfx")
    asm.b("ue_next")

    asm.label("ue_hit_player")
    asm.bl("damage_respawn")

    asm.label("ue_next")
    asm.add_imm(R4, R4, 40)
    asm.sub_imm(R5, R5, 1, s=True)
    asm.b("ue_loop", "NE")

    asm.label("ue_done")
    asm.pop([R4, R5, R6, R7, R8, R9, PC])
    asm.pool()

    # Helper: spawn_enemy_shot(R0=x, R1=y, R2=vx) in projectile slots 4..5
    asm.label("spawn_enemy_shot")
    asm.add_imm(R3, R11, ST_PROJS + 80)  # slot 4
    asm.ldr(R12, R3, 0)
    asm.cmp_imm(R12, 0)
    asm.b("ses_write", "EQ")
    asm.add_imm(R3, R3, 20)              # slot 5
    asm.ldr(R12, R3, 0)
    asm.cmp_imm(R12, 0)
    asm.bx(LR, "NE")
    asm.label("ses_write")
    asm.mov_imm(R12, 1)
    asm.str(R12, R3, 0)
    asm.str(R0, R3, 4)
    asm.str(R1, R3, 8)
    asm.str(R2, R3, 12)
    asm.mov_imm(R12, 0x20000)            # enemy shot flag
    asm.str(R12, R3, 16)
    asm.bx(LR)

    # ==================================================================
    # Subroutine: update_player_anim
    # ==================================================================
    asm.label("update_player_anim")
    asm.ldr(R0, R11, ST_ATIMER)
    asm.add_imm(R0, R0, 1)
    asm.str(R0, R11, ST_ATIMER)
    asm.ldr(R0, R11, ST_ALOCK)
    asm.cmp_imm(R0, 0)
    asm.bx(LR, "GT")
    asm.ldr(R0, R10, CFG_PHYSICS)
    asm.cmp_imm(R0, 0)
    asm.b("upa_check_move", "NE")
    asm.ldr(R1, R11, ST_GROUND)
    asm.cmp_imm(R1, 0)
    asm.b("upa_check_move", "NE")
    asm.mov_imm(R0, 2)
    asm.str(R0, R11, ST_ANIM)
    asm.bx(LR)
    asm.label("upa_check_move")
    asm.ldr(R0, R11, ST_MOVED)
    asm.cmp_imm(R0, 0)
    asm.mov_imm(R1, 1, cond="NE")
    asm.mov_imm(R1, 0, cond="EQ")
    asm.str(R1, R11, ST_ANIM)
    asm.bx(LR)

    # ==================================================================
    # Subroutine: update_camera (BG0 1x scroll + BG2 1/2-speed Parallax!)
    # ==================================================================
    asm.label("update_camera")
    asm.ldr(R12, R11, ST_ROOM_PTR)
    asm.ldr(R0, R11, ST_PX)
    asm.mov_reg(R0, R0, "ASR", 8)
    asm.ldr(R1, R10, CFG_VIEW_W)
    asm.mov_reg(R1, R1, "ASR", 1)
    asm.sub_reg(R0, R0, R1)
    asm.add_imm(R0, R0, 8)
    asm.cmp_imm(R0, 0)
    asm.mov_imm(R0, 0, cond="LT")
    asm.ldr(R2, R12, RM_LVL_W)
    asm.ldr(R3, R10, CFG_VIEW_W)
    asm.sub_reg(R2, R2, R3)
    asm.cmp_imm(R2, 0)
    asm.mov_imm(R2, 0, cond="LT")
    asm.cmp_reg(R0, R2)
    asm.mov_reg(R0, R2, cond="GT")
    asm.str(R0, R11, ST_CAMX)

    asm.ldr(R1, R11, ST_PY)
    asm.mov_reg(R1, R1, "ASR", 8)
    asm.ldr(R2, R10, CFG_VIEW_H)
    asm.mov_reg(R2, R2, "ASR", 1)
    asm.sub_reg(R1, R1, R2)
    asm.add_imm(R1, R1, 8)
    asm.cmp_imm(R1, 0)
    asm.mov_imm(R1, 0, cond="LT")
    asm.ldr(R2, R12, RM_LVL_H)
    asm.ldr(R3, R10, CFG_VIEW_H)
    asm.sub_reg(R2, R2, R3)
    asm.cmp_imm(R2, 0)
    asm.mov_imm(R2, 0, cond="LT")
    asm.cmp_reg(R1, R2)
    asm.mov_reg(R1, R2, cond="GT")
    asm.str(R1, R11, ST_CAMY)

    # BG2 1/2-speed parallax scroll (0x04000018 BG2HOFS, 0x1A BG2VOFS)
    asm.ldr_lit(R3, 0x04000018)
    asm.mov_reg(R2, R0, "ASR", 1)
    asm.strh(R2, R3, 0)
    asm.mov_reg(R2, R1, "ASR", 1)
    asm.strh(R2, R3, 2)

    asm.ldr(R2, R10, CFG_VIEW_OX)
    asm.sub_reg(R0, R0, R2)
    asm.ldr(R2, R10, CFG_VIEW_OY)
    asm.sub_reg(R1, R1, R2)
    asm.ldr_lit(R3, 0x04000010)
    asm.strh(R0, R3, 0)
    asm.strh(R1, R3, 2)
    asm.bx(LR)
    asm.pool()

    # ==================================================================
    # Subroutine: render_oam (Multi-size 16x16 / 16x32 Hero, Morph Ball, Projectiles, 32x32 Bosses!)
    # ==================================================================
    asm.label("render_oam")
    asm.push([R4, R5, R6, R7, R8, R9, LR])
    asm.ldr_lit(R4, 0x07000000)
    asm.ldr(R5, R11, ST_CAMX)
    asm.ldr(R6, R11, ST_CAMY)
    asm.ldr(R7, R10, CFG_VIEW_OX)
    asm.ldr(R8, R10, CFG_VIEW_OY)

    # --- OAM[0]: Hero / Morph Ball ---
    asm.ldr(R0, R11, ST_INVULN)
    asm.tst_imm(R0, 4)
    asm.b("oam_hero_show", "EQ")
    asm.mov_imm(R0, 0x0200)
    asm.strh(R0, R4, 0)
    asm.b("oam_hero_done")
    asm.label("oam_hero_show")

    asm.ldr(R0, R11, ST_PX)
    asm.mov_reg(R0, R0, "ASR", 8)
    asm.sub_reg(R0, R0, R5)
    asm.add_reg(R0, R0, R7)
    asm.ldr_lit(R3, 0x01FF)
    asm.and_reg(R0, R0, R3)

    asm.ldr(R1, R11, ST_PY)
    asm.mov_reg(R1, R1, "ASR", 8)
    asm.sub_reg(R1, R1, R6)
    asm.add_reg(R1, R1, R8)
    asm.and_imm(R1, R1, 0xFF)

    # Check Morph Ball state!
    asm.ldr(R2, R11, ST_MORPHED)
    asm.cmp_imm(R2, 0)
    asm.b("oam_hero_standing", "EQ")
    # Morphed: 16x16 square (attr0 shape=0, attr1 size=0x4000, tile=CFG_MORPH_TILE)
    asm.orr_imm(R0, R0, 0x4000)
    asm.ldr(R2, R10, CFG_MORPH_TILE)
    asm.b("oam_hero_fin")

    asm.label("oam_hero_standing")
    asm.ldr(R3, R10, CFG_HERO_A0_SH)
    asm.orr_reg(R1, R1, R3)
    asm.ldr(R3, R10, CFG_HERO_A1_SZ)
    asm.orr_reg(R0, R0, R3)
    asm.ldr(R2, R11, ST_FACING)
    asm.cmp_imm(R2, 0)
    asm.orr_imm(R0, R0, 0x1000, cond="NE")

    asm.ldr(R2, R11, ST_ANIM)
    asm.and_imm(R2, R2, 3)
    asm.mov_imm(R3, 24)
    asm.mul(R9, R2, R3)
    asm.ldr_lit(R3, "ROM_ANIM_TABLE")
    asm.add_reg(R9, R3, R9)
    asm.ldr(R2, R9, 0)
    asm.ldr(R12, R11, ST_ATIMER)
    asm.mov_reg(R12, R12, "LSR", 3)
    asm.label("oam_mod_loop")
    asm.cmp_reg(R12, R2)
    asm.sub_reg(R12, R12, R2, cond="GE")
    asm.b("oam_mod_loop", "GE")
    asm.add_imm(R9, R9, 8)
    asm.ldr_reg(R2, R9, R12, shift_amt=2)

    asm.label("oam_hero_fin")
    asm.ldr(R3, R11, ST_PAL)
    asm.orr_reg(R2, R2, R3, "LSL", 12)
    asm.orr_imm(R2, R2, 0x0400)
    asm.strh(R1, R4, 0)
    asm.strh(R0, R4, 2)
    asm.strh(R2, R4, 4)
    asm.label("oam_hero_done")
    asm.add_imm(R4, R4, 8)

    # --- OAM[1..6]: Projectiles (4 player + 2 enemy) ---
    asm.add_imm(R9, R11, ST_PROJS)
    asm.mov_imm(R12, 6)
    asm.label("oam_proj_loop")
    asm.ldr(R0, R9, 0)
    asm.cmp_imm(R0, 0)
    asm.b("oam_proj_hide", "EQ")
    asm.ldr(R0, R9, 4)
    asm.sub_reg(R0, R0, R5)
    asm.add_reg(R0, R0, R7)
    asm.cmp_imm(R0, -16)
    asm.b("oam_proj_hide", "LT")
    asm.cmp_imm(R0, 240)
    asm.b("oam_proj_hide", "GE")
    asm.ldr(R1, R9, 8)
    asm.sub_reg(R1, R1, R6)
    asm.add_reg(R1, R1, R8)
    asm.cmp_imm(R1, -16)
    asm.b("oam_proj_hide", "LT")
    asm.cmp_imm(R1, 160)
    asm.b("oam_proj_hide", "GE")

    asm.and_imm(R1, R1, 0xFF)
    asm.ldr_lit(R3, 0x01FF)
    asm.and_reg(R0, R0, R3)
    asm.orr_imm(R0, R0, 0x4000)
    asm.ldr(R2, R10, CFG_PROJ_TILE)
    asm.orr_imm(R2, R2, 0x0400)
    asm.strh(R1, R4, 0)
    asm.strh(R0, R4, 2)
    asm.strh(R2, R4, 4)
    asm.b("oam_proj_next")
    asm.label("oam_proj_hide")
    asm.mov_imm(R0, 0x0200)
    asm.strh(R0, R4, 0)
    asm.label("oam_proj_next")
    asm.add_imm(R4, R4, 8)
    asm.add_imm(R9, R9, 20)
    asm.sub_imm(R12, R12, 1, s=True)
    asm.b("oam_proj_loop", "NE")

    # --- OAM[7..22]: Enemies & 32x32 Bosses ---
    asm.ldr(R0, R11, ST_ROOM_PTR)
    asm.ldr(R12, R0, RM_EN_CNT)
    asm.cmp_imm(R12, 0)
    asm.b("oam_hide_rest", "LE")
    asm.add_imm(R9, R11, ST_ENEMIES)
    asm.label("oam_en_loop")
    asm.ldr(R0, R9, 0)
    asm.cmp_imm(R0, 0)
    asm.b("oam_en_hide", "EQ")
    asm.ldr(R0, R9, 4)
    asm.sub_reg(R0, R0, R5)
    asm.add_reg(R0, R0, R7)
    asm.cmp_imm(R0, -32)
    asm.b("oam_en_hide", "LT")
    asm.cmp_imm(R0, 240)
    asm.b("oam_en_hide", "GE")
    asm.ldr(R1, R9, 8)
    asm.sub_reg(R1, R1, R6)
    asm.add_reg(R1, R1, R8)
    asm.cmp_imm(R1, -32)
    asm.b("oam_en_hide", "LT")
    asm.cmp_imm(R1, 160)
    asm.b("oam_en_hide", "GE")

    asm.and_imm(R1, R1, 0xFF)
    asm.ldr_lit(R3, 0x01FF)
    asm.and_reg(R0, R0, R3)
    # 32x32 boss (bit 8 of offset 36) -> attr1 |= 0x8000, else 0x4000
    asm.ldr(R3, R9, 36)
    asm.tst_imm(R3, 0x100)
    asm.orr_imm(R0, R0, 0x8000, cond="NE")
    asm.orr_imm(R0, R0, 0x4000, cond="EQ")
    asm.ldr(R3, R9, 20)
    asm.cmp_imm(R3, 0)
    asm.orr_imm(R0, R0, 0x1000, cond="LT")
    asm.ldr(R2, R9, 28)
    asm.ldr(R3, R9, 36)
    asm.tst_imm(R3, 0x100)
    asm.b("oam_en_no_toggle", "NE")  # 32x32 boss uses frame 0 cleanly
    asm.ldr(R3, R11, ST_FRAME)
    asm.tst_imm(R3, 16)
    asm.add_imm(R2, R2, 4, cond="NE")
    asm.label("oam_en_no_toggle")
    asm.orr_imm(R2, R2, 0x0400)
    asm.strh(R1, R4, 0)
    asm.strh(R0, R4, 2)
    asm.strh(R2, R4, 4)
    asm.b("oam_en_next")
    asm.label("oam_en_hide")
    asm.mov_imm(R0, 0x0200)
    asm.strh(R0, R4, 0)
    asm.label("oam_en_next")
    asm.add_imm(R4, R4, 8)
    asm.add_imm(R9, R9, 40)
    asm.sub_imm(R12, R12, 1, s=True)
    asm.b("oam_en_loop", "NE")

    # Hide remaining OAM slots up to 24
    asm.label("oam_hide_rest")
    asm.ldr_lit(R3, 0x070000C0)
    asm.mov_imm(R0, 0x0200)
    asm.label("oam_hr_loop")
    asm.cmp_reg(R4, R3)
    asm.b("oam_done", "GE")
    asm.strh(R0, R4, 0)
    asm.add_imm(R4, R4, 8)
    asm.b("oam_hr_loop")

    asm.label("oam_done")
    asm.pop([R4, R5, R6, R7, R8, R9, PC])
    asm.pool()

    # ==================================================================
    # Subroutine: render_hud + draw_dialogue_box / clear_dialogue_box
    # ==================================================================
    asm.label("render_hud")
    asm.push([R4, R5, R6, LR])
    asm.ldr_lit(R4, 0x0600F000)
    asm.ldr(R0, R10, CFG_VIEW_OY)
    asm.cmp_imm(R0, 0)
    asm.add_imm(R4, R4, 74, cond="NE")
    asm.add_imm(R4, R4, 2, cond="EQ")

    # 5 Heart slots
    asm.ldr(R5, R11, ST_HP)
    asm.mov_imm(R6, 0)
    asm.label("hud_hp_loop")
    asm.cmp_reg(R6, R5)
    asm.ldr_lit(R0, (15 << 12) | FONT_INDEX["HEART"], cond="LT")
    asm.ldr_lit(R0, (15 << 12) | FONT_INDEX[" "], cond="GE")
    asm.strh(R0, R4, 0)
    asm.add_imm(R4, R4, 2)
    asm.add_imm(R6, R6, 1)
    asm.cmp_imm(R6, 5)
    asm.b("hud_hp_loop", "LT")

    # Coin count
    asm.add_imm(R4, R4, 2)
    asm.ldr_lit(R0, (15 << 12) | FONT_INDEX["COIN"])
    asm.strh(R0, R4, 0)
    asm.add_imm(R4, R4, 2)
    asm.ldr(R0, R11, ST_COINS)
    asm.mov_imm(R1, 0)
    asm.label("hud_div10")
    asm.cmp_imm(R0, 10)
    asm.sub_imm(R0, R0, 10, cond="GE")
    asm.add_imm(R1, R1, 1, cond="GE")
    asm.b("hud_div10", "GE")
    asm.cmp_imm(R1, 9)
    asm.mov_imm(R1, 9, cond="GT")
    asm.add_imm(R1, R1, FONT_INDEX["0"])
    asm.orr_imm(R1, R1, 0xF000)
    asm.strh(R1, R4, 0)
    asm.add_imm(R0, R0, FONT_INDEX["0"])
    asm.orr_imm(R0, R0, 0xF000)
    asm.strh(R0, R4, 2)

    # Room indicator "R1"
    asm.add_imm(R4, R4, 6)
    asm.ldr_lit(R0, (15 << 12) | FONT_INDEX["R"])
    asm.strh(R0, R4, 0)
    asm.ldr(R0, R11, ST_ROOM_IDX)
    asm.add_imm(R0, R0, FONT_INDEX["1"])
    asm.orr_imm(R0, R0, 0xF000)
    asm.strh(R0, R4, 2)

    # Status Banner (CLEAR! / PAUSED / SAVED! / LOCKED / UPGRD! / Boss HP bars)
    asm.add_imm(R4, R4, 6)
    asm.ldr(R0, R11, ST_WON)
    asm.cmp_imm(R0, 0)
    asm.b("hud_chk_pause", "EQ")
    for idx, ch in enumerate("CLEAR!"):
        asm.ldr_lit(R1, (15 << 12) | FONT_INDEX[ch])
        asm.strh(R1, R4, idx * 2)
    asm.b("hud_done")

    asm.label("hud_chk_pause")
    asm.ldr(R0, R11, ST_PAUSED)
    asm.cmp_imm(R0, 0)
    asm.b("hud_chk_msg", "EQ")
    for idx, ch in enumerate("PAUSED"):
        asm.ldr_lit(R1, (15 << 12) | FONT_INDEX[ch])
        asm.strh(R1, R4, idx * 2)
    asm.b("hud_done")

    asm.label("hud_chk_msg")
    asm.ldr(R0, R11, ST_MSG_TIMER)
    asm.cmp_imm(R0, 0)
    asm.b("hud_chk_boss", "LE")
    asm.ldr(R0, R11, ST_MSG_CODE)
    asm.cmp_imm(R0, 1)
    asm.b("hud_m2", "NE")
    for idx, ch in enumerate("SAVED!"):
        asm.ldr_lit(R1, (15 << 12) | FONT_INDEX[ch])
        asm.strh(R1, R4, idx * 2)
    asm.b("hud_done")
    asm.label("hud_m2")
    asm.cmp_imm(R0, 2)
    asm.b("hud_m3", "NE")
    for idx, ch in enumerate("LOCKED"):
        asm.ldr_lit(R1, (15 << 12) | FONT_INDEX[ch])
        asm.strh(R1, R4, idx * 2)
    asm.b("hud_done")
    asm.label("hud_m3")
    for idx, ch in enumerate("UPGRD!"):
        asm.ldr_lit(R1, (15 << 12) | FONT_INDEX[ch])
        asm.strh(R1, R4, idx * 2)
    asm.b("hud_done")

    asm.label("hud_chk_boss")
    asm.ldr(R5, R11, ST_BOSS_HP)
    asm.cmp_imm(R5, 0)
    asm.b("hud_clear_msg", "LE")
    # Draw Boss HP bar (up to 6 bars)
    asm.mov_imm(R6, 0)
    asm.label("hud_boss_bar")
    asm.mov_reg(R1, R6, "LSL", 1)
    asm.cmp_reg(R1, R5)
    asm.ldr_lit(R0, (15 << 12) | FONT_INDEX["BAR"], cond="LT")
    asm.ldr_lit(R0, (15 << 12) | FONT_INDEX[" "], cond="GE")
    asm.strh(R0, R4, 0)
    asm.add_imm(R4, R4, 2)
    asm.add_imm(R6, R6, 1)
    asm.cmp_imm(R6, 6)
    asm.b("hud_boss_bar", "LT")
    asm.b("hud_done")

    asm.label("hud_clear_msg")
    asm.ldr_lit(R1, (15 << 12) | FONT_INDEX[" "])
    for idx in range(6):
        asm.strh(R1, R4, idx * 2)

    asm.label("hud_done")
    asm.pop([R4, R5, R6, PC])
    asm.pool()

    # Draw 2-line Navigation Terminal Dialogue Box on BG1 rows 16..17 (cols 3..26)
    asm.label("draw_dialogue_box")
    asm.push([R4, R5, R6, LR])
    asm.ldr(R4, R11, ST_ROOM_PTR)
    asm.ldr(R4, R4, RM_DLG_PTR)       # 48 FONT_INDEX bytes
    asm.ldr_lit(R5, 0x0600F000 + (16 * 32 + 3) * 2)
    asm.mov_imm(R6, 0)
    asm.label("ddb_l1")
    asm.ldrb_reg(R0, R4, R6)
    asm.orr_imm(R0, R0, 0xF000)
    asm.strh(R0, R5, 0)
    asm.add_imm(R5, R5, 2)
    asm.add_imm(R6, R6, 1)
    asm.cmp_imm(R6, 24)
    asm.b("ddb_l1", "LT")
    asm.ldr_lit(R5, 0x0600F000 + (17 * 32 + 3) * 2)
    asm.label("ddb_l2")
    asm.ldrb_reg(R0, R4, R6)
    asm.orr_imm(R0, R0, 0xF000)
    asm.strh(R0, R5, 0)
    asm.add_imm(R5, R5, 2)
    asm.add_imm(R6, R6, 1)
    asm.cmp_imm(R6, 48)
    asm.b("ddb_l2", "LT")
    asm.pop([R4, R5, R6, PC])
    asm.pool()

    asm.label("clear_dialogue_box")
    asm.ldr_lit(R0, (15 << 12) | FONT_INDEX[" "])
    asm.ldr_lit(R1, 0x0600F000 + (16 * 32 + 3) * 2)
    asm.mov_imm(R2, 24)
    asm.label("cdb_l1")
    asm.strh(R0, R1, 0)
    asm.add_imm(R1, R1, 2)
    asm.sub_imm(R2, R2, 1, s=True)
    asm.b("cdb_l1", "NE")
    asm.ldr_lit(R1, 0x0600F000 + (17 * 32 + 3) * 2)
    asm.mov_imm(R2, 24)
    asm.label("cdb_l2")
    asm.strh(R0, R1, 0)
    asm.add_imm(R1, R1, 2)
    asm.sub_imm(R2, R2, 1, s=True)
    asm.b("cdb_l2", "NE")
    asm.bx(LR)
    asm.pool()

    # ==================================================================
    # PSG Audio Subroutines: play_sfx & update_bgm_genie
    # ==================================================================
    asm.label("play_sfx")
    asm.ldr(R1, R10, CFG_SFX_CNT)
    asm.cmp_reg(R0, R1)
    asm.bx(LR, "HS")
    asm.ldr_lit(R2, "ROM_SFX")
    asm.add_reg(R2, R2, R0, "LSL", 4)
    asm.ldr(R1, R2, 0)
    asm.cmp_imm(R1, 4)
    asm.b("sfx_ch4", "EQ")
    asm.ldr_lit(R3, 0x04000060)
    asm.ldr(R0, R2, 4)
    asm.strh(R0, R3, 0)
    asm.ldr(R0, R2, 8)
    asm.strh(R0, R3, 2)
    asm.ldr(R0, R2, 12)
    asm.strh(R0, R3, 4)
    asm.bx(LR)
    asm.label("sfx_ch4")
    asm.ldr_lit(R3, 0x04000078)
    asm.ldr(R0, R2, 4)
    asm.strh(R0, R3, 0)
    asm.ldr(R0, R2, 8)
    asm.strh(R0, R3, 4)
    asm.bx(LR)
    asm.pool()

    asm.label("update_bgm_genie")
    asm.ldr(R0, R10, CFG_BGM_EN)
    asm.cmp_imm(R0, 0)
    asm.bx(LR, "EQ")
    asm.ldr(R1, R11, ST_BGM_TICK)
    asm.sub_imm(R1, R1, 1, s=True)
    asm.b("bgm_fire", "LE")
    asm.str(R1, R11, ST_BGM_TICK)
    asm.bx(LR)
    asm.label("bgm_fire")
    asm.ldr(R1, R10, CFG_BGM_FSTEP)
    asm.str(R1, R11, ST_BGM_TICK)
    asm.ldr(R0, R11, ST_BGM_STEP)
    asm.and_imm(R0, R0, 15)
    asm.add_reg(R2, R0, R0, "LSL", 1)
    asm.mov_reg(R2, R2, "LSL", 2)
    asm.ldr_lit(R3, "ROM_BGM_GENIE")
    asm.add_reg(R2, R3, R2)
    asm.add_imm(R0, R0, 1)
    asm.and_imm(R0, R0, 15)
    asm.str(R0, R11, ST_BGM_STEP)
    asm.ldr(R0, R2, 4)
    asm.cmp_imm(R0, 0)
    asm.bx(LR, "EQ")
    asm.ldr(R1, R2, 0)
    asm.ldr_lit(R3, 0x04000068)
    asm.strh(R1, R3, 0)
    asm.strh(R0, R3, 4)
    asm.bx(LR)
    asm.pool()

    # ==================================================================
    # Tilemap Helpers: tile_type_at_px & set_bg0_tile
    # ==================================================================
    asm.label("tile_type_at_px")
    asm.mov_reg(R0, R0, "ASR", 3)
    asm.mov_reg(R1, R1, "ASR", 3)
    asm.cmp_imm(R0, 0)
    asm.b("tt_solid", "LT")
    asm.cmp_imm(R0, 64)
    asm.b("tt_solid", "GE")
    asm.cmp_imm(R1, 0)
    asm.b("tt_empty", "LT")
    asm.cmp_imm(R1, 32)
    asm.b("tt_empty", "GE")
    asm.add_reg(R2, R0, R1, "LSL", 6)
    asm.mov_reg(R2, R2, "LSL", 1)
    asm.ldr_lit(R3, 0x02000000)
    asm.ldrh_reg(R0, R3, R2)
    asm.and_imm(R0, R0, 0xFF)
    asm.ldr_lit(R3, "ROM_TILE_TYPES")
    asm.ldrb_reg(R0, R3, R0)
    asm.bx(LR)
    asm.label("tt_solid")
    asm.mov_imm(R0, TILE_SOLID)
    asm.bx(LR)
    asm.label("tt_empty")
    asm.mov_imm(R0, 0)
    asm.bx(LR)
    asm.pool()

    asm.label("set_bg0_tile")
    asm.add_reg(R3, R0, R1, "LSL", 6)
    asm.mov_reg(R3, R3, "LSL", 1)
    asm.ldr_lit(R12, 0x02000000)
    asm.strh_reg(R2, R12, R3)
    asm.and_imm(R3, R0, 32)
    asm.mov_reg(R3, R3, "LSL", 6)
    asm.and_imm(R12, R1, 31)
    asm.orr_reg(R3, R3, R12, "LSL", 6)
    asm.and_imm(R12, R0, 31)
    asm.orr_reg(R3, R3, R12, "LSL", 1)
    asm.ldr_lit(R12, 0x0600E000)
    asm.strh_reg(R2, R12, R3)
    asm.bx(LR)
    asm.pool()

    # ==================================================================
    # Subroutines: reset_new_game & load_room(R0=room_idx, R1=px, R2=py)
    # ==================================================================
    asm.label("reset_new_game")
    asm.push([LR])
    asm.mov_imm(R0, 0)
    for st_off in (ST_VX, ST_VY, ST_FACING, ST_GROUND, ST_ANIM, ST_ATIMER, ST_ALOCK,
                   ST_SCORE, ST_COINS, ST_INVULN, ST_PAUSED, ST_WON, ST_DASH, ST_MELEE,
                   ST_SHOOT_CD, ST_MORPHED, ST_DIALOG_ON, ST_MSG_TIMER, ST_BOSS_DEAD):
        asm.str(R0, R11, st_off)
    asm.mov_imm(R0, 5)
    asm.str(R0, R11, ST_HP)
    asm.ldr(R0, R10, CFG_START_ABIL)
    asm.str(R0, R11, ST_ABILITIES)
    asm.ldr_lit(R3, "ROM_ROOMS_TABLE")
    asm.mov_imm(R0, 0)
    asm.ldr(R1, R3, RM_SPAWN_X)
    asm.ldr(R2, R3, RM_SPAWN_Y)
    asm.bl("load_room")
    asm.pop([PC])
    asm.pool()

    asm.label("load_room")
    asm.push([R4, R5, R6, R7, LR])
    # Clamp room_idx
    asm.ldr(R3, R10, CFG_ROOM_CNT)
    asm.cmp_reg(R0, R3)
    asm.mov_imm(R0, 0, cond="HS")
    asm.str(R0, R11, ST_ROOM_IDX)
    # Room descriptor ptr = ROM_ROOMS_TABLE + room_idx * 64
    asm.ldr_lit(R3, "ROM_ROOMS_TABLE")
    asm.add_reg(R7, R3, R0, "LSL", 6)
    asm.str(R7, R11, ST_ROOM_PTR)

    # Set player spawn position
    asm.mov_reg(R1, R1, "LSL", 8)
    asm.str(R1, R11, ST_PX)
    asm.mov_reg(R2, R2, "LSL", 8)
    asm.str(R2, R11, ST_PY)
    asm.mov_imm(R0, 0)
    asm.str(R0, R11, ST_VX)
    asm.str(R0, R11, ST_VY)

    # Clear all 6 projectiles
    asm.add_imm(R4, R11, ST_PROJS)
    for i in range(6):
        asm.str(R0, R4, i * 20)

    # Copy room enemies (40 bytes = 20 halfwords each)
    asm.ldr(R2, R7, RM_EN_CNT)
    asm.cmp_imm(R2, 0)
    asm.b("lr_no_en", "LE")
    asm.mov_imm(R3, 20)
    asm.mul(R2, R3, R2)
    asm.ldr(R0, R7, RM_EN_PTR)
    asm.add_imm(R1, R11, ST_ENEMIES)
    asm.bl("copy_halfwords")
    asm.label("lr_no_en")

    # Copy room 64x32 tilemap into EWRAM & BG0 VRAM
    asm.ldr(R4, R7, RM_MAP_PTR)
    asm.mov_imm(R5, 0)
    asm.label("lr_row")
    asm.mov_imm(R6, 0)
    asm.label("lr_col")
    asm.ldrh(R2, R4, 0)
    asm.add_imm(R4, R4, 2)
    asm.mov_reg(R0, R6)
    asm.mov_reg(R1, R5)
    asm.bl("set_bg0_tile")
    asm.add_imm(R6, R6, 1)
    asm.cmp_imm(R6, 64)
    asm.b("lr_col", "LT")
    asm.add_imm(R5, R5, 1)
    asm.cmp_imm(R5, 32)
    asm.b("lr_row", "LT")

    # Fill BG2 Parallax Backdrop (SBB 26 = 0x0600D000, 32x32)
    asm.ldr_lit(R4, 0x0600D000)
    asm.ldr(R3, R7, RM_PAR_EN)
    asm.ldr(R5, R7, RM_PAR_TILE)
    asm.mov_imm(R6, 0)                # 0..1023
    asm.label("lr_par_loop")
    asm.mov_imm(R0, 0)
    asm.cmp_imm(R3, 0)
    asm.b("lr_par_st", "EQ")
    # Subtle spaced BSL grid/star parallax pattern every 4x4 tiles!
    asm.tst_imm(R6, 3)
    asm.b("lr_par_st", "NE")
    asm.tst_imm(R6, 0x60)
    asm.mov_reg(R0, R5, cond="EQ")
    asm.label("lr_par_st")
    asm.strh(R0, R4, 0)
    asm.add_imm(R4, R4, 2)
    asm.add_imm(R6, R6, 1)
    asm.cmp_imm(R6, 1024)
    asm.b("lr_par_loop", "LT")

    # Clear BG1 HUD & GB/GBC Bezel
    asm.ldr_lit(R4, 0x0600F000)
    asm.mov_imm(R5, 0)
    asm.label("lr_hud_y")
    asm.mov_imm(R6, 0)
    asm.label("lr_hud_x")
    asm.ldr_lit(R0, (15 << 12) | FONT_INDEX[" "])
    asm.ldr(R1, R10, CFG_VIEW_OX)
    asm.cmp_imm(R1, 0)
    asm.b("lr_hud_st", "EQ")
    asm.cmp_imm(R6, 5)
    asm.b("lr_bezel", "LT")
    asm.cmp_imm(R6, 25)
    asm.b("lr_bezel", "GE")
    asm.cmp_imm(R5, 1)
    asm.b("lr_bezel", "LT")
    asm.cmp_imm(R5, 19)
    asm.b("lr_hud_st", "LT")
    asm.label("lr_bezel")
    asm.ldr_lit(R0, (15 << 12) | FONT_INDEX["BEZEL"])
    asm.label("lr_hud_st")
    asm.strh(R0, R4, 0)
    asm.add_imm(R4, R4, 2)
    asm.add_imm(R6, R6, 1)
    asm.cmp_imm(R6, 32)
    asm.b("lr_hud_x", "LT")
    asm.add_imm(R5, R5, 1)
    asm.cmp_imm(R5, 32)
    asm.b("lr_hud_y", "LT")

    asm.pop([R4, R5, R6, R7, PC])
    asm.pool()

    # Helpers: copy_halfwords & hide_all_oam
    asm.label("copy_halfwords")
    asm.cmp_imm(R2, 0)
    asm.bx(LR, "LE")
    asm.label("chw_loop")
    asm.ldrh(R3, R0, 0)
    asm.strh(R3, R1, 0)
    asm.add_imm(R0, R0, 2)
    asm.add_imm(R1, R1, 2)
    asm.sub_imm(R2, R2, 1, s=True)
    asm.b("chw_loop", "NE")
    asm.bx(LR)

    asm.label("hide_all_oam")
    asm.ldr_lit(R0, 0x07000000)
    asm.mov_imm(R1, 0x0200)
    asm.mov_imm(R2, 0)
    asm.mov_imm(R3, 128)
    asm.label("hao_loop")
    asm.strh(R1, R0, 0)
    asm.strh(R2, R0, 2)
    asm.strh(R2, R0, 4)
    asm.strh(R2, R0, 6)
    asm.add_imm(R0, R0, 8)
    asm.sub_imm(R3, R3, 1, s=True)
    asm.b("hao_loop", "NE")
    asm.bx(LR)
    asm.pool()

    # ------------------------------------------------------------------
    # 4. Emit Packed ROM Data Tables + Official GBA SRAM Tag!
    # ------------------------------------------------------------------
    asm.align(4)
    asm.emit_bytes(b"SRAM_V113\x00\x00\x00")  # Official GBA SRAM auto-detect identifier!

    asm.label("ROM_CONFIG")
    for w in config_words:
        asm.emit32(w)

    asm.label("ROM_ANIM_TABLE")
    for w in anim_table_words:
        asm.emit32(w)

    asm.label("ROM_RULES")
    for w in rules_words:
        asm.emit32(w)
    if not rules_words:
        asm.emit32(0)

    asm.label("ROM_SFX")
    for w in sfx_words:
        asm.emit32(w)
    if not sfx_words:
        asm.emit32(0)

    asm.label("ROM_BGM_GENIE")
    for w in bgm_words:
        asm.emit32(w)

    # Room Descriptor Table (64 bytes = 16 words per room)
    asm.align(4)
    asm.label("ROM_ROOMS_TABLE")
    for (ri, rwp, rhp, sxp, syp, _mhw, _enw, encnt, _dw, dcnt, _dlg, uab, paren, partile) in room_blobs:
        asm.emit32(rwp)
        asm.emit32(rhp)
        asm.emit32(sxp)
        asm.emit32(syp)
        asm.emit_word_label(f"ROM_RM_MAP_{ri}")
        asm.emit_word_label(f"ROM_RM_EN_{ri}")
        asm.emit32(encnt)
        asm.emit_word_label(f"ROM_RM_DR_{ri}")
        asm.emit32(dcnt)
        asm.emit_word_label(f"ROM_RM_DLG_{ri}")
        asm.emit32(uab)
        asm.emit32(paren)
        asm.emit32(partile)
        asm.emit32(0)
        asm.emit32(0)
        asm.emit32(0)

    # Per-room tilemaps, enemies, doors, dialogues
    for (ri, _rwp, _rhp, _sxp, _syp, mhw, enw, _encnt, dw, _dcnt, dlg, _uab, _pe, _pt) in room_blobs:
        asm.align(4)
        asm.label(f"ROM_RM_MAP_{ri}")
        for hw in mhw:
            asm.emit16(hw)
        asm.align(4)
        asm.label(f"ROM_RM_EN_{ri}")
        for w in enw:
            asm.emit32(w)
        if not enw:
            asm.emit32(0)
        asm.align(4)
        asm.label(f"ROM_RM_DR_{ri}")
        for w in dw:
            asm.emit32(w)
        if not dw:
            asm.emit32(0)
        asm.align(4)
        asm.label(f"ROM_RM_DLG_{ri}")
        asm.emit_bytes(dlg)

    asm.align(4)
    asm.label("ROM_PAL_BG")
    for hw in bg_pal:
        asm.emit16(hw)

    asm.align(4)
    asm.label("ROM_PAL_OBJ")
    for hw in obj_pal:
        asm.emit16(hw)

    asm.align(4)
    asm.label("ROM_TILE_TYPES")
    asm.emit_bytes(bytes(tile_types))

    asm.align(4)
    asm.label("ROM_BG_TILES")
    asm.emit_bytes(bytes(bg_tiles_bytes))

    asm.align(4)
    asm.label("ROM_HUD_FONT")
    asm.emit_bytes(bytes(hud_font_bytes))

    asm.align(4)
    asm.label("ROM_OBJ_TILES")
    asm.emit_bytes(bytes(obj_tiles_bytes))

    asm.align(4)
    asm.label("ROM_DMA_PCM")
    asm.emit_bytes(dma_pcm_bytes)

    rom = bytearray(asm.finalize())
    target_size = max(32768, ((len(rom) + 32767) // 32768) * 32768)
    if len(rom) < target_size:
        rom.extend(b"\xFF" * (target_size - len(rom)))

    assert rom[0xBD] == compute_gba_header_checksum(bytes(rom[:0xC0]))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(rom)

    return BuildReport(
        output_path=output_path,
        rom_size=len(rom),
        format_name=f"GBA (.gba) [{project.target_system} · {len(rooms)} Room(s) · SRAM + BG2 + DMA]",
        title=clean_title,
        checksum_hex=f"0x{chk:02X}",
        bg_tiles=len(project.tiles),
        obj_tiles=next_obj_tile,
        rules_compiled=rules_count,
        enemies_compiled=total_enemies_compiled,
        sfx_compiled=sfx_count,
        rooms_compiled=len(rooms),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Native Game Boy / Game Boy Color (.gb / .gbc) 32 KB Cartridge Compiler
# ---------------------------------------------------------------------------
def _pack_tile_2bpp(grid_8x8: List[List[int]]) -> bytes:
    out = bytearray(16)
    for y in range(8):
        lo = 0
        hi = 0
        row = grid_8x8[y] if y < len(grid_8x8) else [0] * 8
        for x in range(8):
            c = (row[x] if x < len(row) else 0) & 0x3
            bit = 7 - x
            if c & 1:
                lo |= 1 << bit
            if c & 2:
                hi |= 1 << bit
        out[y * 2] = lo
        out[y * 2 + 1] = hi
    return bytes(out)


def compile_gb_rom(project: KinoPixelProject, output_path: str) -> BuildReport:
    """Emit a bootable 32 KB native Game Boy (.gb) or Game Boy Color (.gbc) ROM."""
    is_gbc = project.target_system == "GBC" or output_path.lower().endswith(".gbc")
    rom = bytearray(32768)

    rom[0x0100:0x0104] = bytes([0x00, 0xC3, 0x50, 0x01])
    rom[0x0104:0x0134] = GB_NINTENDO_LOGO
    clean_title = "".join(c if 32 <= ord(c) < 127 else " " for c in project.title.upper())[:15]
    rom[0x0134:0x0143] = clean_title.encode("ascii").ljust(15, b"\x00")
    rom[0x0143] = 0x80 if is_gbc else 0x00

    bg_off = 0x2000
    for i, t in enumerate(project.tiles[:64]):
        rom[bg_off + i * 16: bg_off + (i + 1) * 16] = _pack_tile_2bpp(t.pixels)

    hero_off = 0x2800
    if project.sprites and project.sprites[0].frames:
        fr = project.sprites[0].frames[0]
        idx = 0
        for ty in (0, 8):
            for tx in (0, 8):
                sub = [[fr[ty + y][tx + x] if (ty + y < len(fr) and tx + x < len(fr[ty + y])) else 0 for x in range(8)] for y in range(8)]
                rom[hero_off + idx * 16: hero_off + (idx + 1) * 16] = _pack_tile_2bpp(sub)
                idx += 1

    map_off = 0x3000
    for y in range(min(32, project.level.height)):
        for x in range(min(32, project.level.width)):
            rom[map_off + y * 32 + x] = project.level.get_tile(x, y) & 0x3F

    code = bytearray()

    def emit(*bs: int) -> None:
        code.extend(b & 0xFF for b in bs)

    def pc_now() -> int:
        return 0x0150 + len(code)

    emit(0xF3, 0x31, 0xFE, 0xFF)
    vbl_wait = pc_now()
    emit(0xF0, 0x44, 0xFE, 0x90, 0x38, (vbl_wait - (pc_now() + 2)) & 0xFF)
    emit(0xAF, 0xE0, 0x40)
    emit(0x3E, 0xE4, 0xE0, 0x47, 0xE0, 0x48, 0xE0, 0x49)
    emit(0x21, 0x00, 0x20, 0x11, 0x00, 0x80, 0x01, 0x00, 0x04)
    lp1 = pc_now()
    emit(0x2A, 0x12, 0x13, 0x0B, 0x78, 0xB1, 0x20, (lp1 - (pc_now() + 2)) & 0xFF)
    emit(0x21, 0x00, 0x28, 0x11, 0x00, 0x84, 0x06, 0x40)
    lp2 = pc_now()
    emit(0x2A, 0x12, 0x13, 0x05, 0x20, (lp2 - (pc_now() + 2)) & 0xFF)
    emit(0x21, 0x00, 0x30, 0x11, 0x00, 0x98, 0x01, 0x00, 0x04)
    lp3 = pc_now()
    emit(0x2A, 0x12, 0x13, 0x0B, 0x78, 0xB1, 0x20, (lp3 - (pc_now() + 2)) & 0xFF)
    emit(0x21, 0x00, 0xFE, 0x06, 0xA0, 0xAF)
    lp4 = pc_now()
    emit(0x22, 0x05, 0x20, (lp4 - (pc_now() + 2)) & 0xFF)
    sx = max(16, min(140, project.level.spawn_x * 8 + 8))
    sy = max(24, min(128, project.level.spawn_y * 8 + 16))
    emit(0x3E, sx, 0xEA, 0x00, 0xC0, 0x3E, sy, 0xEA, 0x01, 0xC0)
    emit(0x3E, 0x93, 0xE0, 0x40)

    main_gb = pc_now()
    w1 = pc_now()
    emit(0xF0, 0x44, 0xFE, 0x90, 0x30, (w1 - (pc_now() + 2)) & 0xFF)
    w2 = pc_now()
    emit(0xF0, 0x44, 0xFE, 0x90, 0x38, (w2 - (pc_now() + 2)) & 0xFF)
    emit(0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0x47)
    emit(0xCB, 0x40, 0x28, 0x07, 0xFA, 0x00, 0xC0, 0x3C, 0xEA, 0x00, 0xC0)
    emit(0xCB, 0x48, 0x28, 0x07, 0xFA, 0x00, 0xC0, 0x3D, 0xEA, 0x00, 0xC0)
    emit(0xCB, 0x50, 0x28, 0x07, 0xFA, 0x01, 0xC0, 0x3D, 0xEA, 0x01, 0xC0)
    emit(0xCB, 0x58, 0x28, 0x07, 0xFA, 0x01, 0xC0, 0x3C, 0xEA, 0x01, 0xC0)
    emit(0xFA, 0x01, 0xC0, 0xEA, 0x00, 0xFE, 0xFA, 0x00, 0xC0, 0xEA, 0x01, 0xFE, 0x3E, 64, 0xEA, 0x02, 0xFE)
    emit(0xFA, 0x01, 0xC0, 0xEA, 0x04, 0xFE, 0xFA, 0x00, 0xC0, 0xC6, 8, 0xEA, 0x05, 0xFE, 0x3E, 65, 0xEA, 0x06, 0xFE)
    emit(0xFA, 0x01, 0xC0, 0xC6, 8, 0xEA, 0x08, 0xFE, 0xFA, 0x00, 0xC0, 0xEA, 0x09, 0xFE, 0x3E, 66, 0xEA, 0x0A, 0xFE)
    emit(0xFA, 0x01, 0xC0, 0xC6, 8, 0xEA, 0x0C, 0xFE, 0xFA, 0x00, 0xC0, 0xC6, 8, 0xEA, 0x0D, 0xFE, 0x3E, 67, 0xEA, 0x0E, 0xFE)
    emit(0xC3, main_gb & 0xFF, (main_gb >> 8) & 0xFF)
    rom[0x0150:0x0150 + len(code)] = code

    hchk = 0
    for addr in range(0x0134, 0x014D):
        hchk = (hchk - rom[addr] - 1) & 0xFF
    rom[0x014D] = hchk
    gchk = (sum(rom) - rom[0x014E] - rom[0x014F]) & 0xFFFF
    rom[0x014E] = (gchk >> 8) & 0xFF
    rom[0x014F] = gchk & 0xFF

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(rom)

    return BuildReport(
        output_path=output_path,
        rom_size=len(rom),
        format_name="GBC (.gbc)" if is_gbc else "GB Classic (.gb)",
        title=clean_title,
        checksum_hex=f"0x{hchk:02X}",
        bg_tiles=min(64, len(project.tiles)),
        obj_tiles=4,
        rules_compiled=4,
        enemies_compiled=0,
        sfx_compiled=0,
        rooms_compiled=1,
        warnings=["Native GB/GBC export packs 2bpp tiles & D-Pad hero loop; export .gba for full Metroidvania engine, SRAM & DMA audio!"],
    )


def export_c_source(project: KinoPixelProject, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    lines = [
        f"/* Generated by KinoPixel v2.0 (KinoSuite) — {project.title} ({project.target_system}) */",
        "#pragma once",
        "#include <stdint.h>",
        "",
        f"#define KP_ROOM_COUNT {len(project.rooms)}",
        f"#define KP_LEVEL_W {project.level.width}",
        f"#define KP_LEVEL_H {project.level.height}",
        "",
        "static const uint16_t KP_PALETTE[16] = {",
    ]
    pal = project.get_palette_colors(0)
    lines.append("    " + ", ".join(f"0x{hex_to_bgr555(c):04X}" for c in pal[:16]))
    lines.append("};")
    out_path = os.path.join(output_dir, "kinopixel_assets.h")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_path
