"""Built-in handcrafted playable starter templates for KinoPixel (GBA / GBC / GB)."""
from __future__ import annotations

from typing import Dict, List

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
    ACTION_RESET_LEVEL,
    ACTION_SHOOT,
    AnimationClip,
    ButtonRule,
    EntityPlacement,
    KinoPixelProject,
    LevelMap,
    PRESET_PALETTES,
    SfxPatch,
    SpriteAsset,
    TILE_BOUNCE,
    TILE_COIN,
    TILE_EMPTY,
    TILE_GOAL,
    TILE_HAZARD,
    TILE_ONEWAY,
    TILE_SOLID,
    TRIGGER_HELD,
    TRIGGER_PRESSED,
    TileAsset,
    empty_grid,
)


def _parse_art(lines: List[str], legend: Dict[str, int]) -> List[List[int]]:
    grid: List[List[int]] = []
    for row in lines:
        grid.append([legend.get(ch, 0) for ch in row])
    return grid


def _make_hero_frames() -> List[List[List[int]]]:
    # 16x16 adorable retro knight/adventurer sprite (0=transparent)
    # 1=dark outline, 2=white eye/highlight, 5=violet tunic, 6=lilac highlight,
    # 7=mint visor/cape, 9=gold trim, 13=cyan boot/gem
    leg = {
        ".": 0, "#": 1, "W": 2, "S": 3, "G": 4,
        "V": 5, "L": 6, "M": 7, "E": 8, "Y": 9,
        "K": 10, "R": 11, "C": 13, "B": 14, "D": 15,
    }
    idle0 = _parse_art([
        ".....######.....",
        "....#VVLLVV#....",
        "...#VVLLLLVV#...",
        "...#VYYYYYYV#...",
        "...#S######S#...",
        "...#S#W##W#S#...",
        "...#SS####SS#...",
        "....#SSSSSS#....",
        "...##MMVVMM##...",
        "..#MMMVVVVMMM#..",
        "..#MMVYYYYVMM#..",
        "...##VVVVVV##...",
        "....#VV..VV#....",
        "....#CC..CC#....",
        "....#CC..CC#....",
        "....###..###....",
    ], leg)
    idle1 = _parse_art([
        "................",
        ".....######.....",
        "....#VVLLVV#....",
        "...#VVLLLLVV#...",
        "...#VYYYYYYV#...",
        "...#S######S#...",
        "...#S#W##W#S#...",
        "...#SS####SS#...",
        "....#SSSSSS#....",
        "...##MMVVMM##...",
        "..#MMMVVVVMMM#..",
        "..#MMVYYYYVMM#..",
        "...##VVVVVV##...",
        "....#CC..CC#....",
        "....#CC..CC#....",
        "....###..###....",
    ], leg)
    walk0 = _parse_art([
        ".....######.....",
        "....#VVLLVV#....",
        "...#VVLLLLVV#...",
        "...#VYYYYYYV#...",
        "...#S######S#...",
        "...#S#W##W#S#...",
        "...#SS####SS#...",
        "....#SSSSSS#....",
        "..###MMVVMM#....",
        ".#MMMMVVVVMM#...",
        "..###VYYYYVM#...",
        "....#VVVVVV#....",
        "...#VV....VV#...",
        "..#CC......CC#..",
        "..###......###..",
        "................",
    ], leg)
    walk1 = _parse_art([
        ".....######.....",
        "....#VVLLVV#....",
        "...#VVLLLLVV#...",
        "...#VYYYYYYV#...",
        "...#S######S#...",
        "...#S#W##W#S#...",
        "...#SS####SS#...",
        "....#SSSSSS#....",
        "....#MMVVMM###..",
        "...#MMVVVVMMMM#.",
        "...#MVYYYYV###..",
        "....#VVVVVV#....",
        ".....#VVVV#.....",
        ".....#CC.CC#....",
        ".....###.###....",
        "................",
    ], leg)
    jump0 = _parse_art([
        "....########....",
        "...#VVLLLLVV#...",
        "...#VYYYYYYV#...",
        "...#S######S#...",
        "...#S#W##W#S#...",
        "....#SSSSSS#....",
        "..##MMMVVMMM##..",
        ".#MMMMVVVVMMMM#.",
        ".##MMVYYYYVMM##.",
        "...##VVVVVV##...",
        "..#VV#....#VV#..",
        "..#CC#....#CC#..",
        "..###......###..",
        "................",
        "................",
        "................",
    ], leg)
    attack0 = _parse_art([
        ".....######.....",
        "....#VVLLVV#....",
        "...#VVLLLLVV#...",
        "...#VYYYYYYV#...",
        "...#S######S#...",
        "...#S#W##W#S#...",
        "....#SSSSSS#....",
        "...##MMVVMM###..",
        "..#MMMVVVVMMKK#.",
        "..#MMVYYYYVMKKW#",
        "...##VVVVVV#KK#.",
        "....#VV..VV###..",
        "....#CC..CC#....",
        "....#CC..CC#....",
        "....###..###....",
        "................",
    ], leg)
    return [idle0, idle1, walk0, walk1, jump0, attack0]


def _make_slime_frames() -> List[List[List[int]]]:
    leg = {".": 0, "#": 1, "W": 2, "R": 11, "P": 12, "Y": 9, "K": 10}
    f0 = _parse_art([
        "................",
        "................",
        "................",
        "................",
        ".....######.....",
        "...##RRRRRR##...",
        "..#RRPPPPPPRR#..",
        ".#RRPPRRRRPPPR#.",
        ".#RR#W#RR#W#RR#.",
        ".#RR###RR###RR#.",
        ".#RRRRRRRRRRRR#.",
        ".#RRRRYYYYRRRR#.",
        ".#RRRRRRRRRRRR#.",
        "..#RRRRRRRRRR#..",
        "...##########...",
        "................",
    ], leg)
    f1 = _parse_art([
        "................",
        "................",
        "................",
        "................",
        "................",
        "....########....",
        "..##RRRRRRRR##..",
        ".#RRPPPPPPPPRR#.",
        "#RRPPRRRRRRPPPR#",
        "#RR#W#RRRR#W#RR#",
        "#RR###RRRR###RR#",
        "#RRRRRRRRRRRRRR#",
        "#RRRRRYYYYRRRRR#",
        ".#RRRRRRRRRRRR#.",
        "..############..",
        "................",
    ], leg)
    return [f0, f1]


def _make_projectile_frames() -> List[List[List[int]]]:
    leg = {".": 0, "#": 1, "W": 2, "Y": 9, "K": 10, "R": 11, "C": 13}
    f0 = _parse_art([
        "................",
        "................",
        "................",
        "................",
        "......####......",
        "....##KKKK##....",
        "...#KKWWWWKK#...",
        "...#KWWYYWWK#...",
        "...#KWWYYWWK#...",
        "...#KKWWWWKK#...",
        "....##KKKK##....",
        "......####......",
        "................",
        "................",
        "................",
        "................",
    ], leg)
    f1 = _parse_art([
        "................",
        "................",
        "................",
        ".......##.......",
        ".....#RRRR#.....",
        "....#RKKKKR#....",
        "...#RKWWWWKR#...",
        "...#RKWWWWKR#...",
        "...#RKWWWWKR#...",
        "....#RKKKKR#....",
        ".....#RRRR#.....",
        ".......##.......",
        "................",
        "................",
        "................",
        "................",
    ], leg)
    return [f0, f1]


def _make_default_tiles() -> List[TileAsset]:
    leg = {
        ".": 0, "#": 1, "W": 2, "S": 3, "G": 4,
        "V": 5, "L": 6, "M": 7, "E": 8, "Y": 9,
        "K": 10, "R": 11, "P": 12, "C": 13, "B": 14, "D": 15,
    }
    tiles = [
        # 0: Empty Sky
        TileAsset("Sky / Empty", TILE_EMPTY, 0, empty_grid(8, 8, 0)),
        # 1: Grass Top Ground (Solid)
        TileAsset("Grass Ground", TILE_SOLID, 0, _parse_art([
            "MMMMMMMM",
            "MEEMMEEM",
            "EEDDDDEE",
            "DDDDDDDD",
            "DD#DDDD#",
            "DDDDDDDD",
            "D#DDDDDD",
            "DDDD#DDD",
        ], leg)),
        # 2: Deep Dirt / Brick (Solid)
        TileAsset("Stone Brick", TILE_SOLID, 0, _parse_art([
            "########",
            "#GGG#GGG",
            "#G##G##G",
            "########",
            "GGG#GGG#",
            "##G##G##",
            "########",
            "#GGG#GGG",
        ], leg)),
        # 3: Floating Platform (One-Way)
        TileAsset("Cloud Platform", TILE_ONEWAY, 0, _parse_art([
            ".WWWWWW.",
            "WWCCCCWW",
            "WCCCCCCW",
            ".BBBBBB.",
            "........",
            "........",
            "........",
            "........",
        ], leg)),
        # 4: Star Coin (Collectible)
        TileAsset("Star Coin", TILE_COIN, 0, _parse_art([
            "...YY...",
            "..YKKY..",
            ".YKWKKY.",
            ".YKKKKY.",
            ".YKKKKY.",
            "..YKKY..",
            "...YY...",
            "........",
        ], leg)),
        # 5: Crimson Spikes (Hazard)
        TileAsset("Spikes", TILE_HAZARD, 0, _parse_art([
            "........",
            "........",
            ".#....#.",
            ".R....R.",
            "#R#..#R#",
            "RPR..RPR",
            "RR#..#RR",
            "########",
        ], leg)),
        # 6: Bounce Spring
        TileAsset("Spring Pad", TILE_BOUNCE, 0, _parse_art([
            "........",
            "........",
            ".RRRRRR.",
            ".PPPPPP.",
            "..YYYY..",
            "..#YY#..",
            ".#YYYY#.",
            "########",
        ], leg)),
        # 7: Goal Portal / Flag
        TileAsset("Goal Portal", TILE_GOAL, 0, _parse_art([
            "..LLLL..",
            ".LVWWVL.",
            "LVWMMWVL",
            "LVWMMWVL",
            "LVWMMWVL",
            "LVWMMWVL",
            ".LVWWVL.",
            "..LLLL..",
        ], leg)),
        # 8: Decorative Starry Night Accent (Empty / Passable)
        TileAsset("BG Star", TILE_EMPTY, 0, _parse_art([
            "........",
            "........",
            "...L....",
            "..LWL...",
            "...L....",
            "........",
            "........",
            "........",
        ], leg)),
        # 9: Dungeon Wall (Solid)
        TileAsset("Violet Pillar", TILE_SOLID, 0, _parse_art([
            "########",
            "#LVVVVL#",
            "#L#VV#L#",
            "#LVVVVL#",
            "#LVVVVL#",
            "#L#VV#L#",
            "#LVVVVL#",
            "########",
        ], leg)),
    ]
    return tiles


def _make_default_sfx() -> List[SfxPatch]:
    return [
        SfxPatch("Jump", channel=1, freq_hz=320, duty=2, volume=13, env_step=2, sweep_time=1, sweep_dir=0, sweep_shift=3, duration_ms=160),
        SfxPatch("Star Coin", channel=1, freq_hz=920, duty=1, volume=13, env_step=2, sweep_time=1, sweep_dir=0, sweep_shift=2, duration_ms=150),
        SfxPatch("Fireball", channel=1, freq_hz=620, duty=0, volume=12, env_step=2, sweep_time=1, sweep_dir=1, sweep_shift=2, duration_ms=140),
        SfxPatch("Dash Whoosh", channel=4, volume=12, env_step=2, noise_div=2, noise_shift=3, noise_short=False, duration_ms=130),
        SfxPatch("Hurt / Hit", channel=4, volume=14, env_step=3, noise_div=4, noise_shift=5, noise_short=True, duration_ms=220),
        SfxPatch("Stage Clear", channel=1, freq_hz=523, duty=2, volume=14, env_step=3, sweep_time=2, sweep_dir=0, sweep_shift=2, duration_ms=340),
    ]


def create_starter_project(template: str = "GBA Platformer") -> KinoPixelProject:
    """Create a polished, ready-to-play starter project for GBA, GBC, or GB."""
    is_topdown = "Top-Down" in template
    if "GB Classic" in template or "DMG" in template:
        target = "GB"
        pals = [
            list(PRESET_PALETTES["DMG Classic Olive"]),
            list(PRESET_PALETTES["Game Boy Pocket"]),
            list(PRESET_PALETTES["DMG Classic Olive"]),
        ]
        bg_hex = "#9BBC0F"
        title = "DMG QUEST"
    elif "GBC" in template:
        target = "GBC"
        pals = [
            list(PRESET_PALETTES["GBC Pastel Quest"]),
            list(PRESET_PALETTES["GBA Crimson Hero"]),
            list(PRESET_PALETTES["GBA Emerald Knight"]),
        ]
        bg_hex = "#181828"
        title = "COLOR QUEST"
    else:
        target = "GBA"
        pals = [
            list(PRESET_PALETTES["GBA Starbit Retro"]),
            list(PRESET_PALETTES["GBA Crimson Hero"]),
            list(PRESET_PALETTES["GBA Emerald Knight"]),
        ]
        bg_hex = "#101424"
        title = "STARBIT RPG" if is_topdown else "STARBIT GBA"

    hero = SpriteAsset(
        name="Hero",
        role="player",
        width=16,
        height=16,
        palette_index=0,
        frames=_make_hero_frames(),
        animations=[
            AnimationClip("idle", [0, 1], fps=4, loop=True),
            AnimationClip("walk", [2, 3], fps=10, loop=True),
            AnimationClip("jump", [4], fps=8, loop=False),
            AnimationClip("attack", [5, 0], fps=12, loop=False),
        ],
    )
    slime = SpriteAsset(
        name="Crimson Slime",
        role="enemy",
        width=16,
        height=16,
        palette_index=0,
        frames=_make_slime_frames(),
        animations=[AnimationClip("walk", [0, 1], fps=6, loop=True)],
    )
    fireball = SpriteAsset(
        name="Star Bolt",
        role="projectile",
        width=16,
        height=16,
        palette_index=0,
        frames=_make_projectile_frames(),
        animations=[AnimationClip("fly", [0, 1], fps=12, loop=True)],
    )

    tiles = _make_default_tiles()
    sfx = _make_default_sfx()

    # Build level layout
    w, h = (48, 20) if target == "GBA" else (32, 18)
    cells = empty_grid(w, h, 0)

    if is_topdown:
        # Top-down dungeon room with walls, coins, hazards, enemies, and portal
        for x in range(w):
            cells[0][x] = 9
            cells[h - 1][x] = 9
        for y in range(h):
            cells[y][0] = 9
            cells[y][w - 1] = 9
        # Inner walls / maze dividers
        for y in range(2, h - 5):
            cells[y][10] = 2
        for y in range(5, h - 2):
            cells[y][20] = 2
        for x in range(12, 19):
            cells[8][x] = 2
        # Coins & Goal
        for cx, cy in [(5, 4), (6, 4), (14, 5), (16, 5), (15, 13), (25, 6), (27, 6)]:
            if cx < w - 2 and cy < h - 2:
                cells[cy][cx] = 4
        cells[h // 2][w - 4] = 7
        cells[12][14] = 5
        cells[12][15] = 5
        level = LevelMap(
            name="Dungeon 1 — Violet Sanctum",
            width=w,
            height=h,
            spawn_x=3,
            spawn_y=h // 2,
            cells=cells,
            entities=[
                EntityPlacement(kind="enemy", sprite_index=1, tile_x=13, tile_y=4, patrol_range=4, speed=1),
                EntityPlacement(kind="enemy", sprite_index=1, tile_x=24, tile_y=12, patrol_range=5, speed=1),
            ],
        )
        rules = [
            ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
            ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
            ButtonRule(button="UP", trigger=TRIGGER_HELD, action=ACTION_MOVE_UP, param=2, anim_name="walk", sfx_index=-1),
            ButtonRule(button="DOWN", trigger=TRIGGER_HELD, action=ACTION_MOVE_DOWN, param=2, anim_name="walk", sfx_index=-1),
            ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=4, anim_name="attack", sfx_index=2),
            ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_DASH, param=5, anim_name="jump", sfx_index=3),
            ButtonRule(button="SELECT", trigger=TRIGGER_PRESSED, action=ACTION_PALETTE_NEXT, param=1, anim_name="", sfx_index=1),
            ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="", sfx_index=-1),
        ]
    else:
        # Side-scrolling Platformer Stage!
        ground_y = h - 3
        # Starry background accents
        for sx, sy in [(4, 3), (11, 2), (18, 4), (26, 2), (34, 3), (42, 4)]:
            if sx < w - 1:
                cells[sy][sx] = 8
        # Main grass floor with a small jumpable pit
        for x in range(w):
            if 15 <= x <= 17 and w >= 40:
                continue
            cells[ground_y][x] = 1
            for yy in range(ground_y + 1, h):
                cells[yy][x] = 2
        # Left & right boundary walls
        for y in range(h):
            cells[y][0] = 9
            cells[y][w - 1] = 9
        # Platforms, coins, bounce pad, spikes, elevated pillar, goal portal
        for x in range(7, 12):
            cells[ground_y - 4][x] = 3
            cells[ground_y - 5][x] = 4 if x % 2 == 1 else 0
        cells[ground_y - 1][13] = 6  # Spring pad before gap!
        for x in range(19, 25):
            if x < w - 2:
                cells[ground_y - 5][x] = 3
                cells[ground_y - 6][x] = 4 if x % 2 == 0 else 0
        # Spikes hazard & bridge
        if w >= 40:
            cells[ground_y - 1][26] = 5
            cells[ground_y - 1][27] = 5
            for x in range(29, 35):
                cells[ground_y - 3][x] = 2
                cells[ground_y - 4][x] = 4 if x % 2 == 1 else 0
            for x in range(36, 41):
                cells[ground_y - 6][x] = 3
            cells[ground_y - 7][38] = 4
            cells[ground_y - 1][w - 4] = 7  # Goal Portal!
            entities = [
                EntityPlacement(kind="enemy", sprite_index=1, tile_x=11, tile_y=ground_y - 2, patrol_range=3, speed=1),
                EntityPlacement(kind="enemy", sprite_index=1, tile_x=22, tile_y=ground_y - 2, patrol_range=3, speed=1),
                EntityPlacement(kind="enemy", sprite_index=1, tile_x=38, tile_y=ground_y - 2, patrol_range=4, speed=1),
            ]
        else:
            cells[ground_y - 1][18] = 5
            cells[ground_y - 1][w - 4] = 7
            entities = [
                EntityPlacement(kind="enemy", sprite_index=1, tile_x=10, tile_y=ground_y - 2, patrol_range=3, speed=1),
                EntityPlacement(kind="enemy", sprite_index=1, tile_x=23, tile_y=ground_y - 2, patrol_range=3, speed=1),
            ]

        level = LevelMap(
            name="Stage 1 — Starbit Meadow",
            width=w,
            height=h,
            spawn_x=3,
            spawn_y=ground_y - 2,
            cells=cells,
            entities=entities,
        )
        rules = [
            ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
            ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
            ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_JUMP, param=5, anim_name="jump", sfx_index=0),
            ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=4, anim_name="attack", sfx_index=2),
            ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_DASH, param=5, anim_name="jump", sfx_index=3),
            ButtonRule(button="L", trigger=TRIGGER_PRESSED, action=ACTION_MELEE, param=3, anim_name="attack", sfx_index=3),
            ButtonRule(button="SELECT", trigger=TRIGGER_PRESSED, action=ACTION_PALETTE_NEXT, param=1, anim_name="", sfx_index=1),
            ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_RESET_LEVEL, param=0, anim_name="idle", sfx_index=-1),
        ]
        if target in ("GB", "GBC"):
            # Keep only buttons present on GB/GBC
            rules = [r for r in rules if r.button not in ("L", "R")]

    proj = KinoPixelProject(
        title=title,
        game_code="KPIX",
        maker_code="KP",
        target_system=target,
        physics_mode="topdown" if is_topdown else "platformer",
        gravity=42,
        max_fall_speed=768,
        bg_color_hex=bg_hex,
        palettes=pals,
        sprites=[hero, slime, fireball],
        tiles=tiles,
        level=level,
        button_rules=rules,
        sfx_list=sfx,
    )
    proj.sequence_genie.ensure_initialized()
    proj.sequence_genie.scale = "DOR" if is_topdown else "PENTA MIN"
    proj.sequence_genie.bpm = 118 if is_topdown else 134
    proj.sequence_genie.save_slot(0)
    proj.snapshot_push("Initial Project")
    proj.dirty = False
    return proj
