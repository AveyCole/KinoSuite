"""KinoPixel Custom Interactive Studio Widgets:
- PixelCanvasWidget (Pencil, Eraser, Flood Fill, Line, Rect, Eyedropper, Mirror X, Onion Skin)
- PaletteStripWidget (Hardware 15-bit BGR555 swatch strip)
- LevelMapCanvasWidget (64x32 scrollable map, collision overlay, spawn/enemy placement, viewport guide)
- HandheldDiagramWidget (Interactive clickable GBA/GB console diagram for visual button wiring)
- SfxWaveformWidget (Live PSG waveform visualizer)
- PlaytestScreenWidget (Crisp integer-scaled 60fps handheld screen + keyboard & mouse gamepad)
"""
from __future__ import annotations

from collections import deque
from typing import Callable, Dict, List, Optional, Set, Tuple

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QColorDialog, QSizePolicy, QWidget

from .models import (
    ACTION_NAMES,
    KinoPixelProject,
    TILE_TYPE_COLORS,
    hex_to_bgr555,
    quantize_hex_bgr555,
)
from .theme import get_palette


def render_grid_pixmap(
    grid: List[List[int]],
    palette_hex: List[str],
    scale: int = 2,
    transparent_zero: bool = True,
) -> QPixmap:
    """Render an indexed pixel grid into a crisp nearest-neighbor QPixmap."""
    h = len(grid)
    w = len(grid[0]) if h else 8
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    cols = [QColor(c) for c in palette_hex]
    for y in range(h):
        row = grid[y]
        for x in range(w):
            ci = row[x]
            if ci == 0 and transparent_zero:
                continue
            c = cols[ci % len(cols)] if cols else QColor("#FFFFFF")
            img.setPixelColor(x, y, c)
    pm = QPixmap.fromImage(img)
    if scale > 1:
        return pm.scaled(w * scale, h * scale, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
    return pm


# ---------------------------------------------------------------------------
# 1. Pixel Art Canvas Widget (8x8 Tiles & 16x16 Sprites)
# ---------------------------------------------------------------------------
class PixelCanvasWidget(QWidget):
    pixelsChanged = Signal()
    strokeFinished = Signal(str)
    colorPicked = Signal(int)
    hoverChanged = Signal(int, int)

    def __init__(self, transparent_zero: bool = True, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.grid: List[List[int]] = [[0] * 16 for _ in range(16)]
        self.onion_grid: Optional[List[List[int]]] = None
        self.palette_hex: List[str] = ["#101424", "#FFFFFF"]
        self.transparent_zero = transparent_zero
        self.active_color: int = 1
        self.tool: str = "pencil"  # pencil | eraser | fill | eyedropper | line | rect
        self.mirror_x: bool = False
        self.show_grid: bool = True
        self.show_onion: bool = False
        self.theme_name: str = "Dark"

        self._drawing: bool = False
        self._right_erase: bool = False
        self._start_pt: Optional[Tuple[int, int]] = None
        self._preview_pt: Optional[Tuple[int, int]] = None
        self._hover_pt: Optional[Tuple[int, int]] = None
        self._dirty_stroke: bool = False

        self.setMouseTracking(True)
        self.setMinimumSize(180, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, grid: List[List[int]], palette_hex: List[str], onion_grid: Optional[List[List[int]]] = None) -> None:
        self.grid = grid
        self.palette_hex = palette_hex
        self.onion_grid = onion_grid
        self.update()

    def _grid_dims(self) -> Tuple[int, int]:
        h = len(self.grid)
        w = len(self.grid[0]) if h else 16
        return w, h

    def _canvas_rect(self) -> Tuple[int, int, int]:
        gw, gh = self._grid_dims()
        pad = 10
        cell = max(4, min((self.width() - pad * 2) // max(1, gw), (self.height() - pad * 2) // max(1, gh)))
        ox = (self.width() - cell * gw) // 2
        oy = (self.height() - cell * gh) // 2
        return ox, oy, cell

    def _pos_to_cell(self, pos: QPointF) -> Optional[Tuple[int, int]]:
        gw, gh = self._grid_dims()
        ox, oy, cell = self._canvas_rect()
        cx = int((pos.x() - ox) // cell)
        cy = int((pos.y() - oy) // cell)
        if 0 <= cx < gw and 0 <= cy < gh:
            return cx, cy
        return None

    def _plot(self, x: int, y: int, col: int) -> None:
        gw, gh = self._grid_dims()
        if 0 <= x < gw and 0 <= y < gh:
            if self.grid[y][x] != col:
                self.grid[y][x] = col
                self._dirty_stroke = True
            if self.mirror_x:
                mx = gw - 1 - x
                if self.grid[y][mx] != col:
                    self.grid[y][mx] = col
                    self._dirty_stroke = True

    def _flood_fill(self, sx: int, sy: int, target_col: int) -> None:
        gw, gh = self._grid_dims()
        orig = self.grid[sy][sx]
        if orig == target_col:
            return
        q = deque([(sx, sy)])
        seen = {(sx, sy)}
        while q:
            x, y = q.popleft()
            self.grid[y][x] = target_col
            self._dirty_stroke = True
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < gw and 0 <= ny < gh and (nx, ny) not in seen and self.grid[ny][nx] == orig:
                    seen.add((nx, ny))
                    q.append((nx, ny))

    def _bresenham(self, x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
        pts = []
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            pts.append((x, y))
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy
        return pts

    def mousePressEvent(self, event: QMouseEvent) -> None:
        cell = self._pos_to_cell(event.position())
        if cell is None:
            return
        cx, cy = cell
        self._dirty_stroke = False
        self._right_erase = event.button() == Qt.MouseButton.RightButton
        col = 0 if (self._right_erase or self.tool == "eraser") else self.active_color

        if not self._right_erase and self.tool == "eyedropper":
            self.colorPicked.emit(self.grid[cy][cx])
            return
        if not self._right_erase and self.tool == "fill":
            self._flood_fill(cx, cy, col)
            if self._dirty_stroke:
                self.pixelsChanged.emit()
                self.strokeFinished.emit("Flood Fill")
            self.update()
            return
        if not self._right_erase and self.tool in ("line", "rect"):
            self._drawing = True
            self._start_pt = (cx, cy)
            self._preview_pt = (cx, cy)
            self.update()
            return

        self._drawing = True
        self._plot(cx, cy, col)
        self.pixelsChanged.emit()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        cell = self._pos_to_cell(event.position())
        self._hover_pt = cell
        if cell is not None:
            self.hoverChanged.emit(cell[0], cell[1])
            if self._drawing:
                cx, cy = cell
                if not self._right_erase and self.tool in ("line", "rect"):
                    self._preview_pt = (cx, cy)
                else:
                    col = 0 if (self._right_erase or self.tool == "eraser") else self.active_color
                    self._plot(cx, cy, col)
                    self.pixelsChanged.emit()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._drawing:
            return
        self._drawing = False
        if not self._right_erase and self.tool in ("line", "rect") and self._start_pt and self._preview_pt:
            x0, y0 = self._start_pt
            x1, y1 = self._preview_pt
            if self.tool == "line":
                for px, py in self._bresenham(x0, y0, x1, y1):
                    self._plot(px, py, self.active_color)
            else:
                for px in range(min(x0, x1), max(x0, x1) + 1):
                    self._plot(px, y0, self.active_color)
                    self._plot(px, y1, self.active_color)
                for py in range(min(y0, y1), max(y0, y1) + 1):
                    self._plot(x0, py, self.active_color)
                    self._plot(x1, py, self.active_color)
            self.pixelsChanged.emit()
        self._start_pt = None
        self._preview_pt = None
        if self._dirty_stroke:
            self.strokeFinished.emit(f"Paint ({self.tool})")
        self.update()

    def paintEvent(self, event) -> None:
        pal = get_palette(self.theme_name)
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(pal["bg_canvas"]))

        gw, gh = self._grid_dims()
        ox, oy, cell = self._canvas_rect()
        ca, cb = QColor(pal["checker_a"]), QColor(pal["checker_b"])
        cols = [QColor(c) for c in self.palette_hex]

        # Draw checkerboard + onion skin + pixels
        for y in range(gh):
            for x in range(gw):
                r = QRect(ox + x * cell, oy + y * cell, cell, cell)
                p.fillRect(r, ca if ((x + y) & 1) == 0 else cb)
                if self.show_onion and self.onion_grid and y < len(self.onion_grid) and x < len(self.onion_grid[y]):
                    oi = self.onion_grid[y][x]
                    if oi > 0 and cols:
                        oc = QColor(cols[oi % len(cols)])
                        oc.setAlpha(75)
                        p.fillRect(r, oc)
                ci = self.grid[y][x]
                if ci > 0 or not self.transparent_zero:
                    if cols:
                        p.fillRect(r, cols[ci % len(cols)])

        # Live line/rect preview
        if self._drawing and self._start_pt and self._preview_pt and self.tool in ("line", "rect"):
            x0, y0 = self._start_pt
            x1, y1 = self._preview_pt
            pc = QColor(cols[self.active_color % len(cols)]) if cols else QColor("#A78BFA")
            pc.setAlpha(185)
            pts = (
                self._bresenham(x0, y0, x1, y1)
                if self.tool == "line"
                else (
                    [(px, y0) for px in range(min(x0, x1), max(x0, x1) + 1)]
                    + [(px, y1) for px in range(min(x0, x1), max(x0, x1) + 1)]
                    + [(x0, py) for py in range(min(y0, y1), max(y0, y1) + 1)]
                    + [(x1, py) for py in range(min(y0, y1), max(y0, y1) + 1)]
                )
            )
            for px, py in pts:
                p.fillRect(QRect(ox + px * cell, oy + py * cell, cell, cell), pc)

        # Crisp pixel grid + 8x8 tile quadrant guide
        if self.show_grid and cell >= 6:
            p.setPen(QPen(QColor(pal["grid_minor"]), 1))
            for x in range(gw + 1):
                p.drawLine(ox + x * cell, oy, ox + x * cell, oy + gh * cell)
            for y in range(gh + 1):
                p.drawLine(ox, oy + y * cell, ox + gw * cell, oy + y * cell)
            if gw >= 16:
                p.setPen(QPen(QColor(pal["grid_major"]), 1, Qt.PenStyle.DashLine))
                p.drawLine(ox + (gw // 2) * cell, oy, ox + (gw // 2) * cell, oy + gh * cell)
                p.drawLine(ox, oy + (gh // 2) * cell, ox + gw * cell, oy + (gh // 2) * cell)

        # Mirror axis indicator
        if self.mirror_x:
            p.setPen(QPen(QColor(pal["accent_bright"]), 2, Qt.PenStyle.DashLine))
            mx = ox + (gw * cell) // 2
            p.drawLine(mx, oy, mx, oy + gh * cell)

        # Outer border & hover cursor
        p.setPen(QPen(QColor(pal["border_strong"]), 1))
        p.drawRect(ox, oy, gw * cell, gh * cell)
        if self._hover_pt:
            hx, hy = self._hover_pt
            p.setPen(QPen(QColor(pal["accent_bright"]), 2))
            p.drawRect(ox + hx * cell + 1, oy + hy * cell + 1, cell - 2, cell - 2)
        p.end()


# ---------------------------------------------------------------------------
# 2. Hardware Palette Strip Widget (BGR555 Quantized)
# ---------------------------------------------------------------------------
class PaletteStripWidget(QWidget):
    colorSelected = Signal(int)
    paletteEdited = Signal()

    def __init__(self, transparent_zero: bool = True, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.colors: List[str] = ["#101424", "#FFFFFF", "#8B5CF6", "#34D399"]
        self.active_count: int = 16
        self.selected_idx: int = 1
        self.transparent_zero = transparent_zero
        self.setFixedHeight(64)
        self.setToolTip("Click to select color | Double-click to edit hardware 15-bit BGR555 swatch")

    def set_palette(self, colors: List[str], active_count: int = 16) -> None:
        self.colors = colors
        self.active_count = max(4, min(16, active_count))
        if self.selected_idx >= self.active_count:
            self.selected_idx = 1
        self.update()

    def _swatch_rect(self, idx: int) -> QRect:
        cols = 8 if self.active_count > 4 else 4
        rows = 2 if self.active_count > 4 else 1
        sw = max(18, (self.width() - 8) // cols)
        sh = max(22, (self.height() - 8) // rows)
        r = idx // cols
        c = idx % cols
        return QRect(4 + c * sw, 4 + r * sh, sw - 4, sh - 4)

    def _hit_index(self, pos: QPointF) -> int:
        pt = QPoint(int(pos.x()), int(pos.y()))
        for i in range(min(self.active_count, len(self.colors))):
            if self._swatch_rect(i).contains(pt):
                return i
        return -1

    def mousePressEvent(self, event: QMouseEvent) -> None:
        idx = self._hit_index(event.position())
        if idx >= 0:
            self.selected_idx = idx
            self.colorSelected.emit(idx)
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        idx = self._hit_index(event.position())
        if idx < 0:
            return
        cur = QColor(self.colors[idx])
        chosen = QColorDialog.getColor(cur, self, f"Edit Palette Color #{idx} (Quantized to BGR555)")
        if chosen.isValid():
            self.colors[idx] = quantize_hex_bgr555(chosen.name())
            self.paletteEdited.emit()
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i in range(min(self.active_count, len(self.colors))):
            r = self._swatch_rect(i)
            c = QColor(self.colors[i])
            p.setBrush(QBrush(c))
            if i == self.selected_idx:
                p.setPen(QPen(QColor("#FFFFFF"), 2.2))
            else:
                p.setPen(QPen(QColor("#364056"), 1.0))
            p.drawRoundedRect(r, 4, 4)
            if i == 0 and self.transparent_zero:
                p.setPen(QPen(QColor("#F43F5E"), 1.5))
                p.drawLine(r.topLeft() + QPoint(3, 3), r.bottomRight() - QPoint(3, 3))
                p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
                p.setPen(QColor("#E6EAF2"))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, "T")
        p.end()


# ---------------------------------------------------------------------------
# 3. Scrollable 64x32 Level Map Editor Canvas
# ---------------------------------------------------------------------------
class LevelMapCanvasWidget(QWidget):
    mapChanged = Signal()
    mapStrokeFinished = Signal(str)
    tilePicked = Signal(int)
    hoverTileChanged = Signal(int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project: Optional[KinoPixelProject] = None
        self.selected_tile: int = 1
        self.selected_ai: int = 0   # AI archetype for Place Entity tool
        self.tool: str = "brush"  # brush | eraser | rect | eyedropper | spawn | enemy
        self.show_collision: bool = True
        self.show_viewport: bool = True
        self.zoom: int = 3  # 3 -> 24px per 8x8 tile
        self.theme_name: str = "Dark"

        self._dragging: bool = False
        self._right_erase: bool = False
        self._rect_start: Optional[Tuple[int, int]] = None
        self._hover_tile: Optional[Tuple[int, int]] = None
        self._modified: bool = False
        self.setMouseTracking(True)

    def set_project(self, proj: KinoPixelProject) -> None:
        self.project = proj
        self._sync_size()
        self.update()

    def _sync_size(self) -> None:
        if not self.project:
            return
        ts = 8 * self.zoom
        self.setMinimumSize(self.project.level.width * ts + 2, self.project.level.height * ts + 2)
        self.resize(self.project.level.width * ts + 2, self.project.level.height * ts + 2)

    def _pos_to_tile(self, pos: QPointF) -> Optional[Tuple[int, int]]:
        if not self.project:
            return None
        ts = 8 * self.zoom
        tx = int(pos.x() // ts)
        ty = int(pos.y() // ts)
        if 0 <= tx < self.project.level.width and 0 <= ty < self.project.level.height:
            return tx, ty
        return None

    def _apply_at(self, tx: int, ty: int, erase: bool) -> None:
        assert self.project is not None
        lvl = self.project.level
        if not erase and self.tool == "spawn":
            lvl.spawn_x = tx
            lvl.spawn_y = ty
            self._modified = True
            self.mapChanged.emit()
            return
        if not erase and self.tool == "enemy":
            from .models import EntityPlacement
            # Remove existing enemy at same tile, or place new one
            for i, e in enumerate(lvl.entities):
                if abs(e.tile_x - tx) <= 1 and abs(e.tile_y - ty) <= 1:
                    lvl.entities.pop(i)
                    self._modified = True
                    self.mapChanged.emit()
                    return
            if len(lvl.entities) < 16:
                sp_idx = 1 if len(self.project.sprites) > 1 else 0
                if self.selected_ai == 3:  # Boss
                    boss_i = next((i for i, s in enumerate(self.project.sprites) if s.width >= 32), sp_idx)
                    lvl.entities.append(EntityPlacement(kind="boss", ai_type=3, sprite_index=boss_i, tile_x=tx, tile_y=ty, patrol_range=5, speed=1, hp=12, phase2_hp=6))
                elif self.selected_ai == 5:  # Friendly NPC
                    lvl.entities.append(EntityPlacement(kind="npc", ai_type=5, sprite_index=sp_idx, tile_x=tx, tile_y=ty, patrol_range=0, speed=1, hp=9))
                else:
                    lvl.entities.append(EntityPlacement(kind="enemy", ai_type=self.selected_ai, sprite_index=sp_idx, tile_x=tx, tile_y=ty, patrol_range=3, speed=1, hp=2))
                self._modified = True
                self.mapChanged.emit()
            return
        val = 0 if (erase or self.tool == "eraser") else self.selected_tile
        if lvl.get_tile(tx, ty) != val:
            lvl.set_tile(tx, ty, val)
            self._modified = True
            self.mapChanged.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        hit = self._pos_to_tile(event.position())
        if hit is None or self.project is None:
            return
        tx, ty = hit
        self._modified = False
        self._right_erase = event.button() == Qt.MouseButton.RightButton
        if not self._right_erase and self.tool == "eyedropper":
            self.tilePicked.emit(self.project.level.get_tile(tx, ty))
            return
        if not self._right_erase and self.tool == "rect":
            self._dragging = True
            self._rect_start = (tx, ty)
            self.update()
            return
        self._dragging = True
        self._apply_at(tx, ty, self._right_erase)
        if self.tool in ("spawn", "enemy"):
            self._dragging = False
            if self._modified:
                self.mapStrokeFinished.emit("Place Entity" if self.tool == "enemy" else "Move Spawn")
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        hit = self._pos_to_tile(event.position())
        self._hover_tile = hit
        if hit:
            self.hoverTileChanged.emit(hit[0], hit[1])
            if self._dragging and self.tool not in ("rect", "spawn", "enemy"):
                self._apply_at(hit[0], hit[1], self._right_erase)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._dragging or self.project is None:
            return
        self._dragging = False
        if not self._right_erase and self.tool == "rect" and self._rect_start and self._hover_tile:
            x0, y0 = self._rect_start
            x1, y1 = self._hover_tile
            for yy in range(min(y0, y1), max(y0, y1) + 1):
                for xx in range(min(x0, x1), max(x0, x1) + 1):
                    self.project.level.set_tile(xx, yy, self.selected_tile)
                    self._modified = True
            self.mapChanged.emit()
        self._rect_start = None
        if self._modified:
            self.mapStrokeFinished.emit("Edit Level Map")
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        pal = get_palette(self.theme_name)
        p.fillRect(self.rect(), QColor(pal["bg_canvas"]))
        if not self.project:
            p.end()
            return

        lvl = self.project.level
        ts = 8 * self.zoom
        p.fillRect(QRect(0, 0, lvl.width * ts, lvl.height * ts), QColor(self.project.bg_color_hex))

        # Pre-render tile pixmaps
        tile_pms: List[QPixmap] = []
        for t in self.project.tiles:
            cols = self.project.get_palette_colors(t.palette_index)
            tile_pms.append(render_grid_pixmap(t.pixels, cols, scale=self.zoom, transparent_zero=True))

        # Draw cells
        for ty in range(lvl.height):
            for tx in range(lvl.width):
                ti = lvl.get_tile(tx, ty)
                r = QRect(tx * ts, ty * ts, ts, ts)
                if 0 < ti < len(tile_pms):
                    p.drawPixmap(r.topLeft(), tile_pms[ti])
                if self.show_collision and 0 < ti < len(self.project.tiles):
                    tt = self.project.tiles[ti].tile_type
                    col_hex = TILE_TYPE_COLORS.get(tt, "#00000000")
                    if col_hex != "#00000000":
                        p.fillRect(r, QColor(col_hex))

        # Draw faint tile grid
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        for tx in range(lvl.width + 1):
            p.drawLine(tx * ts, 0, tx * ts, lvl.height * ts)
        for ty in range(lvl.height + 1):
            p.drawLine(0, ty * ts, lvl.width * ts, ty * ts)

        # Draw Hero Spawn marker
        if self.project.sprites and self.project.sprites[0].frames:
            hero_pm = render_grid_pixmap(
                self.project.sprites[0].frames[0],
                self.project.get_palette_colors(self.project.sprites[0].palette_index),
                scale=self.zoom,
            )
            p.drawPixmap(lvl.spawn_x * ts, lvl.spawn_y * ts, hero_pm)
        sp_r = QRect(lvl.spawn_x * ts, lvl.spawn_y * ts, ts * 2, ts * 2)
        p.setPen(QPen(QColor("#34D399"), 2))
        p.drawRect(sp_r)
        p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        p.setPen(QColor("#34D399"))
        p.drawText(sp_r.adjusted(2, -12, 20, 0), Qt.AlignmentFlag.AlignLeft, "SPAWN")

        # Draw Placed Enemies + patrol bounds (supports 16x16 & 32x32 bosses!)
        for en in lvl.entities:
            sp_idx = en.sprite_index if en.sprite_index < len(self.project.sprites) else 0
            sw_tiles, sh_tiles = 2, 2
            if sp_idx < len(self.project.sprites) and self.project.sprites[sp_idx].frames:
                sp = self.project.sprites[sp_idx]
                sw_tiles, sh_tiles = max(2, sp.width // 8), max(2, sp.height // 8)
                epm = render_grid_pixmap(
                    sp.frames[0],
                    self.project.get_palette_colors(sp.palette_index),
                    scale=self.zoom,
                )
                p.drawPixmap(en.tile_x * ts, en.tile_y * ts, epm)
            p.setPen(QPen(QColor("#F43F5E"), 1.5, Qt.PenStyle.DashLine))
            p.drawLine(
                max(0, (en.tile_x - en.patrol_range) * ts),
                en.tile_y * ts + ts,
                min(lvl.width * ts, (en.tile_x + en.patrol_range + sw_tiles) * ts),
                en.tile_y * ts + ts,
            )
            p.setPen(QPen(QColor("#F59E0B") if en.ai_type == 3 else QColor("#F43F5E"), 2))
            p.drawRect(en.tile_x * ts, en.tile_y * ts, ts * sw_tiles, ts * sh_tiles)

        # Draw Linked Room Doors
        for dr in lvl.doors:
            dr_r = QRect(dr.tile_x * ts, dr.tile_y * ts, ts, ts)
            p.setPen(QPen(QColor("#22D3EE"), 2))
            p.drawRect(dr_r)
            p.setFont(QFont("Segoe UI", 6.5, QFont.Weight.Bold))
            p.setPen(QColor("#22D3EE"))
            p.drawText(dr_r.adjusted(-4, -12, 24, 0), Qt.AlignmentFlag.AlignLeft, f"→R{dr.target_room + 1}")

        # Draw Hardware Viewport Guide (240x160 GBA or 160x144 GB/GBC)
        if self.show_viewport:
            prof = self.project.profile()
            vw, vh = int(prof["width"]) * self.zoom, int(prof["height"]) * self.zoom
            p.setPen(QPen(QColor("#F59E0B"), 2, Qt.PenStyle.DashLine))
            p.drawRect(1, 1, vw, vh)
            p.setPen(QColor("#F59E0B"))
            p.drawText(6, 15, f"{self.project.target_system} Screen ({prof['width']}x{prof['height']})")

        # Rect fill preview
        if self._dragging and self.tool == "rect" and self._rect_start and self._hover_tile:
            x0, y0 = self._rect_start
            x1, y1 = self._hover_tile
            rx = min(x0, x1) * ts
            ry = min(y0, y1) * ts
            rw = (abs(x1 - x0) + 1) * ts
            rh = (abs(y1 - y0) + 1) * ts
            p.fillRect(QRect(rx, ry, rw, rh), QColor(139, 92, 246, 90))
            p.setPen(QPen(QColor("#A78BFA"), 2))
            p.drawRect(rx, ry, rw, rh)
        elif self._hover_tile:
            hx, hy = self._hover_tile
            p.setPen(QPen(QColor("#A78BFA"), 2))
            p.drawRect(hx * ts, hy * ts, ts, ts)
        p.end()


# ---------------------------------------------------------------------------
# 4. Interactive Visual GBA / GB Handheld Button-Wiring Diagram
# ---------------------------------------------------------------------------
class HandheldDiagramWidget(QWidget):
    buttonClicked = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project: Optional[KinoPixelProject] = None
        self.selected_button: Optional[str] = None
        self._hit_rects: Dict[str, QRectF] = {}
        self.setMinimumSize(360, 260)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_project(self, proj: KinoPixelProject) -> None:
        self.project = proj
        self.update()

    def _wired_labels(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if not self.project:
            return out
        for r in self.project.button_rules:
            if r.enabled and r.button not in out:
                lbl = ACTION_NAMES.get(r.action, "Action").split(" (")[0]
                out[r.button] = lbl
        return out

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pt = event.position()
        for btn, rect in self._hit_rects.items():
            if rect.contains(pt):
                self.selected_button = btn if self.selected_button != btn else None
                self.buttonClicked.emit(self.selected_button or "")
                self.update()
                return
        self.selected_button = None
        self.buttonClicked.emit("")
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        p.fillRect(self.rect(), QColor("#12151C"))

        is_gba = (self.project.target_system == "GBA") if self.project else True
        wired = self._wired_labels()
        self._hit_rects.clear()

        # Sleek KinoSuite Handheld Shell
        bw = min(w - 28, 430.0)
        bh = min(h - 36, 230.0)
        bx = (w - bw) / 2.0
        by = (h - bh) / 2.0 + 6

        # Shoulder L & R bumpers (for GBA)
        if is_gba:
            r_l = QRectF(bx + 18, by - 14, 72, 20)
            r_r = QRectF(bx + bw - 90, by - 14, 72, 20)
            self._hit_rects["L"] = r_l
            self._hit_rects["R"] = r_r
            for name, rr in (("L", r_l), ("R", r_r)):
                active = name == self.selected_button
                has_w = name in wired
                p.setBrush(QColor("#3A256E") if active else (QColor("#262D42") if has_w else QColor("#1C2130")))
                p.setPen(QPen(QColor("#A78BFA") if (active or has_w) else QColor("#384359"), 1.6))
                p.drawRoundedRect(rr, 7, 7)
                p.setPen(QColor("#FFFFFF") if (active or has_w) else QColor("#8D99AE"))
                p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                txt = f"{name} · {wired[name][:8]}" if has_w else name
                p.drawText(rr, Qt.AlignmentFlag.AlignCenter, txt)

        # Console Body
        grad = QLinearGradient(bx, by, bx, by + bh)
        grad.setColorAt(0.0, QColor("#22283A"))
        grad.setColorAt(1.0, QColor("#171B28"))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor("#434E6B"), 2.0))
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 24, 24)

        # Center LCD Screen Bezel
        sw, sh = bw * 0.44, bh * 0.64
        sx, sy = bx + (bw - sw) / 2.0, by + 18
        p.setBrush(QColor("#0B0E14"))
        p.setPen(QPen(QColor("#2F3950"), 1.5))
        p.drawRoundedRect(QRectF(sx, sy, sw, sh), 10, 10)
        # Inner screen preview info
        p.setBrush(QColor("#141C2B") if is_gba else QColor("#233A22"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(sx + 10, sy + 10, sw - 20, sh - 26), 4, 4)
        p.setPen(QColor("#A78BFA"))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        target_lbl = self.project.target_system if self.project else "GBA"
        p.drawText(QRectF(sx + 10, sy + 14, sw - 20, 22), Qt.AlignmentFlag.AlignCenter, f"KINOPIXEL · {target_lbl}")
        p.setPen(QColor("#94A3B8"))
        p.setFont(QFont("Segoe UI", 7.5))
        sel_txt = f"Filter: [{self.selected_button}]" if self.selected_button else "Click any button\nto inspect / wire!"
        p.drawText(QRectF(sx + 12, sy + 38, sw - 24, sh - 54), Qt.AlignmentFlag.AlignCenter, sel_txt)

        # D-Pad (Left side)
        dcx, dcy = bx + bw * 0.145, by + bh * 0.46
        arm = 24.0
        dpad_defs = [
            ("UP", QRectF(dcx - arm / 2, dcy - arm * 1.45, arm, arm)),
            ("DOWN", QRectF(dcx - arm / 2, dcy + arm * 0.45, arm, arm)),
            ("LEFT", QRectF(dcx - arm * 1.45, dcy - arm / 2, arm, arm)),
            ("RIGHT", QRectF(dcx + arm * 0.45, dcy - arm / 2, arm, arm)),
        ]
        p.setBrush(QColor("#111520"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(dcx - arm / 2, dcy - arm / 2, arm, arm))
        for name, rr in dpad_defs:
            self._hit_rects[name] = rr
            active = name == self.selected_button
            has_w = name in wired
            p.setBrush(QColor("#6D28D9") if active else (QColor("#2E2554") if has_w else QColor("#151924")))
            p.setPen(QPen(QColor("#C4B5FD") if active else (QColor("#8B5CF6") if has_w else QColor("#3A455E")), 1.6))
            p.drawRoundedRect(rr, 4, 4)
            p.setPen(QColor("#FFFFFF") if (active or has_w) else QColor("#8D99AE"))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            sym = {"UP": "▲", "DOWN": "▼", "LEFT": "◀", "RIGHT": "▶"}[name]
            p.drawText(rr, Qt.AlignmentFlag.AlignCenter, sym)

        # A & B Action Buttons (Right side)
        b_rect = QRectF(bx + bw * 0.77, by + bh * 0.44, 34, 34)
        a_rect = QRectF(bx + bw * 0.865, by + bh * 0.30, 34, 34)
        for name, rr, base_col in (("B", b_rect, "#F59E0B"), ("A", a_rect, "#34D399")):
            self._hit_rects[name] = rr
            active = name == self.selected_button
            has_w = name in wired
            p.setBrush(QColor("#8B5CF6") if active else (QColor(base_col) if has_w else QColor("#1D2333")))
            p.setPen(QPen(QColor("#FFFFFF") if active else QColor(base_col), 2.0))
            p.drawEllipse(rr)
            p.setPen(QColor("#081018") if (has_w and not active) else QColor("#FFFFFF"))
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            p.drawText(rr, Qt.AlignmentFlag.AlignCenter, name)
            if has_w:
                p.setPen(QColor("#E6EAF2"))
                p.setFont(QFont("Segoe UI", 7))
                p.drawText(QRectF(rr.x() - 18, rr.bottom() + 2, rr.width() + 36, 16), Qt.AlignmentFlag.AlignCenter, wired[name][:10])

        # SELECT & START pills (Bottom center)
        sel_r = QRectF(bx + bw * 0.35, by + bh - 34, 62, 18)
        sta_r = QRectF(bx + bw * 0.51, by + bh - 34, 62, 18)
        for name, rr in (("SELECT", sel_r), ("START", sta_r)):
            self._hit_rects[name] = rr
            active = name == self.selected_button
            has_w = name in wired
            p.setBrush(QColor("#6D28D9") if active else (QColor("#2A224A") if has_w else QColor("#151924")))
            p.setPen(QPen(QColor("#A78BFA") if (active or has_w) else QColor("#3A455E"), 1.4))
            p.drawRoundedRect(rr, 8, 8)
            p.setPen(QColor("#FFFFFF") if (active or has_w) else QColor("#8D99AE"))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(rr, Qt.AlignmentFlag.AlignCenter, name)

        p.end()


# ---------------------------------------------------------------------------
# 5. Live Chiptune Waveform Visualizer
# ---------------------------------------------------------------------------
class SfxWaveformWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.samples: Optional[np.ndarray] = None
        self.setMinimumHeight(110)
        self.setMaximumHeight(150)

    def set_samples(self, samples: np.ndarray) -> None:
        self.samples = samples
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        p.fillRect(r, QColor("#0E1118"))
        p.setPen(QPen(QColor("#2A3242"), 1))
        p.drawRoundedRect(r.adjusted(0, 0, -1, -1), 6, 6)

        mid_y = r.height() / 2.0
        p.setPen(QPen(QColor("#242D40"), 1, Qt.PenStyle.DashLine))
        p.drawLine(4, int(mid_y), r.width() - 4, int(mid_y))

        if self.samples is not None and len(self.samples) > 4:
            w = max(10, r.width() - 12)
            step = max(1, len(self.samples) // w)
            p.setPen(QPen(QColor("#A78BFA"), 1.5))
            pts = []
            for x in range(w):
                idx = min(len(self.samples) - 1, x * step)
                val = float(self.samples[idx])
                y = mid_y - val * (r.height() * 1.15)
                pts.append(QPointF(6 + x, max(6.0, min(r.height() - 6.0, y))))
            p.drawPolyline(QPolygonF(pts))
        p.end()


# ---------------------------------------------------------------------------
# 6. Live Embedded 60fps Handheld Playtest Screen Widget
# ---------------------------------------------------------------------------
class PlaytestScreenWidget(QWidget):
    keysChanged = Signal(set)

    KEY_MAP = {
        Qt.Key.Key_Left: "LEFT",
        Qt.Key.Key_A: "LEFT",
        Qt.Key.Key_Right: "RIGHT",
        Qt.Key.Key_D: "RIGHT",
        Qt.Key.Key_Up: "UP",
        Qt.Key.Key_W: "UP",
        Qt.Key.Key_Down: "DOWN",
        Qt.Key.Key_S: "DOWN",
        Qt.Key.Key_Z: "A",
        Qt.Key.Key_Space: "A",
        Qt.Key.Key_J: "A",
        Qt.Key.Key_X: "B",
        Qt.Key.Key_Shift: "B",
        Qt.Key.Key_K: "B",
        Qt.Key.Key_Q: "L",
        Qt.Key.Key_E: "R",
        Qt.Key.Key_Return: "START",
        Qt.Key.Key_Enter: "START",
        Qt.Key.Key_Tab: "SELECT",
        Qt.Key.Key_Backspace: "SELECT",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._frame_img: Optional[QImage] = None
        self.hud_info: Tuple[int, int, int, bool, bool] = (5, 0, 0, False, False)
        self.extra_hud: Tuple[int, int, str, str, int] = (0, 0, "", "", 0)  # room_idx, boss_hp, banner, dialogue, var0
        self.minimap_data: Tuple[List[Tuple[int, int, int]], int] = ([], 0)  # [(idx, wx, wy), ...], active_idx
        self.script_mode: bool = False
        self.lcd_grid: bool = True
        self.pressed_keys: Set[str] = set()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(480, 320)

    def set_frame(
        self, rgb: np.ndarray, hp: int, coins: int, score: int, paused: bool, won: bool,
        room_idx: int = 0, boss_hp: int = 0, banner: str = "", dialogue: str = "",
        var0: int = 0, minimap_rooms: Optional[List[Tuple[int, int, int]]] = None,
        script_mode: bool = False,
    ) -> None:
        h, w, _ = rgb.shape
        contiguous = np.ascontiguousarray(rgb)
        self._frame_img = QImage(contiguous.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        self.hud_info = (hp, coins, score, paused, won)
        self.extra_hud = (room_idx, boss_hp, banner, dialogue, var0)
        self.minimap_data = (minimap_rooms or [], room_idx)
        self.script_mode = script_mode
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        btn = self.KEY_MAP.get(event.key())
        if btn:
            self.pressed_keys.add(btn)
            self.keysChanged.emit(set(self.pressed_keys))
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        btn = self.KEY_MAP.get(event.key())
        if btn:
            self.pressed_keys.discard(btn)
            self.keysChanged.emit(set(self.pressed_keys))
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0B0E14"))
        if self._frame_img is None:
            p.end()
            return

        iw, ih = self._frame_img.width(), self._frame_img.height()
        scale = max(1, min((self.width() - 16) // iw, (self.height() - 16) // ih))
        dw, dh = iw * scale, ih * scale
        ox = (self.width() - dw) // 2
        oy = (self.height() - dh) // 2
        dst = QRect(ox, oy, dw, dh)

        # Bezel shadow & crisp integer blit
        p.setPen(QPen(QColor("#8B5CF6") if self.hasFocus() else QColor("#2A3242"), 2))
        p.drawRect(dst.adjusted(-2, -2, 2, 2))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawImage(dst, self._frame_img)

        # Subtle LCD dot-matrix grid overlay
        if self.lcd_grid and scale >= 2:
            p.setPen(QPen(QColor(0, 0, 0, 38), 1))
            for y in range(oy, oy + dh, scale):
                p.drawLine(ox, y, ox + dw, y)
            if scale >= 3:
                for x in range(ox, ox + dw, scale):
                    p.drawLine(x, oy, x, oy + dh)

        # Crisp HUD overlay matching hardware BG1 HUD (skipped in KinoScript mode since script owns BG1!)
        if self.script_mode:
            room_idx, boss_hp, banner, dialogue, var0 = self.extra_hud
            if banner:
                p.setFont(QFont("Consolas", max(8, 3 * scale), QFont.Weight.Bold))
                p.setPen(QColor("#F43F5E"))
                p.drawText(ox + 8, oy + dh - 8, banner)
            p.end()
            return
        hp, coins, score, paused, won = self.hud_info
        room_idx, boss_hp, banner, dialogue, var0 = self.extra_hud
        p.setFont(QFont("Consolas", max(9, 4 * scale), QFont.Weight.Bold))
        p.setPen(QColor("#F43F5E"))
        p.drawText(ox + 8, oy + 4 * scale + 10, "♥" * max(0, hp))
        p.setPen(QColor("#FDE047"))
        p.drawText(ox + 92, oy + 4 * scale + 10, f"★{coins:02d}  R{room_idx + 1}  M{var0:02d}")
        p.setPen(QColor("#F8FAFC"))
        p.drawText(ox + dw - 125, oy + 4 * scale + 10, f"PTS {score:04d}")

        if boss_hp > 0:
            p.setPen(QColor("#34D399"))
            p.drawText(ox + dw // 2 - 48, oy + 4 * scale + 10, f"BOSS {'█' * min(8, (boss_hp + 1) // 2)}")
        elif banner:
            p.setPen(QColor("#38BDF8"))
            p.drawText(ox + dw // 2 - 64, oy + 4 * scale + 10, banner)

        if dialogue:
            box = QRect(ox + 16, oy + dh - 64, dw - 32, 52)
            p.fillRect(box, QColor(13, 19, 34, 235))
            p.setPen(QPen(QColor("#38BDF8"), 2))
            p.drawRect(box)
            p.setPen(QColor("#F8FAFC"))
            p.setFont(QFont("Consolas", max(8, 3 * scale), QFont.Weight.Bold))
            p.drawText(box.adjusted(8, 6, -8, -6), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, f"{dialogue}\n[Press A / Z to continue]")

        if won:
            p.fillRect(QRect(ox + dw // 6, oy + dh // 2 - 26, dw * 2 // 3, 52), QColor(14, 17, 26, 220))
            p.setPen(QPen(QColor("#34D399"), 2))
            p.drawRect(QRect(ox + dw // 6, oy + dh // 2 - 26, dw * 2 // 3, 52))
            p.setPen(QColor("#34D399"))
            p.drawText(dst, Qt.AlignmentFlag.AlignCenter, "STAGE CLEAR!\nPress START / A to Replay")
        elif paused:
            mbox = QRect(ox + dw // 5, oy + dh // 5, dw * 3 // 5, dh * 3 // 5)
            p.fillRect(mbox, QColor(13, 19, 34, 235))
            p.setPen(QPen(QColor("#A78BFA"), 2))
            p.drawRect(mbox)
            p.setPen(QColor("#F59E0B"))
            p.drawText(QRect(mbox.x(), mbox.y() + 6, mbox.width(), 22), Qt.AlignmentFlag.AlignCenter, "PAUSED · WORLD MAP")
            mrooms, cur_rm = self.minimap_data
            cell_w = max(10, (mbox.width() - 24) // 16)
            cell_h = max(10, (mbox.height() - 40) // 8)
            for ri, wx, wy in mrooms:
                rr = QRect(mbox.x() + 12 + (wx & 15) * cell_w, mbox.y() + 30 + (wy & 7) * cell_h, cell_w - 2, cell_h - 2)
                p.fillRect(rr, QColor("#34D399") if ri == cur_rm else QColor("#FDE047"))
                p.setPen(QColor("#0D1322"))
                p.drawRect(rr)

        p.end()
