"""Built-in handcrafted playable starter templates for KinoPixel v3.0 (Universal GB / GBC / GBA Studio).

Demonstrates the breadth of games you can build from the exact same flexible universal primitives:
- GBA Side-Scroller (Starbit)
- GBA Sci-Fi Exploration (BSL Sector — multi-room, 16x32 hero, alt-form, slopes, water, boss)
- GBA Action-RPG (Legacy Quest — top-down village + dungeon, friendly NPC, world switch, Ki/Super Burst)
- GBA Tactical Grid (Advance Ops — 16px tile-stepped strategy map, command burst, HQ capture)
- GBA Space Action (Omega Wing — 8-way free flight, sine squadrons, 3-way Super Burst, 32x32 boss)
- GBC Pastel Adventure & GB Classic (DMG)
- Blank Custom Canvas (GBA)
"""
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
    ACTION_HEAL,
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
    ACTION_SUPER_BURST,
    AI_BOSS,
    AI_CHASER,
    AI_NPC,
    AI_PATROL,
    AI_SINE,
    AI_TURRET,
    AnimationClip,
    ButtonRule,
    COND_ALWAYS,
    COND_VAR_POS,
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


def _make_starfighter_frames() -> List[List[List[int]]]:
    """16x16 Sleek Space Fighter / Flying Hero sprite for 8-way Space Action games."""
    leg = {".": 0, "#": 1, "W": 2, "S": 3, "B": 5, "C": 6, "Y": 9, "K": 10, "R": 11}
    f0 = _parse_art([
        "................",
        "....###.........",
        "....#BB#........",
        "....#BBB##......",
        "..###BBBBBB##...",
        ".#KK#WWBBBBBB##.",
        "#KKKWCCWWWWBBBB#",
        "#RRRWWWWWWWWWWB#",
        "#KKKWCCWWWWBBBB#",
        ".#KK#WWBBBBBB##.",
        "..###BBBBBB##...",
        "....#BBB##......",
        "....#BB#........",
        "....###.........",
        "................",
        "................",
    ], leg)
    f1 = _parse_art([
        "................",
        "....###.........",
        "....#BB#........",
        "....#BBB##......",
        "..###BBBBBB##...",
        ".#RR#WWBBBBBB##.",
        "#RRRWCCWWWWBBBB#",
        "#KKKWWWWWWWWWWB#",
        "#RRRWCCWWWWBBBB#",
        ".#RR#WWBBBBBB##.",
        "..###BBBBBB##...",
        "....#BBB##......",
        "....#BB#........",
        "....###.........",
        "................",
        "................",
    ], leg)
    return [f0, f1]


def _make_tank_unit_frames() -> List[List[List[int]]]:
    """16x16 Tactical Armored Unit sprite for Grid Strategy games."""
    leg = {".": 0, "#": 1, "W": 2, "S": 3, "G": 4, "B": 5, "C": 6, "M": 7, "E": 8, "Y": 9, "R": 11}
    f0 = _parse_art([
        "................",
        ".....######.....",
        "....#MMMMMM#....",
        "...#MMWWMMMM###.",
        "...#MMMMMMMMMMM#",
        "...#MMMEEEEE###.",
        "..############..",
        ".#MMMMMMMMMMMM#.",
        ".#MMYYYYMMMMMM#.",
        ".#MMMMMMMMMMMM#.",
        ".##############.",
        ".#G#G#G#G#G#G#G#",
        "..############..",
        "................",
        "................",
        "................",
    ], leg)
    f1 = _parse_art([
        "................",
        ".....######.....",
        "....#MMMMMM#....",
        "...#MMWWMMMM###.",
        "...#MMMMMMMMMMM#",
        "...#MMMEEEEE###.",
        "..############..",
        ".#MMMMMMMMMMMM#.",
        ".#MMWWWWMMMMMM#.",
        ".#MMMMMMMMMMMM#.",
        ".##############.",
        ".##G#G#G#G#G#G##",
        "..############..",
        "................",
        "................",
        "................",
    ], leg)
    return [f0, f1]


def _make_hunter_16x32_frames() -> List[List[List[int]]]:
    """16x32 Tall Armored Sci-Fi Hero metasprite."""
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


def _make_compact_form_frames() -> List[List[List[int]]]:
    """16x16 Secondary / Compact Form metasprite."""
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
    """32x32 Multi-Phase Boss Metasprite."""
    g = empty_grid(32, 32, 0)
    for y in range(32):
        for x in range(32):
            dx = x - 15.5
            dy = y - 15.5
            d2 = dx * dx + dy * dy
            if 110 <= d2 <= 195:
                g[y][x] = 1
            elif 42 <= d2 < 110:
                g[y][x] = 13 if ((x + y) % 3 == 0) else 5
            elif 16 <= d2 < 42:
                g[y][x] = 11
            elif d2 < 16:
                g[y][x] = 2 if (dx < 0 and dy < 0) else 7
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


def _make_npc_frames() -> List[List[List[int]]]:
    leg = {".": 0, "#": 1, "W": 2, "S": 3, "G": 4, "M": 7, "E": 8, "Y": 9, "K": 10, "C": 13}
    f0 = _parse_art([
        ".....######.....",
        "....#YYYYYY#....",
        "...#YKKKKKKY#...",
        "...#S######S#...",
        "...#S#W##W#S#...",
        "...#SS####SS#...",
        "....#SSSSSS#....",
        "...##MMMMMM##...",
        "..#MMMEEEEMMM#..",
        "..#MMMEWWEMMM#..",
        "...##MMMMMM##...",
        "....#MM..MM#....",
        "....#EE..EE#....",
        "....#EE..EE#....",
        "....###..###....",
        "................",
    ], leg)
    return [f0]


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
        TileAsset("Grass / Terrain", TILE_SOLID, 0, _parse_art([
            "MMMMMMMM", "MEEMMEEM", "EEDDDDEE", "DDDDDDDD",
            "DD#DDDD#", "DDDDDDDD", "D#DDDDDD", "DDDD#DDD",
        ], leg)),
        TileAsset("Steel / Brick", TILE_SOLID, 0, _parse_art([
            "########", "#GGG#GGG", "#G##G##G", "########",
            "GGG#GGG#", "##G##G##", "########", "#GGG#GGG",
        ], leg)),
        TileAsset("One-Way Platform", TILE_ONEWAY, 0, _parse_art([
            ".WWWWWW.", "WWCCCCWW", "WCCCCCCW", ".BBBBBB.",
            "........", "........", "........", "........",
        ], leg)),
        TileAsset("Collectible Star", TILE_COIN, 0, _parse_art([
            "...YY...", "..YKKY..", ".YKWKKY.", ".YKKKKY.",
            ".YKKKKY.", "..YKKY..", "...YY...", "........",
        ], leg)),
        TileAsset("Spikes / Hazard", TILE_HAZARD, 0, _parse_art([
            "........", "........", ".#....#.", ".R....R.",
            "#R#..#R#", "RPR..RPR", "RR#..#RR", "########",
        ], leg)),
        TileAsset("Spring / Boost", TILE_BOUNCE, 0, _parse_art([
            "........", "........", ".RRRRRR.", ".PPPPPP.",
            "..YYYY..", "..#YY#..", ".#YYYY#.", "########",
        ], leg)),
        TileAsset("Goal / Objective", TILE_GOAL, 0, _parse_art([
            "..LLLL..", ".LVWWVL.", "LVWMMWVL", "LVWMMWVL",
            "LVWMMWVL", "LVWMMWVL", ".LVWWVL.", "..LLLL..",
        ], leg)),
        TileAsset("Parallax Star", TILE_EMPTY, 0, _parse_art([
            "........", "........", "...L....", "..LWL...",
            "...L....", "........", "........", "........",
        ], leg)),
        TileAsset("Armor Wall", TILE_SOLID, 0, _parse_art([
            "########", "#LVVVVL#", "#L#VV#L#", "#LVVVVL#",
            "#LVVVVL#", "#L#VV#L#", "#LVVVVL#", "########",
        ], leg)),
        TileAsset("Cracked Block", TILE_BREAKABLE, 0, _parse_art([
            "########", "#YY##YY#", "#Y#YY#Y#", "##YYYY##",
            "#Y#YY#Y#", "#YY##YY#", "#Y####Y#", "########",
        ], leg)),
        TileAsset("Warp Door / Gate", TILE_DOOR, 0, _parse_art([
            "##CCCC##", "#CCWWCC#", "#CWWWWC#", "#CCWWCC#",
            "#CCWWCC#", "#CWWWWC#", "#CCWWCC#", "##CCCC##",
        ], leg)),
        TileAsset("SRAM Checkpoint", TILE_SAVE, 0, _parse_art([
            "........", "..MMMM..", ".MMWWMM.", ".MWMMWM.",
            "..MMMM..", "..#MM#..", ".#MMMM#.", "########",
        ], leg)),
        TileAsset("Skill / Key Orb", TILE_UPGRADE, 0, _parse_art([
            "..####..", ".#KKKK#.", "#KKWWKK#", "#KWWWWK#",
            "#KKWWKK#", ".#KKKK#.", "..####..", "........",
        ], leg)),
        TileAsset("Sign / Terminal", TILE_TERMINAL, 0, _parse_art([
            ".######.", "#CCCCCC#", "#CWWWWC#", "#CCCCCC#",
            ".######.", "...##...", "..####..", ".######.",
        ], leg)),
        # v3.0 Universal Terrain & Interactive Tiles (15..19)
        TileAsset("Slope Up (/)", TILE_SLOPE_L, 0, _parse_art([
            ".......#", "......#M", ".....#MM", "....#MMD",
            "...#MMDD", "..#MMDDD", ".#MMDDDD", "#MMDDDDD",
        ], leg)),
        TileAsset("Slope Down (\\)", TILE_SLOPE_R, 0, _parse_art([
            "#.......", "M#......", "MM#.....", "DMM#....",
            "DDMM#...", "DDDMM#..", "DDDDMM#.", "DDDDDMM#",
        ], leg)),
        TileAsset("Water Zone", TILE_WATER, 0, _parse_art([
            ".WW..WW.", "WCCWWCCW", "CCCCCCCC", "CBBCCBBC",
            "BBBBBBBB", "BBCCBBCC", "BBBBBBBB", "BBBBBBBB",
        ], leg)),
        TileAsset("Ladder / Vine", TILE_LADDER, 0, _parse_art([
            ".Y....Y.", ".YYYYYY.", ".Y....Y.", ".YYYYYY.",
            ".Y....Y.", ".YYYYYY.", ".Y....Y.", ".YYYYYY.",
        ], leg)),
        TileAsset("World Switch", TILE_SWITCH, 0, _parse_art([
            "........", "..PPPP..", ".PPWWPP.", "..PPPP..",
            "...##...", "..####..", ".######.", "########",
        ], leg)),
    ]


def _make_default_sfx() -> List[SfxPatch]:
    return [
        SfxPatch("Jump", channel=1, freq_hz=320, duty=2, volume=13, env_step=2, sweep_time=1, sweep_dir=0, sweep_shift=3, duration_ms=160),
        SfxPatch("Pickup / Save", channel=1, freq_hz=920, duty=1, volume=13, env_step=2, sweep_time=1, sweep_dir=0, sweep_shift=2, duration_ms=150),
        SfxPatch("Blaster / Shot", channel=1, freq_hz=680, duty=0, volume=12, env_step=2, sweep_time=1, sweep_dir=1, sweep_shift=2, duration_ms=130),
        SfxPatch("Dash / Shift", channel=4, volume=12, env_step=2, noise_div=2, noise_shift=3, noise_short=False, duration_ms=130),
        SfxPatch("Hurt / Blast", channel=4, volume=14, env_step=3, noise_div=4, noise_shift=5, noise_short=True, duration_ms=220),
        SfxPatch("Unlock / Clear", channel=1, freq_hz=523, duty=2, volume=14, env_step=3, sweep_time=2, sweep_dir=0, sweep_shift=2, duration_ms=340),
    ]


def _create_bsl_exploration() -> KinoPixelProject:
    """Showcase 1: 3-Room Sci-Fi Action-Exploration GBA Demo (16x32 Hero, Alt-Form, Slopes, Water, Ladder, Multi-Phase Boss)."""
    pals = [
        list(PRESET_PALETTES["BSL Fusion Station"]),
        list(PRESET_PALETTES["GBA Crimson Hero"]),
        list(PRESET_PALETTES["GBA Emerald Knight"]),
    ]
    hunter = SpriteAsset(
        name="Armored Hero (16×32)",
        role="player", width=16, height=32, palette_index=0,
        frames=_make_hunter_16x32_frames(),
        animations=[
            AnimationClip("idle", [0], fps=4, loop=True),
            AnimationClip("walk", [1, 2], fps=10, loop=True),
            AnimationClip("jump", [3], fps=8, loop=False),
            AnimationClip("attack", [4, 0], fps=12, loop=False),
        ],
    )
    slime = SpriteAsset(name="Bio-Stalker", role="enemy", width=16, height=16, palette_index=0, frames=_make_slime_frames(), animations=[AnimationClip("walk", [0, 1], fps=6, loop=True)])
    beam = SpriteAsset(name="Plasma Shot", role="projectile", width=16, height=16, palette_index=0, frames=_make_projectile_frames(), animations=[AnimationClip("fly", [0, 1], fps=12, loop=True)])
    alt_form = SpriteAsset(name="Compact Form (16×16)", role="morph", width=16, height=16, palette_index=0, frames=_make_compact_form_frames(), animations=[AnimationClip("roll", [0, 1], fps=10, loop=True)])
    boss = SpriteAsset(name="Omega Core Boss (32×32)", role="boss", width=32, height=32, palette_index=0, frames=_make_boss_32x32_frames(), animations=[AnimationClip("idle", [0], fps=6, loop=True)])

    tiles = _make_default_tiles()
    sfx = _make_default_sfx()

    # Room 0: Main Deck (Terminal 2-page, Save Station, Slope ramp, Ladder, Skill Orb, East Door)
    w, h = 44, 20
    c0 = empty_grid(w, h, 0)
    for x in range(w):
        c0[0][x] = 9; c0[h - 2][x] = 2; c0[h - 1][x] = 9
    for y in range(h):
        c0[y][0] = 9; c0[y][w - 1] = 9
    c0[h - 3][6] = 14   # Dialogue Terminal
    c0[h - 3][11] = 12  # SRAM Checkpoint
    # 45-degree Slope ramp & Ladder up to Skill Orb platform
    c0[h - 3][14] = 15  # Slope Up (/)
    for y in range(h - 6, h - 2):
        c0[y][16] = 18  # Climbable Ladder!
    for x in range(16, 23):
        c0[h - 6][x] = 3
    c0[h - 7][19] = 13  # Skill 1 Unlock Orb (Alt Form!)
    # Small water basin to test low-G swim
    c0[h - 3][26] = 17; c0[h - 3][27] = 17
    for y in range(h - 6, h - 2):
        c0[y][30] = 10  # Destructible Wall
    c0[h - 4][w - 2] = 11; c0[h - 3][w - 2] = 11
    rm0 = LevelMap(
        name="Sector 1 — Main Deck", width=w, height=h, world_x=1, world_y=3,
        spawn_x=3, spawn_y=h - 6, cells=c0,
        entities=[EntityPlacement(kind="enemy", ai_type=AI_PATROL, sprite_index=1, tile_x=24, tile_y=h - 4, patrol_range=3, speed=1, hp=2)],
        doors=[DoorLink(tile_x=w - 2, tile_y=h - 3, target_room=1, target_x=3, target_y=h - 6, req_ability=ABIL_MORPH_BALL)],
        dialogue_text="HQ: CORE ACTIVE IN SEC 3. UNLOCK ALT FORM FIRST!",
        dialogue_page2="PRESS START FOR MINIMAP. R FIRES HEAVY SHOTS!",
        upgrade_ability=ABIL_MORPH_BALL, parallax_enabled=True, parallax_tile_idx=8,
    )

    # Room 1: Low Tunnel & Lab
    c1 = empty_grid(w, h, 0)
    for x in range(w):
        c1[0][x] = 9; c1[h - 2][x] = 2; c1[h - 1][x] = 9
    for y in range(h):
        c1[y][0] = 9; c1[y][w - 1] = 9
    c1[h - 4][1] = 11; c1[h - 3][1] = 11
    for y in range(1, h - 4):
        for x in range(13, 20):
            c1[y][x] = 9
    c1[h - 3][16] = 10
    for x in range(25, 31):
        c1[h - 6][x] = 3
    c1[h - 7][28] = 13
    c1[h - 3][33] = 5; c1[h - 3][34] = 5
    c1[h - 4][w - 2] = 11; c1[h - 3][w - 2] = 11
    rm1 = LevelMap(
        name="Sector 2 — Tunnel Lab", width=w, height=h, world_x=2, world_y=3,
        spawn_x=3, spawn_y=h - 6, cells=c1,
        entities=[
            EntityPlacement(kind="enemy", ai_type=AI_CHASER, sprite_index=1, tile_x=24, tile_y=h - 4, patrol_range=6, speed=1, hp=3),
            EntityPlacement(kind="enemy", ai_type=AI_TURRET, sprite_index=1, tile_x=36, tile_y=h - 4, patrol_range=1, speed=1, hp=3),
        ],
        doors=[
            DoorLink(tile_x=1, tile_y=h - 3, target_room=0, target_x=w - 5, target_y=h - 6, req_ability=ABIL_NONE),
            DoorLink(tile_x=w - 2, tile_y=h - 3, target_room=2, target_x=3, target_y=h - 6, req_ability=ABIL_NONE),
        ],
        dialogue_text="PRESS SELECT TO SHRINK  PASS UNDER LOW TUNNEL!",
        dialogue_page2="WATCH OUT FOR STALKERS  AND PLASMA TURRETS!",
        upgrade_ability=ABIL_MISSILES, parallax_enabled=True, parallax_tile_idx=8,
    )

    # Room 2: Multi-Phase 32x32 Boss Chamber
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
        name="Sector 3 — Core Chamber", width=bw, height=bh, world_x=3, world_y=3,
        spawn_x=4, spawn_y=bh - 6, cells=c2,
        entities=[
            EntityPlacement(kind="boss", ai_type=AI_BOSS, sprite_index=4, tile_x=20, tile_y=bh - 6, patrol_range=7, speed=1, hp=12, phase2_hp=6, defeat_flag=1),
        ],
        doors=[DoorLink(tile_x=1, tile_y=bh - 3, target_room=1, target_x=w - 5, target_y=bh - 6, req_ability=ABIL_NONE)],
        dialogue_text="WARNING: OMEGA CORE!    USE HEAVY SHOTS (R)!",
        dialogue_page2="UNDER 50 PCT HP IT USES 3-WAY SPREAD ATTACK!",
        upgrade_ability=ABIL_HIGH_JUMP, parallax_enabled=True, parallax_tile_idx=8,
    )

    rules = [
        ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="UP", trigger=TRIGGER_HELD, action=ACTION_MOVE_UP, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="DOWN", trigger=TRIGGER_HELD, action=ACTION_MOVE_DOWN, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="L", trigger=TRIGGER_HELD, action=ACTION_AIM_UP, param=0, anim_name="", sfx_index=-1),
        ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_JUMP, param=6, anim_name="jump", sfx_index=0),
        ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=5, anim_name="attack", sfx_index=2),
        # R fires Heavy Shot using VAR[0] ammo (starts at 10, decrements by 1!)
        ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_BOMB, param=4, anim_name="attack", sfx_index=4, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-1),
        ButtonRule(button="SELECT", trigger=TRIGGER_PRESSED, action=ACTION_MORPH_BALL, param=0, anim_name="", sfx_index=3),
        ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="", sfx_index=-1),
    ]

    proj = KinoPixelProject(
        title="BSL FUSION", game_code="KMET", maker_code="KP", target_system="GBA",
        physics_mode="platformer", gravity=40, max_fall_speed=768, bg_color_hex="#0A101E",
        alpha_blend_enabled=True, sram_save_enabled=True, starting_abilities=ABIL_WALL_JUMP,
        starting_vars=[10, 0, 0, 0, 0, 0, 0, 0], morph_sprite_index=3,
        palettes=pals, sprites=[hunter, slime, beam, alt_form, boss], tiles=tiles,
        rooms=[rm0, rm1, rm2], active_room_idx=0, button_rules=rules, sfx_list=sfx,
        direct_sound=DirectSoundConfig(enabled=True, preset="Boss Explosion", sample_rate=8192),
    )
    proj.sequence_genie.ensure_initialized()
    proj.sequence_genie.scale = "PHRYG"
    proj.sequence_genie.bpm = 124
    proj.sequence_genie.save_slot(0)
    proj.snapshot_push("Initial Sci-Fi Exploration Project")
    proj.dirty = False
    return proj


def _create_action_rpg() -> KinoPixelProject:
    """Showcase 2: Top-Down Action-RPG (Legacy of Goku / Zelda style — Village + Dungeon, Friendly NPC, Ki Burst, Switch, SRAM)."""
    pals = [
        list(PRESET_PALETTES["GBA Emerald Knight"]),
        list(PRESET_PALETTES["GBA Starbit Retro"]),
        list(PRESET_PALETTES["GBA Crimson Hero"]),
    ]
    hero = SpriteAsset(
        name="Adventurer", role="player", width=16, height=16, palette_index=0, frames=_make_hero_frames(),
        animations=[
            AnimationClip("idle", [0, 1], fps=4, loop=True),
            AnimationClip("walk", [2, 3], fps=10, loop=True),
            AnimationClip("jump", [4], fps=8, loop=False),
            AnimationClip("attack", [5, 0], fps=12, loop=False),
        ],
    )
    slime = SpriteAsset(name="Shadow Beast", role="enemy", width=16, height=16, palette_index=0, frames=_make_slime_frames(), animations=[AnimationClip("walk", [0, 1], fps=6, loop=True)])
    ki_bolt = SpriteAsset(name="Energy Wave", role="projectile", width=16, height=16, palette_index=0, frames=_make_projectile_frames(), animations=[AnimationClip("fly", [0, 1], fps=12, loop=True)])
    elder = SpriteAsset(name="Village Elder (NPC)", role="prop", width=16, height=16, palette_index=0, frames=_make_npc_frames(), animations=[AnimationClip("idle", [0], fps=4, loop=True)])
    tiles = _make_default_tiles()
    sfx = _make_default_sfx()

    # Room 0: Overworld Village (Friendly NPC, World Switch, SRAM Save, Temple Door)
    w, h = 36, 22
    c0 = empty_grid(w, h, 0)
    for x in range(w):
        c0[0][x] = 9; c0[h - 1][x] = 9
    for y in range(h):
        c0[y][0] = 9; c0[y][w - 1] = 9
    for x in range(10, 16):
        c0[6][x] = 2
    c0[14][8] = 12   # SRAM Save Shrine
    c0[10][18] = 19  # World Switch!
    c0[5][22] = 4; c0[5][24] = 4; c0[15][22] = 4
    c0[10][w - 2] = 11  # Temple Entrance Warp
    rm0 = LevelMap(
        name="Overworld — Emerald Village", width=w, height=h, world_x=2, world_y=3,
        spawn_x=4, spawn_y=10, cells=c0,
        entities=[
            EntityPlacement(kind="npc", ai_type=AI_NPC, sprite_index=3, tile_x=10, tile_y=10, patrol_range=0, speed=1, hp=9),
            EntityPlacement(kind="enemy", ai_type=AI_PATROL, sprite_index=1, tile_x=24, tile_y=12, patrol_range=4, speed=1, hp=2),
        ],
        doors=[DoorLink(tile_x=w - 2, tile_y=10, target_room=1, target_x=3, target_y=10, req_ability=ABIL_NONE)],
        dialogue_text="ELDER: DARKNESS STIRS   IN THE EASTERN TEMPLE!",
        dialogue_page2="USE R FOR SUPER BURST   AND L TO HEAL WITH KI!",
        switch_flag=1, parallax_enabled=False,
    )

    # Room 1: Temple Sanctum (Chasers + Turret + Goal Relic!)
    c1 = empty_grid(32, 20, 0)
    for x in range(32):
        c1[0][x] = 9; c1[19][x] = 9
    for y in range(20):
        c1[y][0] = 9; c1[y][31] = 9
    c1[10][1] = 11
    for y in range(5, 15):
        c1[y][14] = 10  # Destructible temple barrier
    c1[10][27] = 7      # Goal Relic!
    rm1 = LevelMap(
        name="Dungeon — Ancient Temple", width=32, height=20, world_x=3, world_y=3,
        spawn_x=3, spawn_y=10, cells=c1,
        entities=[
            EntityPlacement(kind="enemy", ai_type=AI_CHASER, sprite_index=1, tile_x=18, tile_y=8, patrol_range=4, speed=1, hp=3),
            EntityPlacement(kind="enemy", ai_type=AI_TURRET, sprite_index=1, tile_x=22, tile_y=13, patrol_range=1, speed=1, hp=3),
        ],
        doors=[DoorLink(tile_x=1, tile_y=10, target_room=0, target_x=w - 4, target_y=10, req_ability=ABIL_NONE)],
        dialogue_text="ANCIENT TEMPLE SANCTUM  CLAIM THE STAR RELIC!",
        dialogue_page2="", parallax_enabled=True, parallax_tile_idx=8,
    )

    rules = [
        ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="UP", trigger=TRIGGER_HELD, action=ACTION_MOVE_UP, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="DOWN", trigger=TRIGGER_HELD, action=ACTION_MOVE_DOWN, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_MELEE, param=3, anim_name="attack", sfx_index=3),
        ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=4, anim_name="attack", sfx_index=2),
        ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_SUPER_BURST, param=5, anim_name="attack", sfx_index=4, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-2),
        ButtonRule(button="L", trigger=TRIGGER_PRESSED, action=ACTION_HEAL, param=1, anim_name="", sfx_index=1, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-1),
        ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="", sfx_index=-1),
    ]

    proj = KinoPixelProject(
        title="LEGACY RPG", game_code="KRPG", maker_code="KP", target_system="GBA",
        physics_mode="topdown", gravity=0, max_fall_speed=512, bg_color_hex="#102420",
        alpha_blend_enabled=True, sram_save_enabled=True, starting_abilities=ABIL_NONE,
        starting_vars=[12, 0, 0, 0, 0, 0, 0, 0],
        palettes=pals, sprites=[hero, slime, ki_bolt, elder], tiles=tiles,
        rooms=[rm0, rm1], active_room_idx=0, button_rules=rules, sfx_list=sfx,
        direct_sound=DirectSoundConfig(enabled=True, preset="Laser Charge", sample_rate=8192),
    )
    proj.sequence_genie.ensure_initialized()
    proj.sequence_genie.scale = "DOR"
    proj.sequence_genie.bpm = 114
    proj.sequence_genie.save_slot(0)
    proj.snapshot_push("Initial Action-RPG Project")
    proj.dirty = False
    return proj


def _create_space_action() -> KinoPixelProject:
    """Showcase 3: 8-Way Space Action / Flight Shooter (Astro Boy / Gradius style — Sine Squadrons, 3-Way Super Burst, 32x32 Boss)."""
    pals = [
        list(PRESET_PALETTES["GBA Starbit Retro"]),
        list(PRESET_PALETTES["BSL Fusion Station"]),
        list(PRESET_PALETTES["GBA Crimson Hero"]),
    ]
    ship = SpriteAsset(name="Omega Wing", role="player", width=16, height=16, palette_index=0, frames=_make_starfighter_frames(), animations=[AnimationClip("idle", [0, 1], fps=10, loop=True), AnimationClip("walk", [0, 1], fps=14, loop=True), AnimationClip("attack", [1, 0], fps=16, loop=False)])
    drone = SpriteAsset(name="Interceptor", role="enemy", width=16, height=16, palette_index=0, frames=_make_slime_frames(), animations=[AnimationClip("walk", [0, 1], fps=8, loop=True)])
    laser = SpriteAsset(name="Hyper Laser", role="projectile", width=16, height=16, palette_index=0, frames=_make_projectile_frames(), animations=[AnimationClip("fly", [0, 1], fps=14, loop=True)])
    boss = SpriteAsset(name="Dreadnought Core (32×32)", role="boss", width=32, height=32, palette_index=0, frames=_make_boss_32x32_frames(), animations=[AnimationClip("idle", [0], fps=6, loop=True)])
    tiles = _make_default_tiles()
    sfx = _make_default_sfx()

    w, h = 48, 20
    c0 = empty_grid(w, h, 0)
    for x in range(w):
        c0[0][x] = 9; c0[h - 1][x] = 9
    for y in range(h):
        c0[y][0] = 9; c0[y][w - 1] = 9
    for x in (14, 24, 32):
        c0[5][x] = 10; c0[14][x] = 10
    rm0 = LevelMap(
        name="Orbit 1 — Asteroid Belt", width=w, height=h, world_x=1, world_y=2,
        spawn_x=3, spawn_y=9, cells=c0,
        entities=[
            EntityPlacement(kind="enemy", ai_type=AI_SINE, sprite_index=1, tile_x=16, tile_y=8, patrol_range=4, speed=1, hp=2),
            EntityPlacement(kind="enemy", ai_type=AI_SINE, sprite_index=1, tile_x=24, tile_y=11, patrol_range=5, speed=1, hp=2),
            EntityPlacement(kind="enemy", ai_type=AI_TURRET, sprite_index=1, tile_x=31, tile_y=6, patrol_range=1, speed=1, hp=3),
            EntityPlacement(kind="boss", ai_type=AI_BOSS, sprite_index=3, tile_x=39, tile_y=8, patrol_range=4, speed=1, hp=12, phase2_hp=6, defeat_flag=1),
        ],
        dialogue_text="LAUNCHED! PRESS B FIRE  AND R FOR 3-WAY BURST!",
        dialogue_page2="", parallax_enabled=True, parallax_tile_idx=8,
    )

    rules = [
        ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=3, anim_name="walk", sfx_index=-1),
        ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=3, anim_name="walk", sfx_index=-1),
        ButtonRule(button="UP", trigger=TRIGGER_HELD, action=ACTION_MOVE_UP, param=3, anim_name="walk", sfx_index=-1),
        ButtonRule(button="DOWN", trigger=TRIGGER_HELD, action=ACTION_MOVE_DOWN, param=3, anim_name="walk", sfx_index=-1),
        ButtonRule(button="B", trigger=TRIGGER_HELD, action=ACTION_SHOOT, param=6, anim_name="attack", sfx_index=2),
        ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_DASH, param=6, anim_name="walk", sfx_index=3),
        ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_SUPER_BURST, param=5, anim_name="attack", sfx_index=4, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-1),
        ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="", sfx_index=-1),
    ]

    proj = KinoPixelProject(
        title="OMEGA WING", game_code="KSHM", maker_code="KP", target_system="GBA",
        physics_mode="shmup", gravity=0, max_fall_speed=512, bg_color_hex="#0B0F1E",
        alpha_blend_enabled=True, sram_save_enabled=True, starting_abilities=ABIL_NONE,
        starting_vars=[8, 0, 0, 0, 0, 0, 0, 0],
        palettes=pals, sprites=[ship, drone, laser, boss], tiles=tiles,
        rooms=[rm0], active_room_idx=0, button_rules=rules, sfx_list=sfx,
        direct_sound=DirectSoundConfig(enabled=True, preset="Boss Explosion", sample_rate=8192),
    )
    proj.sequence_genie.ensure_initialized()
    proj.sequence_genie.scale = "HIRO"
    proj.sequence_genie.bpm = 138
    proj.sequence_genie.save_slot(0)
    proj.snapshot_push("Initial Space Action Project")
    proj.dirty = False
    return proj


def _create_tactical_grid() -> KinoPixelProject:
    """Showcase 4: Tactical Grid Strategy (Advance Wars style — 16px Tile-Stepped Unit, Funds/AP Var, Command Burst, HQ Capture)."""
    pals = [
        list(PRESET_PALETTES["GBA Crimson Hero"]),
        list(PRESET_PALETTES["GBA Emerald Knight"]),
        list(PRESET_PALETTES["GBA Starbit Retro"]),
    ]
    unit = SpriteAsset(name="Vanguard Tank", role="player", width=16, height=16, palette_index=0, frames=_make_tank_unit_frames(), animations=[AnimationClip("idle", [0, 1], fps=4, loop=True), AnimationClip("walk", [0, 1], fps=8, loop=True), AnimationClip("attack", [1, 0], fps=12, loop=False)])
    enemy = SpriteAsset(name="Enemy Recon", role="enemy", width=16, height=16, palette_index=0, frames=_make_slime_frames(), animations=[AnimationClip("walk", [0, 1], fps=6, loop=True)])
    shell = SpriteAsset(name="Artillery Shell", role="projectile", width=16, height=16, palette_index=0, frames=_make_projectile_frames(), animations=[AnimationClip("fly", [0, 1], fps=12, loop=True)])
    tiles = _make_default_tiles()
    sfx = _make_default_sfx()

    w, h = 32, 20
    c0 = empty_grid(w, h, 0)
    for x in range(w):
        c0[0][x] = 9; c0[h - 1][x] = 9
    for y in range(h):
        c0[y][0] = 9; c0[y][w - 1] = 9
    # River & Bridge terrain layout
    for y in range(2, h - 2):
        if y not in (9, 10):
            c0[y][14] = 17; c0[y][15] = 17
    c0[4][8] = 12   # Supply Base (SRAM Save + Repair!)
    c0[14][10] = 19 # Strategic Switch
    c0[10][27] = 7  # Enemy HQ Capture Objective!
    rm0 = LevelMap(
        name="Sector Alpha — River Front", width=w, height=h, world_x=1, world_y=1,
        spawn_x=4, spawn_y=10, cells=c0,
        entities=[
            EntityPlacement(kind="enemy", ai_type=AI_TURRET, sprite_index=1, tile_x=18, tile_y=6, patrol_range=1, speed=1, hp=3),
            EntityPlacement(kind="enemy", ai_type=AI_PATROL, sprite_index=1, tile_x=22, tile_y=12, patrol_range=3, speed=1, hp=3),
        ],
        dialogue_text="CMD: MOVE ON GRID WITH  D-PAD. CAPTURE EAST HQ!",
        dialogue_page2="PRESS R FOR CO BURST    OR L FOR FIELD REPAIR!",
        parallax_enabled=False,
    )

    rules = [
        ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="UP", trigger=TRIGGER_HELD, action=ACTION_MOVE_UP, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="DOWN", trigger=TRIGGER_HELD, action=ACTION_MOVE_DOWN, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=5, anim_name="attack", sfx_index=2),
        ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_BOMB, param=4, anim_name="attack", sfx_index=4, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-1),
        ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_SUPER_BURST, param=5, anim_name="attack", sfx_index=4, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-2),
        ButtonRule(button="L", trigger=TRIGGER_PRESSED, action=ACTION_HEAL, param=1, anim_name="", sfx_index=1, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-1),
        ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="", sfx_index=-1),
    ]

    proj = KinoPixelProject(
        title="ADVANCE OPS", game_code="KTAC", maker_code="KP", target_system="GBA",
        physics_mode="tactical", gravity=0, max_fall_speed=512, bg_color_hex="#18221A",
        alpha_blend_enabled=False, sram_save_enabled=True, starting_abilities=ABIL_NONE,
        starting_vars=[15, 0, 0, 0, 0, 0, 0, 0],
        palettes=pals, sprites=[unit, enemy, shell], tiles=tiles,
        rooms=[rm0], active_room_idx=0, button_rules=rules, sfx_list=sfx,
        direct_sound=DirectSoundConfig(enabled=True, preset="Item Fanfare", sample_rate=8192),
    )
    proj.sequence_genie.ensure_initialized()
    proj.sequence_genie.scale = "MAJ"
    proj.sequence_genie.bpm = 122
    proj.sequence_genie.save_slot(0)
    proj.snapshot_push("Initial Tactical Grid Project")
    proj.dirty = False
    return proj


def create_starter_project(template: str = "GBA Platformer") -> KinoPixelProject:
    """Create a polished, ready-to-play starter project across any supported genre or handheld target."""
    if any(k in template for k in ("Exploration", "BSL", "Fusion", "Metroidvania")):
        return _create_bsl_exploration()
    if any(k in template for k in ("Action-RPG", "Legacy", "Top-Down")):
        return _create_action_rpg()
    if any(k in template for k in ("Space", "Omega", "Shmup")):
        return _create_space_action()
    if any(k in template for k in ("Tactical", "Advance", "Grid")):
        return _create_tactical_grid()

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
        bg_hex, title = "#101424", "STARBIT GBA"

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
    level = LevelMap(name="Stage 1 — Starbit Meadow", width=w, height=h, world_x=1, world_y=2, spawn_x=3, spawn_y=ground_y - 2, cells=cells, entities=entities)
    rules = [
        ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
        ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_JUMP, param=5, anim_name="jump", sfx_index=0),
        ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=4, anim_name="attack", sfx_index=2),
        ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_DASH, param=5, anim_name="jump", sfx_index=3),
        ButtonRule(button="L", trigger=TRIGGER_PRESSED, action=ACTION_MELEE, param=3, anim_name="attack", sfx_index=3),
        ButtonRule(button="SELECT", trigger=TRIGGER_PRESSED, action=ACTION_PALETTE_NEXT, param=1, anim_name="", sfx_index=1),
        ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="idle", sfx_index=-1),
    ]
    if target in ("GB", "GBC"):
        rules = [r for r in rules if r.button not in ("L", "R")]

    proj = KinoPixelProject(
        title=title, game_code="KPIX", maker_code="KP", target_system=target,
        physics_mode="platformer", gravity=42, max_fall_speed=768, bg_color_hex=bg_hex,
        palettes=pals, sprites=[hero, slime, fireball], tiles=tiles,
        rooms=[level], active_room_idx=0, button_rules=rules, sfx_list=sfx,
    )
    proj.sequence_genie.ensure_initialized()
    proj.sequence_genie.scale = "PENTA MIN"
    proj.sequence_genie.bpm = 128
    proj.sequence_genie.save_slot(0)
    proj.snapshot_push("Initial Project")
    proj.dirty = False
    return proj
