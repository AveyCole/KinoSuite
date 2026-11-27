"""Built-in handcrafted playable starter templates for KinoPixel v2.0 (GBA / GBC / GB + Metroidvania BSL Sector)."""
from __future__ import annotations

from typing import Dict, List

from .models import (
    ABIL_HIGH_JUMP,
    ABIL_MISSILES,
    ABIL_MORPH_BALL,
    ABIL_NONE,
    ABIL_WALL_JUMP,
    ACTION_AIM_UP,
    ACTION_BOMB,
    ACTION_DASH,
    ACTION_JUMP,
    ACTION_MELEE,
    ACTION_MORPH_BALL,
    ACTION_MOVE_DOWN,
    ACTION_MOVE_LEFT,
    ACTION_MOVE_RIGHT,
    ACTION_MOVE_UP,
    ACTION_PALETTE_NEXT,
    ACTION_PAUSE,
    ACTION_RESET_LEVEL,
    ACTION_SHOOT,
    AI_BOSS,
    AI_CHASER,
    AI_PATROL,
    AI_TURRET,
    AnimationClip,
    ButtonRule,
    DirectSoundConfig,
    DoorLink,
    EntityPlacement,
    KinoPixelProject,
    LevelMap,
    PRESET_PALETTES,
    SfxPatch,
    SpriteAsset,
    TILE_BOUNCE,
    TILE_BREAKABLE,
    TILE_COIN,
    TILE_DOOR,
    TILE_EMPTY,
    TILE_GOAL,
    TILE_HAZARD,
    TILE_ONEWAY,
    TILE_SAVE,
    TILE_SOLID,
    TILE_TERMINAL,
    TILE_UPGRADE,
    TRIGGER_HELD,
    TRIGGER_PRESSED,
    TileAsset,
    empty_grid,
)


def _parse_art(lines: List[str], legend: Dict[str, int]) -> List[List[int]]:
    return [[legend.get(ch, 0) for ch in row] for row in lines]


def _make_hero_frames() -> List[List[List[int]]]:
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


def _make_hunter_16x32_frames() -> List[List[List[int]]]:
    """16x32 Fusion-style Armored Sci-Fi Bounty Hunter metasprite!"""
    leg = {".": 0, "#": 1, "W": 2, "S": 3, "G": 4, "B": 5, "C": 6, "Y": 7, "O": 8, "E": 9, "M": 10, "R": 11, "P": 13}
    base_idle = [
        ".....######.....",
        "....#BBBBBB#....",
        "...#BBCCCCBB#...",
        "...#BCWWWWCB#...",
        "...#B#EEEE#B#...",
        "...#B#EMME#B#...",
        "....#BBBBBB#....",
        ".....#YYYY#.....",
        "..####YYYY####..",
        ".#CCCCBBBBCCCC#.",
        ".#CCCBBBBBBCCC#.",
        ".#CC#BBYYBB#GG#.",
        "..##.BBYYBB#GGG#",
        ".....#BBBB#GGWG#",
        ".....#BBBB#GGGG#",
        ".....#YYYY#.##..",
        ".....#BBBB#.....",
        "....#BBYYBB#....",
        "....#BB..BB#....",
        "....#BB..BB#....",
        "....#CC..CC#....",
        "....#CC..CC#....",
        "....#BB..BB#....",
        "....#BB..BB#....",
        "....#YY..YY#....",
        "....#YY..YY#....",
        "....#BB..BB#....",
        "....#BB..BB#....",
        "...#BBB..BBB#...",
        "...#CCC..CCC#...",
        "...####..####...",
        "................",
    ]
    walk0 = list(base_idle)
    walk0[26] = "...#BB....BB#..."
    walk0[27] = "..#BB......BB#.."
    walk0[28] = "..#CC......CC#.."
    walk0[29] = "..###......###.."
    walk0[30] = "................"

    walk1 = list(base_idle)
    walk1[26] = ".....#BBBB#....."
    walk1[27] = ".....#CCCC#....."
    walk1[28] = ".....#BBBB#....."
    walk1[29] = "....########...."

    jump0 = list(base_idle)
    jump0[22] = "...#BB....BB#..."
    jump0[23] = "...#YY....YY#..."
    jump0[24] = "...#CC....CC#..."
    jump0[25] = "...###....###..."
    for r in range(26, 31):
        jump0[r] = "................"

    attack0 = list(base_idle)
    attack0[12] = "..##.BBYYBB#GGMM"
    attack0[13] = ".....#BBBB#GGWWM"
    attack0[14] = ".....#BBBB#GGMM."

    return [_parse_art(f, leg) for f in (base_idle, walk0, walk1, jump0, attack0)]


def _make_morph_ball_frames() -> List[List[List[int]]]:
    leg = {".": 0, "#": 1, "W": 2, "B": 5, "C": 6, "Y": 7, "E": 9, "M": 10}
    f0 = _parse_art([
        "................",
        "................",
        ".....######.....",
        "...##BBCCBB##...",
        "..#BBCCCCCCBB#..",
        ".#BCWCCEECCBCB#.",
        ".#BCCCEMMECCCB#.",
        ".#BYYCEEEECYYB#.",
        ".#BYYCCCCCCYYB#.",
        ".#BCCCCCCCCCCB#.",
        "..#BBBBBBBBBB#..",
        "...##BBBBBB##...",
        ".....######.....",
        "................",
        "................",
        "................",
    ], leg)
    f1 = _parse_art([
        "................",
        "................",
        ".....######.....",
        "...##BBYYBB##...",
        "..#BBYYYYYYBB#..",
        ".#BCCCCEECCCCB#.",
        ".#BCCCEMMECCCB#.",
        ".#BCCCCCCWCCCB#.",
        ".#BCCCCCCCCCCB#.",
        ".#BBCCCCCCCCBB#.",
        "..#BBBBBBBBBB#..",
        "...##BBBBBB##...",
        ".....######.....",
        "................",
        "................",
        "................",
    ], leg)
    return [f0, f1]


def _make_boss_32x32_frames() -> List[List[List[int]]]:
    """32x32 Omega Core Metroidvania Boss Metasprite!"""
    g = empty_grid(32, 32, 0)
    # Build armored bio-mechanical core shell + glowing crimson eye + claws
    for y in range(32):
        for x in range(32):
            dx = x - 15.5
            dy = y - 15.5
            d2 = dx * dx + dy * dy
            if 110 <= d2 <= 195:
                g[y][x] = 1  # Dark armor rim
            elif 42 <= d2 < 110:
                g[y][x] = 13 if ((x + y) % 3 == 0) else 5  # Violet/Blue bio-armor
            elif 16 <= d2 < 42:
                g[y][x] = 11  # Crimson core ring
            elif d2 < 16:
                g[y][x] = 2 if (dx < 0 and dy < 0) else 7  # Glowing yellow/white eye
    # Side pincers/claws
    for y in range(22, 30):
        g[y][4] = 1; g[y][5] = 7; g[y][6] = 1
        g[y][25] = 1; g[y][26] = 7; g[y][27] = 1
    return [g]


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
    return [
        TileAsset("Sky / Empty", TILE_EMPTY, 0, empty_grid(8, 8, 0)),
        TileAsset("Grass / Deck", TILE_SOLID, 0, _parse_art([
            "MMMMMMMM", "MEEMMEEM", "EEDDDDEE", "DDDDDDDD",
            "DD#DDDD#", "DDDDDDDD", "D#DDDDDD", "DDDD#DDD",
        ], leg)),
        TileAsset("Steel / Brick", TILE_SOLID, 0, _parse_art([
            "########", "#GGG#GGG", "#G##G##G", "########",
            "GGG#GGG#", "##G##G##", "########", "#GGG#GGG",
        ], leg)),
        TileAsset("One-Way Grate", TILE_ONEWAY, 0, _parse_art([
            ".WWWWWW.", "WWCCCCWW", "WCCCCCCW", ".BBBBBB.",
            "........", "........", "........", "........",
        ], leg)),
        TileAsset("Star / Energy", TILE_COIN, 0, _parse_art([
            "...YY...", "..YKKY..", ".YKWKKY.", ".YKKKKY.",
            ".YKKKKY.", "..YKKY..", "...YY...", "........",
        ], leg)),
        TileAsset("Spikes / Acid", TILE_HAZARD, 0, _parse_art([
            "........", "........", ".#....#.", ".R....R.",
            "#R#..#R#", "RPR..RPR", "RR#..#RR", "########",
        ], leg)),
        TileAsset("Spring Pad", TILE_BOUNCE, 0, _parse_art([
            "........", "........", ".RRRRRR.", ".PPPPPP.",
            "..YYYY..", "..#YY#..", ".#YYYY#.", "########",
        ], leg)),
        TileAsset("Goal / Escape", TILE_GOAL, 0, _parse_art([
            "..LLLL..", ".LVWWVL.", "LVWMMWVL", "LVWMMWVL",
            "LVWMMWVL", "LVWMMWVL", ".LVWWVL.", "..LLLL..",
        ], leg)),
        TileAsset("Parallax Grid", TILE_EMPTY, 0, _parse_art([
            "........", "........", "...L....", "..LWL...",
            "...L....", "........", "........", "........",
        ], leg)),
        TileAsset("Armor Wall", TILE_SOLID, 0, _parse_art([
            "########", "#LVVVVL#", "#L#VV#L#", "#LVVVVL#",
            "#LVVVVL#", "#L#VV#L#", "#LVVVVL#", "########",
        ], leg)),
        # v2.0 Metroidvania Tiles (10..14)!
        TileAsset("Cracked Block", TILE_BREAKABLE, 0, _parse_art([
            "########", "#YY##YY#", "#Y#YY#Y#", "##YYYY##",
            "#Y#YY#Y#", "#YY##YY#", "#Y####Y#", "########",
        ], leg)),
        TileAsset("Hatch Door", TILE_DOOR, 0, _parse_art([
            "##CCCC##", "#CCWWCC#", "#CWWWWC#", "#CCWWCC#",
            "#CCWWCC#", "#CWWWWC#", "#CCWWCC#", "##CCCC##",
        ], leg)),
        TileAsset("Save Station", TILE_SAVE, 0, _parse_art([
            "........", "..MMMM..", ".MMWWMM.", ".MWMMWM.",
            "..MMMM..", "..#MM#..", ".#MMMM#.", "########",
        ], leg)),
        TileAsset("Upgrade Orb", TILE_UPGRADE, 0, _parse_art([
            "..####..", ".#KKKK#.", "#KKWWKK#", "#KWWWWK#",
            "#KKWWKK#", ".#KKKK#.", "..####..", "........",
        ], leg)),
        TileAsset("Nav Terminal", TILE_TERMINAL, 0, _parse_art([
            ".######.", "#CCCCCC#", "#CWWWWC#", "#CCCCCC#",
            ".######.", "...##...", "..####..", ".######.",
        ], leg)),
    ]


def _make_default_sfx() -> List[SfxPatch]:
    return [
        SfxPatch("Jump", channel=1, freq_hz=320, duty=2, volume=13, env_step=2, sweep_time=1, sweep_dir=0, sweep_shift=3, duration_ms=160),
        SfxPatch("Pickup / Save", channel=1, freq_hz=920, duty=1, volume=13, env_step=2, sweep_time=1, sweep_dir=0, sweep_shift=2, duration_ms=150),
        SfxPatch("Arm Cannon", channel=1, freq_hz=680, duty=0, volume=12, env_step=2, sweep_time=1, sweep_dir=1, sweep_shift=2, duration_ms=130),
        SfxPatch("Dash / Morph", channel=4, volume=12, env_step=2, noise_div=2, noise_shift=3, noise_short=False, duration_ms=130),
        SfxPatch("Hurt / Blast", channel=4, volume=14, env_step=3, noise_div=4, noise_shift=5, noise_short=True, duration_ms=220),
        SfxPatch("Upgrade / Clear", channel=1, freq_hz=523, duty=2, volume=14, env_step=3, sweep_time=2, sweep_dir=0, sweep_shift=2, duration_ms=340),
    ]


def _create_bsl_metroidvania() -> KinoPixelProject:
    """Create a complete 3-room Metroid Fusion-inspired GBA Metroidvania ('BSL SECTOR')!"""
    pals = [
        list(PRESET_PALETTES["BSL Fusion Station"]),
        list(PRESET_PALETTES["GBA Crimson Hero"]),
        list(PRESET_PALETTES["GBA Emerald Knight"]),
    ]
    hunter = SpriteAsset(
        name="Fusion Hunter (16×32)",
        role="player",
        width=16,
        height=32,
        palette_index=0,
        frames=_make_hunter_16x32_frames(),
        animations=[
            AnimationClip("idle", [0], fps=4, loop=True),
            AnimationClip("walk", [1, 2], fps=10, loop=True),
            AnimationClip("jump", [3], fps=8, loop=False),
            AnimationClip("attack", [4, 0], fps=12, loop=False),
        ],
    )
    slime = SpriteAsset(
        name="X-Parasite Stalker",
        role="enemy",
        width=16,
        height=16,
        palette_index=0,
        frames=_make_slime_frames(),
        animations=[AnimationClip("walk", [0, 1], fps=6, loop=True)],
    )
    beam = SpriteAsset(
        name="Plasma Beam",
        role="projectile",
        width=16,
        height=16,
        palette_index=0,
        frames=_make_projectile_frames(),
        animations=[AnimationClip("fly", [0, 1], fps=12, loop=True)],
    )
    morph = SpriteAsset(
        name="Morph Ball",
        role="morph",
        width=16,
        height=16,
        palette_index=0,
        frames=_make_morph_ball_frames(),
        animations=[AnimationClip("roll", [0, 1], fps=10, loop=True)],
    )
    boss = SpriteAsset(
        name="Omega Core Boss (32×32)",
        role="boss",
        width=32,
        height=32,
        palette_index=0,
        frames=_make_boss_32x32_frames(),
        animations=[AnimationClip("idle", [0], fps=6, loop=True)],
    )

    tiles = _make_default_tiles()
    sfx = _make_default_sfx()

    # --- Room 0: Main Deck & Nav Room (Save Station, Adam Terminal, Morph Ball Orb, Hatch East!) ---
    w, h = 44, 20
    c0 = empty_grid(w, h, 0)
    for x in range(w):
        c0[0][x] = 9; c0[h - 2][x] = 2; c0[h - 1][x] = 9
    for y in range(h):
        c0[y][0] = 9; c0[y][w - 1] = 9
    c0[h - 3][6] = 14   # Adam Navigation Terminal!
    c0[h - 3][11] = 12  # SRAM Save Station!
    # Platform leading to Morph Ball Upgrade Orb
    for x in range(16, 23):
        c0[h - 6][x] = 3
    c0[h - 7][19] = 13  # Morph Ball Upgrade Orb!
    # Cracked Destructible Wall before East Hatch
    for y in range(h - 6, h - 2):
        c0[y][30] = 10  # Destructible Cracked Block!
    # East Hatch to Room 1 (requires Morph Ball!)
    c0[h - 4][w - 2] = 11
    c0[h - 3][w - 2] = 11
    rm0 = LevelMap(
        name="Sector 1 — Main Deck",
        width=w, height=h, spawn_x=3, spawn_y=h - 6, cells=c0,
        entities=[
            EntityPlacement(kind="enemy", ai_type=AI_PATROL, sprite_index=1, tile_x=24, tile_y=h - 4, patrol_range=4, speed=1, hp=2),
        ],
        doors=[DoorLink(tile_x=w - 2, tile_y=h - 3, target_room=1, target_x=3, target_y=h - 6, req_ability=ABIL_MORPH_BALL)],
        dialogue_text="ADAM: X-CORE IN SEC 3.  GET MORPH BALL FIRST!",
        upgrade_ability=ABIL_MORPH_BALL,
        parallax_enabled=True, parallax_tile_idx=8,
    )

    # --- Room 1: Morph Tunnel & Bio-Lab (Low 16px Morph Tunnel, SA-X Chaser, Turret, Missiles Orb!) ---
    c1 = empty_grid(w, h, 0)
    for x in range(w):
        c1[0][x] = 9; c1[h - 2][x] = 2; c1[h - 1][x] = 9
    for y in range(h):
        c1[y][0] = 9; c1[y][w - 1] = 9
    # West Hatch back to Room 0
    c1[h - 4][1] = 11; c1[h - 3][1] = 11
    # Low 2-tile-high (16px!) Morph Ball Tunnel wall (standing 32px Hunter MUST morph to pass!)
    for y in range(1, h - 4):
        for x in range(13, 20):
            c1[y][x] = 9
    # Cracked block inside tunnel
    c1[h - 3][16] = 10
    # Elevated Missile Upgrade Orb
    for x in range(25, 31):
        c1[h - 6][x] = 3
    c1[h - 7][28] = 13  # Missiles / Bombs Upgrade!
    # Acid pit
    c1[h - 3][33] = 5; c1[h - 3][34] = 5
    # East Hatch to Room 2 (Boss Chamber!)
    c1[h - 4][w - 2] = 11; c1[h - 3][w - 2] = 11
    rm1 = LevelMap(
        name="Sector 2 — Morph Lab",
        width=w, height=h, spawn_x=3, spawn_y=h - 6, cells=c1,
        entities=[
            EntityPlacement(kind="enemy", ai_type=AI_CHASER, sprite_index=1, tile_x=24, tile_y=h - 4, patrol_range=6, speed=1, hp=3),
            EntityPlacement(kind="enemy", ai_type=AI_TURRET, sprite_index=1, tile_x=36, tile_y=h - 4, patrol_range=1, speed=1, hp=3),
        ],
        doors=[
            DoorLink(tile_x=1, tile_y=h - 3, target_room=0, target_x=w - 5, target_y=h - 6, req_ability=ABIL_NONE),
            DoorLink(tile_x=w - 2, tile_y=h - 3, target_room=2, target_x=3, target_y=h - 6, req_ability=ABIL_NONE),
        ],
        dialogue_text="PRESS SELECT TO MORPH   ROLL UNDER LOW TUNNEL!",
        upgrade_ability=ABIL_MISSILES,
        parallax_enabled=True, parallax_tile_idx=8,
    )

    # --- Room 2: Omega Core Boss Chamber (32x32 Multi-HP Boss + Platforms!) ---
    bw, bh = 32, 20
    c2 = empty_grid(bw, bh, 0)
    for x in range(bw):
        c2[0][x] = 9; c2[bh - 2][x] = 2; c2[bh - 1][x] = 9
    for y in range(bh):
        c2[y][0] = 9; c2[y][bw - 1] = 9
    c2[bh - 4][1] = 11; c2[bh - 3][1] = 11
    for x in range(6, 11):
        c2[bh - 6][x] = 3
    for x in range(20, 25):
        c2[bh - 6][x] = 3
    rm2 = LevelMap(
        name="Sector 3 — Omega Core",
        width=bw, height=bh, spawn_x=4, spawn_y=bh - 6, cells=c2,
        entities=[
            EntityPlacement(kind="boss", ai_type=AI_BOSS, sprite_index=4, tile_x=20, tile_y=bh - 6, patrol_range=7, speed=1, hp=12),
        ],
        doors=[DoorLink(tile_x=1, tile_y=bh - 3, target_room=1, target_x=w - 5, target_y=bh - 6, req_ability=ABIL_NONE)],
        dialogue_text="WARNING: OMEGA X CORE!  USE MISSILES (R) TO WIN",
        upgrade_ability=ABIL_HIGH_JUMP,
        parallax_enabled=True, parallax_tile_idx=8,
    )

    rules = [
        ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="L", trigger=TRIGGER_HELD, action=ACTION_AIM_UP, param=0, anim_name="", sfx_index=-1),
        ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_JUMP, param=6, anim_name="jump", sfx_index=0),
        ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=5, anim_name="attack", sfx_index=2),
        ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_BOMB, param=4, anim_name="attack", sfx_index=4),
        ButtonRule(button="SELECT", trigger=TRIGGER_PRESSED, action=ACTION_MORPH_BALL, param=0, anim_name="", sfx_index=3),
        ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="", sfx_index=-1),
    ]

    proj = KinoPixelProject(
        title="BSL FUSION",
        game_code="KMET",
        maker_code="KP",
        target_system="GBA",
        physics_mode="platformer",
        gravity=40,
        max_fall_speed=768,
        bg_color_hex="#0A101E",
        alpha_blend_enabled=True,
        sram_save_enabled=True,
        starting_abilities=ABIL_WALL_JUMP,
        morph_sprite_index=3,
        palettes=pals,
        sprites=[hunter, slime, beam, morph, boss],
        tiles=tiles,
        rooms=[rm0, rm1, rm2],
        active_room_idx=0,
        button_rules=rules,
        sfx_list=sfx,
        direct_sound=DirectSoundConfig(enabled=True, preset="Boss Explosion", sample_rate=8192),
    )
    proj.sequence_genie.ensure_initialized()
    proj.sequence_genie.scale = "PHRYG"
    proj.sequence_genie.bpm = 124
    proj.sequence_genie.save_slot(0)
    proj.snapshot_push("Initial BSL Metroidvania Project")
    proj.dirty = False
    return proj


def create_starter_project(template: str = "GBA Platformer") -> KinoPixelProject:
    """Create a polished, ready-to-play starter project for GBA, GBC, GB, or BSL Metroidvania."""
    if "Metroidvania" in template or "BSL" in template or "Fusion" in template:
        return _create_bsl_metroidvania()

    is_topdown = "Top-Down" in template
    if "GB Classic" in template or "DMG" in template:
        target = "GB"
        pals = [list(PRESET_PALETTES["DMG Classic Olive"]), list(PRESET_PALETTES["Game Boy Pocket"]), list(PRESET_PALETTES["DMG Classic Olive"])]
        bg_hex, title = "#9BBC0F", "DMG QUEST"
    elif "GBC" in template:
        target = "GBC"
        pals = [list(PRESET_PALETTES["GBC Pastel Quest"]), list(PRESET_PALETTES["GBA Crimson Hero"]), list(PRESET_PALETTES["GBA Emerald Knight"])]
        bg_hex, title = "#181828", "COLOR QUEST"
    else:
        target = "GBA"
        pals = [list(PRESET_PALETTES["GBA Starbit Retro"]), list(PRESET_PALETTES["GBA Crimson Hero"]), list(PRESET_PALETTES["GBA Emerald Knight"])]
        bg_hex, title = "#101424", ("STARBIT RPG" if is_topdown else "STARBIT GBA")

    hero = SpriteAsset(
        name="Hero", role="player", width=16, height=16, palette_index=0, frames=_make_hero_frames(),
        animations=[
            AnimationClip("idle", [0, 1], fps=4, loop=True),
            AnimationClip("walk", [2, 3], fps=10, loop=True),
            AnimationClip("jump", [4], fps=8, loop=False),
            AnimationClip("attack", [5, 0], fps=12, loop=False),
        ],
    )
    slime = SpriteAsset(name="Crimson Slime", role="enemy", width=16, height=16, palette_index=0, frames=_make_slime_frames(), animations=[AnimationClip("walk", [0, 1], fps=6, loop=True)])
    fireball = SpriteAsset(name="Star Bolt", role="projectile", width=16, height=16, palette_index=0, frames=_make_projectile_frames(), animations=[AnimationClip("fly", [0, 1], fps=12, loop=True)])
    tiles = _make_default_tiles()
    sfx = _make_default_sfx()

    w, h = (48, 20) if target == "GBA" else (32, 18)
    cells = empty_grid(w, h, 0)

    if is_topdown:
        for x in range(w):
            cells[0][x] = 9; cells[h - 1][x] = 9
        for y in range(h):
            cells[y][0] = 9; cells[y][w - 1] = 9
        for y in range(2, h - 5):
            cells[y][10] = 2
        for y in range(5, h - 2):
            cells[y][20] = 2
        for x in range(12, 19):
            cells[8][x] = 2
        for cx, cy in [(5, 4), (6, 4), (14, 5), (16, 5), (15, 13), (25, 6), (27, 6)]:
            if cx < w - 2 and cy < h - 2:
                cells[cy][cx] = 4
        cells[h // 2][w - 4] = 7
        cells[12][14] = 5; cells[12][15] = 5
        level = LevelMap(
            name="Dungeon 1 — Violet Sanctum", width=w, height=h, spawn_x=3, spawn_y=h // 2, cells=cells,
            entities=[
                EntityPlacement(kind="enemy", ai_type=AI_PATROL, sprite_index=1, tile_x=13, tile_y=4, patrol_range=4, speed=1),
                EntityPlacement(kind="enemy", ai_type=AI_CHASER, sprite_index=1, tile_x=24, tile_y=12, patrol_range=5, speed=1),
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
        ground_y = h - 3
        for sx, sy in [(4, 3), (11, 2), (18, 4), (26, 2), (34, 3), (42, 4)]:
            if sx < w - 1:
                cells[sy][sx] = 8
        for x in range(w):
            if 15 <= x <= 17 and w >= 40:
                continue
            cells[ground_y][x] = 1
            for yy in range(ground_y + 1, h):
                cells[yy][x] = 2
        for y in range(h):
            cells[y][0] = 9; cells[y][w - 1] = 9
        for x in range(7, 12):
            cells[ground_y - 4][x] = 3
            cells[ground_y - 5][x] = 4 if x % 2 == 1 else 0
        cells[ground_y - 1][13] = 6
        for x in range(19, 25):
            if x < w - 2:
                cells[ground_y - 5][x] = 3
                cells[ground_y - 6][x] = 4 if x % 2 == 0 else 0
        if w >= 40:
            cells[ground_y - 1][26] = 5; cells[ground_y - 1][27] = 5
            for x in range(29, 35):
                cells[ground_y - 3][x] = 2
                cells[ground_y - 4][x] = 4 if x % 2 == 1 else 0
            for x in range(36, 41):
                cells[ground_y - 6][x] = 3
            cells[ground_y - 7][38] = 4
            cells[ground_y - 1][w - 4] = 7
            entities = [
                EntityPlacement(kind="enemy", ai_type=AI_PATROL, sprite_index=1, tile_x=11, tile_y=ground_y - 2, patrol_range=3, speed=1),
                EntityPlacement(kind="enemy", ai_type=AI_PATROL, sprite_index=1, tile_x=22, tile_y=ground_y - 2, patrol_range=3, speed=1),
                EntityPlacement(kind="enemy", ai_type=AI_PATROL, sprite_index=1, tile_x=38, tile_y=ground_y - 2, patrol_range=4, speed=1),
            ]
        else:
            cells[ground_y - 1][18] = 5; cells[ground_y - 1][w - 4] = 7
            entities = [
                EntityPlacement(kind="enemy", ai_type=AI_PATROL, sprite_index=1, tile_x=10, tile_y=ground_y - 2, patrol_range=3, speed=1),
                EntityPlacement(kind="enemy", ai_type=AI_PATROL, sprite_index=1, tile_x=23, tile_y=ground_y - 2, patrol_range=3, speed=1),
            ]
        level = LevelMap(name="Stage 1 — Starbit Meadow", width=w, height=h, spawn_x=3, spawn_y=ground_y - 2, cells=cells, entities=entities)
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
            rules = [r for r in rules if r.button not in ("L", "R")]

    proj = KinoPixelProject(
        title=title, game_code="KPIX", maker_code="KP", target_system=target,
        physics_mode="topdown" if is_topdown else "platformer",
        gravity=42, max_fall_speed=768, bg_color_hex=bg_hex,
        palettes=pals, sprites=[hero, slime, fireball], tiles=tiles,
        rooms=[level], active_room_idx=0, button_rules=rules, sfx_list=sfx,
    )
    proj.sequence_genie.ensure_initialized()
    proj.sequence_genie.scale = "DOR" if is_topdown else "PENTA MIN"
    proj.sequence_genie.bpm = 118 if is_topdown else 134
    proj.sequence_genie.save_slot(0)
    proj.snapshot_push("Initial Project")
    proj.dirty = False
    return proj
