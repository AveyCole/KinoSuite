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


def _make_cursor_frames() -> List[List[List[int]]]:
    """16x16 Animated Tactical Selection Cursor."""
    leg = {".": 0, "W": 2, "Y": 9, "K": 10}
    f0 = _parse_art([
        "KKKKK......KKKKK",
        "KWWWW......WWWWK",
        "KW............WK",
        "KW............WK",
        "K..............K",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "K..............K",
        "KW............WK",
        "KW............WK",
        "KWWWW......WWWWK",
        "KKKKK......KKKKK",
    ], leg)
    f1 = _parse_art([
        "................",
        ".YYYY......YYYY.",
        ".YWW........WWY.",
        ".YW..........WY.",
        ".Y............Y.",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        ".Y............Y.",
        ".YW..........WY.",
        ".YWW........WWY.",
        ".YYYY......YYYY.",
        "................",
    ], leg)
    return [f0, f1]


def _make_infantry_frames() -> List[List[List[int]]]:
    """16x16 Tactical Infantry Squad sprite."""
    leg = {".": 0, "#": 1, "W": 2, "S": 3, "B": 5, "C": 6, "Y": 9}
    f0 = _parse_art([
        "................",
        "..####....####..",
        ".#BBBB#..#BBBB#.",
        ".#BCCC#..#BCCC#.",
        "..#SS#....#SS#..",
        "..####....####..",
        ".#BBBB#..#BBBB#.",
        "#BBWWBB##BBWWBB#",
        ".#BBBB#..#BBBB#.",
        "..#BB#....#BB#..",
        "..#BB#....#BB#..",
        ".#B..B#..#B..B#.",
        ".##..##..##..##.",
        "................",
        "................",
        "................",
    ], leg)
    f1 = _parse_art([
        "................",
        "................",
        "..####....####..",
        ".#BBBB#..#BBBB#.",
        ".#BCCC#..#BCCC#.",
        "..#SS#....#SS#..",
        "..####....####..",
        ".#BBBB#..#BBBB#.",
        "#BBWWBB##BBWWBB#",
        ".#BBBB#..#BBBB#.",
        "..#BB#....#BB#..",
        ".##..##..##..##.",
        "................",
        "................",
        "................",
        "................",
    ], leg)
    return [f0, f1]


def _make_mech_frames() -> List[List[List[int]]]:
    """16x16 Heavy Anti-Armor Mech Infantry sprite."""
    leg = {".": 0, "#": 1, "W": 2, "S": 3, "G": 4, "B": 5, "C": 6, "Y": 9, "R": 11}
    f0 = _parse_art([
        "................",
        "....######......",
        "...#BBBBBB#.....",
        "...#BCWWCB#.....",
        "####BSSSSB######",
        "#RRGGGGGGGGGGGW#",
        "####BBBBBB######",
        "...#BBBBBB#.....",
        "..#BBCCCCBB#....",
        "..#BBBBBBBB#....",
        "..#BB#..#BB#....",
        "..#CC#..#CC#....",
        ".#BBB#..#BBB#...",
        ".#####..#####...",
        "................",
        "................",
    ], leg)
    return [f0, f0]


def _make_artillery_frames() -> List[List[List[int]]]:
    """16x16 Ranged Mobile Artillery sprite."""
    leg = {".": 0, "#": 1, "W": 2, "G": 4, "B": 5, "C": 6, "Y": 9}
    f0 = _parse_art([
        "................",
        "..........####..",
        "........##CCWW#.",
        "......##CCCC##..",
        ".....#BBBB##....",
        "...##BBBB#......",
        "..#BBBBBB##.....",
        ".#BBCCCCBBB#....",
        ".#BBBBBBBBBB#...",
        ".#BBYYYYBBBB#...",
        ".############...",
        ".#G#G#G#G#G#G...",
        "..##########....",
        "................",
        "................",
        "................",
    ], leg)
    return [f0, f0]


def _make_tank_unit_frames() -> List[List[List[int]]]:
    """16x16 Tactical Armored Tank sprite."""
    leg = {".": 0, "#": 1, "W": 2, "S": 3, "G": 4, "B": 5, "C": 6, "M": 7, "E": 8, "Y": 9, "R": 11}
    f0 = _parse_art([
        "................",
        ".....######.....",
        "....#BBBBBB#....",
        "...#BBWWBBBB###.",
        "...#BBBBBBBBBBB#",
        "...#BBBCCCCC###.",
        "..############..",
        ".#BBBBBBBBBBBB#.",
        ".#BBYYYYBBBBBB#.",
        ".#BBBBBBBBBBBB#.",
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
        "....#BBBBBB#....",
        "...#BBWWBBBB###.",
        "...#BBBBBBBBBBB#",
        "...#BBBCCCCC###.",
        "..############..",
        ".#BBBBBBBBBBBB#.",
        ".#BBWWWWBBBBBB#.",
        ".#BBBBBBBBBBBB#.",
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


def _make_co_portrait_32x32() -> List[List[List[int]]]:
    """32x32 Shaded Tactical Commander Portrait for Title Screen, Briefings & War Room."""
    leg = {".": 0, "#": 1, "W": 2, "S": 3, "G": 4, "B": 5, "C": 6, "M": 7, "E": 8, "Y": 9, "K": 10, "R": 11, "P": 12, "D": 15}
    art = [
        "........################........",
        "......##BBBBBBBBBBBBBBBB##......",
        ".....#BBCCCCCCCCCCCCCCCCBB#.....",
        "....#BBCCBBBBBBBBBBBBBBCCBB#....",
        "....#BBBBBBB##YYYY##BBBBBBB#....",
        "...#BBBBBBB#YYKKKKYY#BBBBBBB#...",
        "...#BBBBBBB##YYYYYY##BBBBBBB#...",
        "...#BBBBBBBBBBBBBBBBBBBBBBBB#...",
        "..###########################...",
        "..#GGGGGGGGGGGGGGGGGGGGGGGGGG#..",
        "...####DDDDDDDDDDDDDDDDDD####...",
        ".....##DDSSSSSSSSSSSSSSDD##.....",
        ".....#DDSSWWWWWWWWWWWWSSDD#.....",
        ".....#D#SSW##########WSS#D#.....",
        ".....#D#SS#CCWW##CCWW#SS#D#.....",
        ".....#D#SS#CCBB##CCBB#SS#D#.....",
        ".....#D#SS############SS#D#.....",
        "......#DSSSWWWWWWWWWWWSSD#......",
        "......#DDSSWWWWWWWWWWSSDD#......",
        ".......#DDSSWW####WWSSDD#.......",
        "........#DDSSWWWWWWSSDD#........",
        ".........##DDSSSSSSDD##.........",
        ".......####DDDDDDDDDD####.......",
        ".....##BBBB##SSSSSS##BBBB##.....",
        "....#BBCCCCBB######BBCCCCBB#....",
        "...#BBCCBBBBBB#WW#BBBBBBCCBB#...",
        "...#BBBBYYYYBB#WW#BBYYYYBBBB#...",
        "..#BBBBBYKKYBB#RR#BBYKKYBBBBB#..",
        "..#BBBBBBBBBBB#RR#BBBBBBBBBBB#..",
        "..#BBCCBBBBBBB#RR#BBBBBBBCCBB#..",
        "..#BBBBBBBBBBB#RR#BBBBBBBBBBB#..",
        "..############################..",
    ]
    return [_parse_art(art, leg)]


def _make_explosion_frames() -> List[List[List[int]]]:
    """16x16 3-Frame Animated Battle Explosion VFX."""
    leg = {".": 0, "#": 1, "W": 2, "Y": 9, "K": 10, "R": 11, "P": 12}
    f0 = _parse_art([
        "................", "................", "................", "......####......",
        "....##RRRR##....", "...#RRKKKKRR#...", "...#RKWWWWKR#...", "...#RKWYYWKR#...",
        "...#RKWWWWKR#...", "...#RRKKKKRR#...", "....##RRRR##....", "......####......",
        "................", "................", "................", "................",
    ], leg)
    f1 = _parse_art([
        ".....#....#.....", "...##R#..#R##...", "..#RRKK##KKRR#..", ".#RRKKWWWWKKRR#.",
        ".#RKKWWWWWWKKR#.", "#RKKWWYYYYWWKKR#", "#RKWWYYYYYYWWKR#", ".#RKWWYYYYWWKR#.",
        ".#RKKWWWWWWKKR#.", "#RRKKWWWWWWKKRR#", "#RRRKKWWWWKKRRR#", ".#RRRKKKKKKRRR#.",
        "..##RRRRRRRR##..", "...##R####R##...", ".....#....#.....", "................",
    ], leg)
    f2 = _parse_art([
        "..##........##..", ".#PP#..##..#PP#.", ".#P#..#RR#..#P#.", "..#..#RKKR#..#..",
        "....#RK..KR#....", "..#.#K....K#.#..", ".#R#........#R#.", ".#R#........#R#.",
        "..#..#....#..#..", "....#R#..#R#....", ".#P#.#RRRR#.#P#.", ".#PP#..##..#PP#.",
        "..##........##..", "................", "................", "................",
    ], leg)
    return [f0, f1, f2]


ADVANCE_OPS_SCRIPT = '''# ADVANCE OPS — Commercial-Grade Turn-Based Tactical Strategy Engine (KinoScript Native ARM7TDMI!)
# Features:
# - Animated Title Screen (Campaign / Briefing / SRAM Continue) + Hardware Fades (set_fade)
# - 32x32 Commander Portrait Briefing & War Room Intel Status Screen (9-Slice Windows + Gauges)
# - 15x8 Multi-Terrain Battlefield with Defense Stars & 4 Distinct Unit Classes (Inf/Mech/Tank/Arty)
# - Move-then-Command Popup Menu (FIRE / CAPT / WAIT + B Undo-Move Snapback!)
# - LIVE BATTLE FORECAST WINDOW predicting Attacker & Counter-Attack Damage before firing!
# - Impact White Flash + Camera Screen Shake + 3-Frame Explosion VFX + Autonomous Red AI + SRAM!

MAP_W = 15
MAP_H = 8
MAX_UNITS = 24

# Terrain Defense Stars: 1=Plain, 2=Road, 3=Woods, 4=Mtn, 5=River, 6=Bridge, 7..13=Properties
t_def = [0, 1, 0, 2, 4, 0, 0, 3, 3, 3, 3, 3, 4, 4]

# Unit Classes: [0=Infantry, 1=Mech, 2=Tank, 3=Artillery]
c_move = [3, 2, 5, 3]
c_minr = [1, 1, 1, 2]
c_maxr = [1, 1, 1, 3]
c_atk  = [45, 65, 85, 80]
c_cost = [1000, 2000, 3000, 4000]

# Modes: 0=Cursor, 1=UnitMove, 2=FactoryBuild, 3=AITurn, 4=GameOver,
#        5=TitleScreen, 6=COBriefing, 7=UnitCmdPopup, 8=TargetForecast, 9=PauseMenu, 10=WarRoomIntel
day = 1
turn_team = 0
mode = 5
winner = 0
cx = 2
cy = 4
sel_idx = -1
orig_x = 0
orig_y = 0
menu_idx = 0
tgt_idx = -1
funds_blu = 3000
funds_red = 3000
ai_idx = 0
ai_wait = 0
msg_timer = 0
msg_code = 0
rep_cd = 0
fade_val = -12
flash_tmr = 0
vfx_tmr = 0
vfx_x = 0
vfx_y = 0

t_grid = [1] * 120
cap_hp = [20] * 120

u_alive = [0] * 24
u_team  = [0] * 24
u_type  = [0] * 24
u_x     = [0] * 24
u_y     = [0] * 24
u_hp    = [0] * 24
u_acted = [0] * 24


def cell_idx(x, y):
    return y * MAP_W + x


def draw_cell_bg0(x, y, tid):
    bx = x * 2
    by = 2 + y * 2
    set_tile(bx, by, tid)
    set_tile(bx + 1, by, tid)
    set_tile(bx, by + 1, tid)
    set_tile(bx + 1, by + 1, tid)


def find_unit_at(x, y):
    for i in range(MAX_UNITS):
        if u_alive[i] and u_x[i] == x and u_y[i] == y:
            return i
    return -1


def spawn_unit(team, utype, x, y, acted):
    for i in range(MAX_UNITS):
        if u_alive[i] == 0:
            u_alive[i] = 1
            u_team[i] = team
            u_type[i] = utype
            u_x[i] = x
            u_y[i] = y
            u_hp[i] = 10
            u_acted[i] = acted
            return i
    return -1


def can_enter(utype, x, y):
    if x < 0 or x >= MAP_W or y < 0 or y >= MAP_H:
        return 0
    tid = t_grid[cell_idx(x, y)]
    if tid == 5:
        return 0
    if tid == 4 and utype >= 2:
        return 0
    return 1


def calc_damage_pct(atk_i, def_i):
    ut = u_type[atk_i]
    dt = u_type[def_i]
    base = c_atk[ut]
    if ut == 1 and dt >= 2:
        base += 20
    if ut == 2 and dt == 0:
        base += 15
    d_stars = t_def[t_grid[cell_idx(u_x[def_i], u_y[def_i])]]
    pct = (base * u_hp[atk_i] * (10 - d_stars)) // 100
    return clamp(pct, 10, 99)


def calc_damage(atk_i, def_i):
    return max(1, calc_damage_pct(atk_i, def_i) // 10)


def trigger_impact(gx, gy):
    vfx_x = gx * 16
    vfx_y = 16 + gy * 16
    vfx_tmr = 15
    flash_tmr = 6


def perform_attack(atk_i, def_i):
    dmg = calc_damage(atk_i, def_i)
    trigger_impact(u_x[def_i], u_y[def_i])
    u_hp[def_i] -= dmg
    play_sfx(4)
    if u_hp[def_i] <= 0:
        u_alive[def_i] = 0
        play_dma()
        msg_code = 2
        msg_timer = 55
    else:
        dist = abs(u_x[atk_i] - u_x[def_i]) + abs(u_y[atk_i] - u_y[def_i])
        if dist == 1 and c_minr[u_type[def_i]] == 1:
            cdmg = calc_damage(def_i, atk_i)
            u_hp[atk_i] -= cdmg
            if u_hp[atk_i] <= 0:
                u_alive[atk_i] = 0
                play_dma()
    check_victory()


def can_capture_here(ui):
    if u_type[ui] > 1:
        return 0
    tid = t_grid[cell_idx(u_x[ui], u_y[ui])]
    tm = u_team[ui]
    if tid == 7:
        return 1
    if tm == 0 and (tid == 9 or tid == 11 or tid == 13):
        return 1
    if tm == 1 and (tid == 8 or tid == 10 or tid == 12):
        return 1
    return 0


def try_capture(ui):
    if can_capture_here(ui) == 0:
        return 0
    ci = cell_idx(u_x[ui], u_y[ui])
    tid = t_grid[ci]
    tm = u_team[ui]
    cap_hp[ci] -= u_hp[ui]
    play_sfx(1)
    if cap_hp[ci] <= 0:
        cap_hp[ci] = 20
        if tid == 13 and tm == 0:
            t_grid[ci] = 12
            draw_cell_bg0(u_x[ui], u_y[ui], 12)
            winner = 1
            mode = 4
            play_dma()
            play_sfx(5)
            return 1
        if tid == 12 and tm == 1:
            t_grid[ci] = 13
            draw_cell_bg0(u_x[ui], u_y[ui], 13)
            winner = 2
            mode = 4
            play_dma()
            play_sfx(4)
            return 1
        nt = (10 if tm == 0 else 11) if (tid == 10 or tid == 11) else (8 if tm == 0 else 9)
        t_grid[ci] = nt
        draw_cell_bg0(u_x[ui], u_y[ui], nt)
        msg_code = 1
        msg_timer = 55
        play_sfx(5)
    return 1


def find_enemy_in_range(ui, start_from):
    ut = u_type[ui]
    ux = u_x[ui]
    uy = u_y[ui]
    mnr = c_minr[ut]
    mxr = c_maxr[ut]
    for step in range(MAX_UNITS):
        j = (start_from + step) % MAX_UNITS
        if u_alive[j] and u_team[j] != u_team[ui]:
            d = abs(u_x[j] - ux) + abs(u_y[j] - uy)
            if d >= mnr and d <= mxr:
                return j
    return -1


def check_victory():
    b_cnt = 0
    r_cnt = 0
    for i in range(MAX_UNITS):
        if u_alive[i]:
            if u_team[i] == 0: b_cnt += 1
            else: r_cnt += 1
    if r_cnt == 0:
        winner = 1; mode = 4; play_dma(); play_sfx(5)
    elif b_cnt == 0:
        winner = 2; mode = 4; play_dma(); play_sfx(4)


def count_props(team):
    cnt = 0
    for i in range(120):
        t = t_grid[i]
        if team == 0 and (t == 8 or t == 10 or t == 12): cnt += 1
        elif team == 1 and (t == 9 or t == 11 or t == 13): cnt += 1
    return cnt


def count_units(team):
    cnt = 0
    for i in range(MAX_UNITS):
        if u_alive[i] and u_team[i] == team:
            cnt += 1
    return cnt


def award_income(team):
    inc = count_props(team) * 1000
    if team == 0: funds_blu = min(99000, funds_blu + inc)
    else: funds_red = min(99000, funds_red + inc)


def refresh_team(team):
    for i in range(MAX_UNITS):
        if u_alive[i] and u_team[i] == team:
            u_acted[i] = 0
            t = t_grid[cell_idx(u_x[i], u_y[i])]
            own = 1 if ((team == 0 and (t == 8 or t == 10 or t == 12)) or (team == 1 and (t == 9 or t == 11 or t == 13))) else 0
            if own and u_hp[i] < 10:
                u_hp[i] = min(10, u_hp[i] + 2)


def save_sram_state():
    sram_write(0, 65)  # 'A'
    sram_write(1, 87)  # 'W'
    sram_write(2, day & 255)
    sram_write(3, (funds_blu // 100) & 255)


def clear_mid_ui():
    clear_ui_rect(0, 2, 30, 16)


def draw_range_highlights(ui):
    clear_mid_ui()
    ux = u_x[ui]
    uy = u_y[ui]
    ut = u_type[ui]
    mv = c_move[ut]
    mnr = c_minr[ut]
    mxr = c_maxr[ut]
    for y in range(MAP_H):
        for x in range(MAP_W):
            d = abs(x - ux) + abs(y - uy)
            if d > 0 and d <= mv and can_enter(ut, x, y) and find_unit_at(x, y) == -1:
                set_ui_tile(x * 2, 2 + y * 2, 42, 15)
            occ = find_unit_at(x, y)
            if occ >= 0 and u_team[occ] != u_team[ui]:
                if mnr > 1:
                    if d >= mnr and d <= mxr:
                        set_ui_tile(x * 2, 2 + y * 2, 41, 15)
                elif d <= mv + 1:
                    set_ui_tile(x * 2, 2 + y * 2, 41, 15)


def draw_hud():
    if mode == 5:
        # Commercial 9-Slice Title Screen!
        draw_window(2, 1, 26, 6)
        draw_text(7, 2, "ADVANCE OPS GBA")
        draw_text(5, 4, "TACTICAL COMMAND SUITE")
        draw_window(10, 8, 18, 9)
        draw_text(13, 10, "NEW CAMPAIGN")
        draw_text(13, 12, "CO BRIEFING ")
        draw_text(13, 14, "CONTINUE    ")
        draw_text(11, 10 + menu_idx * 2, ">")
        draw_window(2, 8, 7, 7)
        draw_text(4, 18, "A:SELECT  D-PAD:MOVE")
        return

    if mode == 6:
        # Commander Portrait Briefing Screen!
        draw_window(1, 2, 7, 7)
        draw_window(9, 2, 20, 10)
        draw_text(11, 3, "CMDR VANCE (BLUE)")
        draw_text(11, 5, "HOLD THE BRIDGES!")
        draw_text(11, 7, "MOVE THEN PICK FIRE")
        draw_text(11, 9, "OR CAPTURE CITIES!")
        draw_window(4, 13, 22, 5)
        draw_text(6, 15, "> DEPLOY TO BATTLE")
        return

    # Top Tactical Status Bar
    draw_box(0, 0, 30, 2)
    draw_text(1, 0, "DAY")
    draw_num(4, 0, day, 2)
    if turn_team == 0:
        draw_text(7, 0, "BLU")
    else:
        draw_text(7, 0, "RED")
    draw_text(11, 0, "G:")
    draw_num(13, 0, funds_blu, 5)
    draw_text(20, 0, "AI:")
    draw_num(23, 0, funds_red, 5)
    if msg_timer > 0:
        if msg_code == 1: draw_text(1, 1, "PROPERTY CAPTURED! +1000G ")
        elif msg_code == 2: draw_text(1, 1, "ENEMY UNIT DESTROYED!     ")
        elif msg_code == 3: draw_text(1, 1, "REINFORCEMENT DEPLOYED!   ")
        else: draw_text(1, 1, "SAVED TO GBA SRAM!        ")
    elif mode == 1: draw_text(1, 1, "PICK MOVE TILE   B:CANCEL ")
    elif mode == 7: draw_text(1, 1, "COMMAND UNIT     B:UNDO   ")
    elif mode == 8: draw_text(1, 1, "L/R:TARGET A:FIRE B:BACK  ")
    elif mode == 3: draw_text(1, 1, "RED ARMY AI COMMANDING... ")
    else: draw_text(1, 1, "A:SELECT   START:CMD MENU ")

    # Bottom Terrain & Unit Inspector with HP Gauge Bar!
    draw_box(0, 18, 30, 2)
    tid = t_grid[cell_idx(cx, cy)]
    if tid == 1: draw_text(1, 18, "PLAIN  ")
    elif tid == 2: draw_text(1, 18, "ROAD   ")
    elif tid == 3: draw_text(1, 18, "WOODS  ")
    elif tid == 4: draw_text(1, 18, "MTN    ")
    elif tid == 5: draw_text(1, 18, "RIVER  ")
    elif tid == 6: draw_text(1, 18, "BRIDGE ")
    elif tid == 7: draw_text(1, 18, "CITY   ")
    elif tid == 8: draw_text(1, 18, "B-CITY ")
    elif tid == 9: draw_text(1, 18, "R-CITY ")
    elif tid == 10: draw_text(1, 18, "B-FACT ")
    elif tid == 11: draw_text(1, 18, "R-FACT ")
    elif tid == 12: draw_text(1, 18, "BLU HQ ")
    else: draw_text(1, 18, "RED HQ ")
    draw_text(8, 18, "*")
    draw_num(9, 18, t_def[tid], 1)

    ui = find_unit_at(cx, cy)
    if ui >= 0:
        ut = u_type[ui]
        if ut == 0: draw_text(12, 18, "INF ")
        elif ut == 1: draw_text(12, 18, "MECH")
        elif ut == 2: draw_text(12, 18, "TANK")
        else: draw_text(12, 18, "ARTY")
        draw_bar(17, 18, 6, u_hp[ui], 10)
        draw_num(24, 18, u_hp[ui], 2)
        if u_team[ui] == 0:
            draw_text(27, 18, "BL")
        else:
            draw_text(27, 18, "RD")
        draw_text(1, 19, "MV:")
        draw_num(4, 19, c_move[ut], 1)
        draw_text(7, 19, "RNG:")
        draw_num(11, 19, c_minr[ut], 1)
        draw_text(12, 19, "-")
        draw_num(13, 19, c_maxr[ut], 1)
        draw_text(16, 19, "ATK:")
        draw_num(20, 19, c_atk[ut], 2)
    else:
        draw_text(12, 18, "OPEN TERRAIN      ")
        draw_text(1, 19, "GRID (")
        draw_num(7, 19, cx, 2)
        draw_text(9, 19, "/")
        draw_num(10, 19, cy, 2)
        draw_text(12, 19, ")   START:MENU")

    # Contextual 9-Slice Popups!
    if mode == 7:
        # Unit Command Popup (FIRE / CAPT / WAIT)
        px = 18 if cx < 8 else 2
        draw_window(px, 5, 10, 7)
        if find_enemy_in_range(sel_idx, 0) >= 0:
            draw_text(px + 3, 6, "FIRE  ")
        else:
            draw_text(px + 3, 6, "----  ")
        if can_capture_here(sel_idx):
            draw_text(px + 3, 8, "CAPT  ")
        else:
            draw_text(px + 3, 8, "----  ")
        draw_text(px + 3, 10, "WAIT  ")
        draw_text(px + 1, 6 + menu_idx * 2, ">")
    elif mode == 8 and tgt_idx >= 0:
        # LIVE BATTLE FORECAST WINDOW!
        draw_window(4, 3, 22, 8)
        draw_text(6, 4, "BATTLE FORECAST")
        apct = calc_damage_pct(sel_idx, tgt_idx)
        draw_text(6, 6, "ATK DMG:")
        draw_num(15, 6, apct, 2)
        draw_text(17, 6, "%")
        draw_bar(19, 6, 5, apct, 100)
        dist = abs(u_x[sel_idx] - u_x[tgt_idx]) + abs(u_y[sel_idx] - u_y[tgt_idx])
        cpct = calc_damage_pct(tgt_idx, sel_idx) if (dist == 1 and c_minr[u_type[tgt_idx]] == 1) else 0
        draw_text(6, 8, "CTR DMG:")
        draw_num(15, 8, cpct, 2)
        draw_text(17, 8, "%")
        draw_bar(19, 8, 5, cpct, 100)
        draw_text(6, 9, "A:ENGAGE!   B:BACK")
    elif mode == 2:
        # Factory Build Menu
        draw_window(4, 4, 22, 10)
        draw_text(6, 5, "BASE PRODUCTION")
        draw_text(8, 7,  "INF   1000G  MV3")
        draw_text(8, 8,  "MECH  2000G  AT+")
        draw_text(8, 9,  "TANK  3000G  MV5")
        draw_text(8, 10, "ARTY  4000G  R23")
        draw_text(6, 7 + menu_idx, ">")
        draw_text(6, 12, "FUNDS:")
        draw_num(13, 12, funds_blu, 5)
    elif mode == 9:
        # Tactical Command Pause Menu
        draw_window(7, 4, 16, 10)
        draw_text(9, 5, "COMMAND MENU")
        draw_text(10, 7,  "END TURN   ")
        draw_text(10, 8,  "WAR ROOM   ")
        draw_text(10, 9,  "SAVE SRAM  ")
        draw_text(10, 10, "TITLE MENU ")
        draw_text(8, 7 + menu_idx, ">")
    elif mode == 10:
        # War Room Intel Screen
        draw_window(2, 3, 26, 13)
        draw_text(8, 4, "WAR ROOM INTEL")
        bu = count_units(0); ru = count_units(1)
        bp = count_props(0); rp = count_props(1)
        draw_text(4, 6, "BLUE UNITS:")
        draw_num(16, 6, bu, 2)
        draw_bar(19, 6, 7, bu, 12)
        draw_text(4, 8, "RED  UNITS:")
        draw_num(16, 8, ru, 2)
        draw_bar(19, 8, 7, ru, 12)
        draw_text(4, 10, "BLUE BASES:")
        draw_num(16, 10, bp, 2)
        draw_text(20, 10, "+")
        draw_num(21, 10, bp * 1000, 5)
        draw_text(4, 12, "RED  BASES:")
        draw_num(16, 12, rp, 2)
        draw_text(20, 12, "+")
        draw_num(21, 12, rp * 1000, 5)
        draw_text(7, 14, "PRESS B TO RETURN")
    elif mode == 4:
        draw_window(5, 6, 20, 6)
        if winner == 1:
            draw_text(8, 8, "BLUE VICTORY!")
        else:
            draw_text(8, 8, "RED VICTORY! ")
        draw_text(7, 10, "START: NEW WAR")


def render_all_sprites():
    if mode == 5:
        hide_all_sprites()
        set_sprite(0, 28, 76, 5, 0, 0, 0)  # 32x32 CO Portrait in Title Frame!
        return
    if mode == 6:
        hide_all_sprites()
        set_sprite(0, 20, 28, 5, 0, 0, 0)  # 32x32 CO Portrait in Briefing Frame!
        return

    # OAM[0] = Animated Cursor (snaps to target during Battle Forecast!)
    cur_x = u_x[tgt_idx] if (mode == 8 and tgt_idx >= 0) else cx
    cur_y = u_y[tgt_idx] if (mode == 8 and tgt_idx >= 0) else cy
    set_sprite(0, cur_x * 16, 16 + cur_y * 16, 0, (frame_count() >> 4) & 1, 0, 0)

    # OAM[1..24] = Units (Blue=Pal 0, Red=Pal 1, Acted=Pal 2)
    for i in range(MAX_UNITS):
        if u_alive[i]:
            pal = 2 if u_acted[i] else u_team[i]
            hfl = 1 if u_team[i] == 1 else 0
            fr = (frame_count() >> 5) & 1
            set_sprite(1 + i, u_x[i] * 16, 16 + u_y[i] * 16, 1 + u_type[i], fr, pal, hfl)
        else:
            hide_sprite(1 + i)

    # OAM[25] = 3-Frame Animated Explosion VFX!
    if vfx_tmr > 0:
        efr = 0 if vfx_tmr > 10 else (1 if vfx_tmr > 5 else 2)
        set_sprite(25, vfx_x, vfx_y, 6, efr, 0, 0)
    else:
        hide_sprite(25)


def step_ai_unit(ui):
    ut = u_type[ui]
    ux = u_x[ui]
    uy = u_y[ui]
    mnr = c_minr[ut]
    mxr = c_maxr[ut]
    mv = c_move[ut]
    best_t = -1
    best_hp = 99
    for j in range(MAX_UNITS):
        if u_alive[j] and u_team[j] == 0:
            d = abs(u_x[j] - ux) + abs(u_y[j] - uy)
            if mnr > 1:
                if d >= mnr and d <= mxr and u_hp[j] < best_hp:
                    best_hp = u_hp[j]; best_t = j
            elif d == 1 and u_hp[j] < best_hp:
                best_hp = u_hp[j]; best_t = j
    if best_t >= 0:
        cx = u_x[best_t]; cy = u_y[best_t]
        perform_attack(ui, best_t)
        u_acted[ui] = 1
        return 1

    goal_x = 1; goal_y = 4; best_d = 999
    for j in range(MAX_UNITS):
        if u_alive[j] and u_team[j] == 0:
            d = abs(u_x[j] - ux) + abs(u_y[j] - uy)
            if d < best_d:
                best_d = d; goal_x = u_x[j]; goal_y = u_y[j]
    bx = ux; by = uy; bscore = abs(ux - goal_x) + abs(uy - goal_y)
    for y in range(MAP_H):
        for x in range(MAP_W):
            md = abs(x - ux) + abs(y - uy)
            if md > 0 and md <= mv and can_enter(ut, x, y) and find_unit_at(x, y) == -1:
                sc = abs(x - goal_x) + abs(y - goal_y)
                if sc < bscore:
                    bscore = sc; bx = x; by = y
    u_x[ui] = bx; u_y[ui] = by
    cx = bx; cy = by
    if ut <= 1:
        try_capture(ui)
    if mnr == 1:
        for j in range(MAX_UNITS):
            if u_alive[j] and u_team[j] == 0 and abs(u_x[j] - bx) + abs(u_y[j] - by) == 1:
                perform_attack(ui, j)
                break
    u_acted[ui] = 1
    return 1


def ai_try_build():
    if find_unit_at(13, 2) == -1:
        if funds_red >= 3000:
            funds_red -= 3000; spawn_unit(1, 2, 13, 2, 1); play_sfx(1)
        elif funds_red >= 1000:
            funds_red -= 1000; spawn_unit(1, 0, 13, 2, 1); play_sfx(1)


def setup_battle(start_mode):
    clear_ui()
    hide_all_sprites()
    day = 1; turn_team = 0; mode = start_mode; winner = 0
    cx = 2; cy = 4; sel_idx = -1; menu_idx = 0; tgt_idx = -1
    funds_blu = 3000; funds_red = 3000; msg_timer = 0
    fade_val = -10; flash_tmr = 0; vfx_tmr = 0
    for i in range(MAX_UNITS): u_alive[i] = 0
    for i in range(120): t_grid[i] = 1; cap_hp[i] = 20

    for y in range(MAP_H): t_grid[cell_idx(7, y)] = 5
    t_grid[cell_idx(7, 2)] = 6; t_grid[cell_idx(7, 5)] = 6
    for x in range(1, 14):
        if x != 7:
            t_grid[cell_idx(x, 2)] = 2; t_grid[cell_idx(x, 5)] = 2
    t_grid[cell_idx(4, 1)] = 3; t_grid[cell_idx(5, 3)] = 3; t_grid[cell_idx(4, 6)] = 3
    t_grid[cell_idx(10, 1)] = 3; t_grid[cell_idx(9, 4)] = 3; t_grid[cell_idx(10, 6)] = 3
    t_grid[cell_idx(6, 0)] = 4; t_grid[cell_idx(6, 7)] = 4; t_grid[cell_idx(8, 0)] = 4; t_grid[cell_idx(8, 7)] = 4
    t_grid[cell_idx(5, 1)] = 7; t_grid[cell_idx(5, 6)] = 7
    t_grid[cell_idx(9, 1)] = 7; t_grid[cell_idx(9, 6)] = 7
    t_grid[cell_idx(1, 4)] = 12; t_grid[cell_idx(1, 2)] = 10; t_grid[cell_idx(2, 6)] = 8
    t_grid[cell_idx(13, 4)] = 13; t_grid[cell_idx(13, 2)] = 11; t_grid[cell_idx(12, 6)] = 9

    for y in range(MAP_H):
        for x in range(MAP_W):
            draw_cell_bg0(x, y, t_grid[cell_idx(x, y)])

    spawn_unit(0, 0, 3, 2, 0); spawn_unit(0, 0, 3, 5, 0); spawn_unit(0, 1, 2, 4, 0)
    spawn_unit(0, 2, 4, 2, 0); spawn_unit(0, 2, 4, 5, 0); spawn_unit(0, 3, 2, 3, 0)
    spawn_unit(1, 0, 11, 2, 0); spawn_unit(1, 0, 11, 5, 0); spawn_unit(1, 1, 12, 4, 0)
    spawn_unit(1, 2, 10, 2, 0); spawn_unit(1, 2, 10, 5, 0); spawn_unit(1, 3, 12, 3, 0)
    draw_hud()
    render_all_sprites()


def on_init():
    setup_battle(5)  # Boot directly into Commercial 9-Slice Title Screen!


def move_cursor_input():
    if rep_cd > 0: rep_cd -= 1
    dx = 0; dy = 0
    if key_pressed(BTN_RIGHT) or (key_held(BTN_RIGHT) and rep_cd == 0): dx = 1
    elif key_pressed(BTN_LEFT) or (key_held(BTN_LEFT) and rep_cd == 0): dx = -1
    if key_pressed(BTN_DOWN) or (key_held(BTN_DOWN) and rep_cd == 0): dy = 1
    elif key_pressed(BTN_UP) or (key_held(BTN_UP) and rep_cd == 0): dy = -1
    if dx != 0 or dy != 0:
        cx = clamp(cx + dx, 0, MAP_W - 1)
        cy = clamp(cy + dy, 0, MAP_H - 1)
        rep_cd = 7
        play_sfx(1)


def on_frame():
    if msg_timer > 0: msg_timer -= 1
    if vfx_tmr > 0: vfx_tmr -= 1

    # Hardware Fade & Impact Flash + Screen Shake!
    if flash_tmr > 0:
        flash_tmr -= 1
        set_fade(flash_tmr * 2)
        sh = 2 if (flash_tmr & 1) else -2
        scroll_bg(0, sh, sh)
    elif fade_val < 0:
        fade_val += 2
        set_fade(fade_val)
        scroll_bg(0, 0, 0)
    else:
        set_fade(0)
        scroll_bg(0, 0, 0)

    if mode == 5:
        if key_pressed(BTN_DOWN):
            menu_idx = (menu_idx + 1) % 3; play_sfx(1)
        elif key_pressed(BTN_UP):
            menu_idx = (menu_idx + 2) % 3; play_sfx(1)
        elif key_pressed(BTN_A) or key_pressed(BTN_START):
            clear_ui()
            if menu_idx == 1:
                mode = 6; fade_val = -8; play_sfx(0)
            else:
                if menu_idx == 2 and sram_read(0) == 65 and sram_read(1) == 87:
                    day = max(1, sram_read(2))
                    funds_blu = max(1000, sram_read(3) * 100)
                mode = 0; fade_val = -8; play_sfx(5)
        draw_hud(); render_all_sprites()
        return

    if mode == 6:
        if key_pressed(BTN_A) or key_pressed(BTN_START) or key_pressed(BTN_B):
            clear_ui(); mode = 0; fade_val = -8; play_sfx(5)
        draw_hud(); render_all_sprites()
        return

    if mode == 4:
        if key_pressed(BTN_START) or key_pressed(BTN_A):
            setup_battle(5)
        draw_hud(); render_all_sprites()
        return

    if mode == 10:
        if key_pressed(BTN_B) or key_pressed(BTN_A) or key_pressed(BTN_START):
            clear_mid_ui(); mode = 0; play_sfx(3)
        draw_hud(); render_all_sprites()
        return

    if mode == 9:
        if key_pressed(BTN_DOWN):
            menu_idx = (menu_idx + 1) & 3; play_sfx(1)
        elif key_pressed(BTN_UP):
            menu_idx = (menu_idx + 3) & 3; play_sfx(1)
        elif key_pressed(BTN_B) or key_pressed(BTN_START):
            clear_mid_ui(); mode = 0; play_sfx(3)
        elif key_pressed(BTN_A):
            clear_mid_ui()
            if menu_idx == 0:
                turn_team = 1; award_income(1); refresh_team(1); ai_idx = 0; ai_wait = 8; mode = 3; play_sfx(3)
            elif menu_idx == 1:
                mode = 10; play_sfx(0)
            elif menu_idx == 2:
                save_sram_state(); msg_code = 4; msg_timer = 60; mode = 0; play_sfx(1)
            else:
                setup_battle(5)
        draw_hud(); render_all_sprites()
        return

    if mode == 3:
        if ai_wait > 0:
            ai_wait -= 1
        else:
            acted_one = 0
            while ai_idx < MAX_UNITS:
                if u_alive[ai_idx] and u_team[ai_idx] == 1 and u_acted[ai_idx] == 0:
                    step_ai_unit(ai_idx); ai_idx += 1; ai_wait = 10; acted_one = 1; break
                ai_idx += 1
            if acted_one == 0 and mode == 3:
                ai_try_build()
                day += 1; turn_team = 0; award_income(0); refresh_team(0)
                save_sram_state()
                mode = 0; cx = 2; cy = 4; play_sfx(5)
        draw_hud(); render_all_sprites()
        return

    if mode == 2:
        if key_pressed(BTN_DOWN):
            menu_idx = (menu_idx + 1) & 3; play_sfx(1)
        elif key_pressed(BTN_UP):
            menu_idx = (menu_idx + 3) & 3; play_sfx(1)
        elif key_pressed(BTN_B):
            clear_mid_ui(); mode = 0; play_sfx(3)
        elif key_pressed(BTN_A):
            cost = c_cost[menu_idx]
            if funds_blu >= cost:
                funds_blu -= cost; spawn_unit(0, menu_idx, cx, cy, 1)
                msg_code = 3; msg_timer = 50; play_sfx(5); clear_mid_ui(); mode = 0
            else:
                play_sfx(4)
        draw_hud(); render_all_sprites()
        return

    if mode == 7:
        # Unit Command Popup (0=FIRE, 1=CAPT, 2=WAIT) — B snaps unit back to orig_x, orig_y!
        if key_pressed(BTN_DOWN):
            menu_idx = (menu_idx + 1) % 3; play_sfx(1)
        elif key_pressed(BTN_UP):
            menu_idx = (menu_idx + 2) % 3; play_sfx(1)
        elif key_pressed(BTN_B):
            u_x[sel_idx] = orig_x; u_y[sel_idx] = orig_y
            cx = orig_x; cy = orig_y
            clear_mid_ui(); mode = 1; draw_range_highlights(sel_idx); play_sfx(3)
        elif key_pressed(BTN_A):
            if menu_idx == 0:
                t0 = find_enemy_in_range(sel_idx, 0)
                if t0 >= 0:
                    tgt_idx = t0; clear_mid_ui(); mode = 8; play_sfx(0)
                else:
                    play_sfx(4)
            elif menu_idx == 1:
                if can_capture_here(sel_idx):
                    try_capture(sel_idx); u_acted[sel_idx] = 1
                    clear_mid_ui(); sel_idx = -1
                    if mode == 7: mode = 0
                else:
                    play_sfx(4)
            else:
                u_acted[sel_idx] = 1; clear_mid_ui(); sel_idx = -1; mode = 0; play_sfx(1)
        draw_hud(); render_all_sprites()
        return

    if mode == 8:
        # Target Selector with LIVE BATTLE FORECAST!
        if key_pressed(BTN_RIGHT) or key_pressed(BTN_DOWN):
            tgt_idx = find_enemy_in_range(sel_idx, tgt_idx + 1); play_sfx(1)
        elif key_pressed(BTN_LEFT) or key_pressed(BTN_UP):
            tgt_idx = find_enemy_in_range(sel_idx, tgt_idx + 1); play_sfx(1)
        elif key_pressed(BTN_B):
            clear_mid_ui(); mode = 7; play_sfx(3)
        elif key_pressed(BTN_A) and tgt_idx >= 0:
            perform_attack(sel_idx, tgt_idx)
            u_acted[sel_idx] = 1
            clear_mid_ui(); sel_idx = -1; tgt_idx = -1
            if mode == 8: mode = 0
        draw_hud(); render_all_sprites()
        return

    move_cursor_input()
    if mode == 0:
        if key_pressed(BTN_START):
            clear_mid_ui(); menu_idx = 0; mode = 9; play_sfx(0)
        elif key_pressed(BTN_A):
            ui = find_unit_at(cx, cy)
            if ui >= 0 and u_team[ui] == 0 and u_acted[ui] == 0:
                sel_idx = ui; orig_x = u_x[ui]; orig_y = u_y[ui]
                mode = 1; draw_range_highlights(ui); play_sfx(0)
            elif ui == -1 and t_grid[cell_idx(cx, cy)] == 10:
                menu_idx = 0; mode = 2; play_sfx(0)
            else:
                play_sfx(3)
    elif mode == 1:
        if key_pressed(BTN_B):
            clear_mid_ui(); sel_idx = -1; mode = 0; play_sfx(3)
        elif key_pressed(BTN_A):
            d = abs(cx - orig_x) + abs(cy - orig_y)
            ut = u_type[sel_idx]
            tgt = find_unit_at(cx, cy)
            if (tgt == -1 or tgt == sel_idx) and d <= c_move[ut] and can_enter(ut, cx, cy):
                u_x[sel_idx] = cx; u_y[sel_idx] = cy
                clear_mid_ui()
                # Smart default menu cursor: FIRE if enemy in range, else CAPT if capturable, else WAIT!
                if find_enemy_in_range(sel_idx, 0) >= 0: menu_idx = 0
                elif can_capture_here(sel_idx): menu_idx = 1
                else: menu_idx = 2
                mode = 7; play_sfx(0)
            else:
                play_sfx(4)

    draw_hud()
    render_all_sprites()
'''


def _make_tactical_tiles() -> List[TileAsset]:
    """14 richly shaded GBA tactical terrain tiles (Multi-tone Plains, Layered Woods, Snow Peaks, Cities, HQs)."""
    leg = {".": 0, "#": 1, "W": 2, "S": 3, "G": 4, "B": 5, "C": 6, "M": 7, "E": 8, "Y": 9, "K": 10, "R": 11, "P": 12, "D": 15}
    return [
        TileAsset("HUD Empty", TILE_EMPTY, 0, empty_grid(8, 8, 0)),
        TileAsset("Plains (DEF 1)", TILE_EMPTY, 0, _parse_art([
            "MMEMMMMM", "MMMMMMMM", "MMMMMMEM", "MMKMMMMM",
            "MMMMMMMM", "MEMMMMMM", "MMMMMEMM", "MMMMMMMM",
        ], leg)),
        TileAsset("Road (DEF 0)", TILE_EMPTY, 0, _parse_art([
            "GGGGGGGG", "GSSSSSSG", "GSGGGGSG", "GSWWGGSG",
            "GSGGGGSG", "GSGGWWSG", "GSSSSSSG", "GGGGGGGG",
        ], leg)),
        TileAsset("Woods (DEF 2)", TILE_EMPTY, 0, _parse_art([
            "MM####MM", "M#EMME#M", "#EMKKME#", "#EEEMEE#",
            "M#E##E#M", "MM#DD#MM", "M##DD##M", "MMMMMMMM",
        ], leg)),
        TileAsset("Mountain (DEF 4)", TILE_SOLID, 0, _parse_art([
            "...##...", "..#WW#..", ".#WWSS#.", ".#SSGG#.",
            "#SSGGGG#", "#GG##GG#", "#G####G#", "########",
        ], leg)),
        TileAsset("River (Blocked)", TILE_WATER, 0, _parse_art([
            "BBBBBBBB", "BWWCBBBB", "BBBBBBBB", "BBCCWBBB",
            "BBBBBBBB", "BBBBWWCB", "BBBBBBBB", "CCBBBBCC",
        ], leg)),
        TileAsset("Bridge (DEF 0)", TILE_EMPTY, 0, _parse_art([
            "########", "DYYYYYYD", "D#DDDD#D", "DDDDDDDD",
            "DDDDDDDD", "D#DDDD#D", "DYYYYYYD", "########",
        ], leg)),
        TileAsset("Neutral City", TILE_EMPTY, 0, _parse_art([
            "........", ".######.", "#SWWWWS#", "#S#KK#S#",
            "#SSSSSS#", "#S#WW#S#", "#SGGGGS#", "########",
        ], leg)),
        TileAsset("Blue City", TILE_EMPTY, 0, _parse_art([
            "........", ".######.", "#BCCCCB#", "#B#KK#B#",
            "#BBBBBB#", "#B#WW#B#", "#B####B#", "########",
        ], leg)),
        TileAsset("Red City", TILE_EMPTY, 0, _parse_art([
            "........", ".######.", "#RPPPPR#", "#R#KK#R#",
            "#RRRRRR#", "#R#WW#R#", "#R####R#", "########",
        ], leg)),
        TileAsset("Blue Factory", TILE_EMPTY, 0, _parse_art([
            ".##.....", ".#C#####", "#BCCCCB#", "#B#KK#B#",
            "#BBBBBB#", "#B#WW#B#", "#BGGGGB#", "########",
        ], leg)),
        TileAsset("Red Factory", TILE_EMPTY, 0, _parse_art([
            ".##.....", ".#P#####", "#RPPPPR#", "#R#KK#R#",
            "#RRRRRR#", "#R#WW#R#", "#RGGGGR#", "########",
        ], leg)),
        TileAsset("Blue HQ", TILE_EMPTY, 0, _parse_art([
            "...##...", "..#CC#..", ".#BWWB#.", "#BCKKCB#",
            "#BCCCCB#", "#BBBBBB#", "#B#WW#B#", "########",
        ], leg)),
        TileAsset("Red HQ", TILE_EMPTY, 0, _parse_art([
            "...##...", "..#KK#..", ".#RWW#..", "#RPKKPR#",
            "#RPPPPR#", "#RRRRRR#", "#R#WW#R#", "########",
        ], leg)),
    ]


def _create_tactical_grid() -> KinoPixelProject:
    """Showcase 4: Commercial-Grade Turn-Based Tactical Strategy Game powered by KinoScript!"""
    blue_pal = [
        "#101424", "#121826", "#F8FAFC", "#CBD5E1",
        "#64748B", "#2563EB", "#38BDF8", "#22C55E",
        "#15803D", "#F59E0B", "#FDE047", "#EF4444",
        "#FB7185", "#A855F7", "#0284C7", "#92400E",
    ]
    red_pal = [
        "#101424", "#121826", "#F8FAFC", "#FED7AA",
        "#64748B", "#DC2626", "#FB7185", "#22C55E",
        "#15803D", "#F59E0B", "#FDE047", "#EF4444",
        "#FB7185", "#A855F7", "#0284C7", "#92400E",
    ]
    acted_pal = [
        "#101424", "#111520", "#94A3B8", "#64748B",
        "#475569", "#475569", "#64748B", "#334155",
        "#1E293B", "#64748B", "#94A3B8", "#475569",
        "#64748B", "#475569", "#334155", "#334155",
    ]
    pals = [blue_pal, red_pal, acted_pal]

    cursor = SpriteAsset(name="Tactical Cursor", role="player", width=16, height=16, palette_index=0, frames=_make_cursor_frames(), animations=[AnimationClip("idle", [0, 1], fps=6, loop=True)])
    infantry = SpriteAsset(name="Infantry Squad", role="enemy", width=16, height=16, palette_index=0, frames=_make_infantry_frames(), animations=[AnimationClip("idle", [0, 1], fps=4, loop=True)])
    mech = SpriteAsset(name="Mech Bazooka", role="enemy", width=16, height=16, palette_index=0, frames=_make_mech_frames(), animations=[AnimationClip("idle", [0], fps=4, loop=True)])
    tank = SpriteAsset(name="Battle Tank", role="enemy", width=16, height=16, palette_index=0, frames=_make_tank_unit_frames(), animations=[AnimationClip("idle", [0, 1], fps=6, loop=True)])
    arty = SpriteAsset(name="Artillery", role="enemy", width=16, height=16, palette_index=0, frames=_make_artillery_frames(), animations=[AnimationClip("idle", [0], fps=4, loop=True)])
    co_port = SpriteAsset(name="Commander Portrait (32×32)", role="prop", width=32, height=32, palette_index=0, frames=_make_co_portrait_32x32(), animations=[AnimationClip("idle", [0], fps=4, loop=True)])
    boom = SpriteAsset(name="Battle Explosion (3f)", role="projectile", width=16, height=16, palette_index=0, frames=_make_explosion_frames(), animations=[AnimationClip("boom", [0, 1, 2], fps=12, loop=False)])

    tiles = _make_tactical_tiles()
    sfx = _make_default_sfx()
    w, h = 30, 20
    c0 = empty_grid(w, h, 1)
    rm0 = LevelMap(
        name="Sector Alpha — River Front", width=w, height=h, world_x=1, world_y=1,
        spawn_x=4, spawn_y=8, cells=c0, parallax_enabled=False,
    )

    proj = KinoPixelProject(
        title="ADVANCE OPS", game_code="KAW1", maker_code="KP", target_system="GBA",
        physics_mode="tactical", gravity=0, max_fall_speed=512, bg_color_hex="#0D1528",
        alpha_blend_enabled=False, sram_save_enabled=True, starting_abilities=ABIL_NONE,
        starting_vars=[30, 0, 0, 0, 0, 0, 0, 0],
        palettes=pals, sprites=[cursor, infantry, mech, tank, arty, co_port, boom], tiles=tiles,
        rooms=[rm0], active_room_idx=0, button_rules=[], sfx_list=sfx,
        direct_sound=DirectSoundConfig(enabled=True, preset="Boss Explosion", sample_rate=8192),
        script_enabled=True,
        script_code=ADVANCE_OPS_SCRIPT,
    )
    proj.sequence_genie.ensure_initialized()
    proj.sequence_genie.scale = "MAJ"
    proj.sequence_genie.bpm = 122
    proj.sequence_genie.save_slot(0)
    proj.snapshot_push("Initial Advance Ops Tactical Strategy Project")
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
