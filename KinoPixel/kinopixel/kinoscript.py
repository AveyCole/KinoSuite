"""KinoScript — Native Python-Syntax to ARM7TDMI GBA Compiler + 60 FPS Live VM.

Allows KinoPixel users to write arbitrary, unrestricted game logic (Advance Wars turn-based
tactics, Legacy of Goku RPGs, Astro Boy action shooters, Metroidvania engines, puzzle games,
menus, AI opponents, custom physics, anything!) that:
  1. Compiles directly to native 32-bit ARM7TDMI machine code inside a bootable .gba ROM
     with ZERO external toolchain.
  2. Executes 1:1 in KinoPixel's live 60 FPS Playtester with full 128-OAM sprites, BG0/BG1/BG2
     tilemaps, crisp BG1 text/UI boxes, 5-voice audio, and 32 KB SRAM.
"""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .arm_asm import (
    ArmAssembler,
    LR,
    PC,
    R0, R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12,
    SP,
)
from .models import (
    BUTTON_BITS,
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
)

# Built-in hardware constants available automatically in every KinoScript
KS_CONSTANTS: Dict[str, int] = {
    "True": 1,
    "False": 0,
    "BTN_A": BUTTON_BITS["A"],
    "BTN_B": BUTTON_BITS["B"],
    "BTN_SELECT": BUTTON_BITS["SELECT"],
    "BTN_START": BUTTON_BITS["START"],
    "BTN_RIGHT": BUTTON_BITS["RIGHT"],
    "BTN_LEFT": BUTTON_BITS["LEFT"],
    "BTN_UP": BUTTON_BITS["UP"],
    "BTN_DOWN": BUTTON_BITS["DOWN"],
    "BTN_R": BUTTON_BITS["R"],
    "BTN_L": BUTTON_BITS["L"],
    "TILE_EMPTY": TILE_EMPTY,
    "TILE_SOLID": TILE_SOLID,
    "TILE_ONEWAY": TILE_ONEWAY,
    "TILE_HAZARD": TILE_HAZARD,
    "TILE_COIN": TILE_COIN,
    "TILE_GOAL": TILE_GOAL,
    "TILE_BOUNCE": TILE_BOUNCE,
    "TILE_BREAKABLE": TILE_BREAKABLE,
    "TILE_DOOR": TILE_DOOR,
    "TILE_SAVE": TILE_SAVE,
    "TILE_UPGRADE": TILE_UPGRADE,
    "TILE_TERMINAL": TILE_TERMINAL,
    "TILE_SLOPE_L": TILE_SLOPE_L,
    "TILE_SLOPE_R": TILE_SLOPE_R,
    "TILE_WATER": TILE_WATER,
    "TILE_LADDER": TILE_LADDER,
    "TILE_SWITCH": TILE_SWITCH,
}

# Built-in API function signatures (name -> arg count; draw_text takes string literal as arg 2)
KS_BUILTINS: Dict[str, int] = {
    "key_held": 1,
    "key_pressed": 1,
    "key_released": 1,
    "frame_count": 0,
    "load_room": 1,
    "room_width": 0,
    "room_height": 0,
    "get_tile": 2,
    "get_tile_type": 2,
    "set_tile": 3,
    "set_ui_tile": 4,
    "set_bg2_tile": 4,
    "scroll_bg": 3,
    "draw_text": 3,
    "draw_num": 4,
    "draw_box": 4,
    "draw_window": 4,
    "draw_bar": 5,
    "set_fade": 1,
    "clear_ui_rect": 4,
    "clear_ui": 0,
    "set_sprite": 7,
    "hide_sprite": 1,
    "hide_all_sprites": 0,
    "play_sfx": 1,
    "play_dma": 0,
    "bgm_enable": 1,
    "sram_write": 2,
    "sram_read": 1,
    "abs": 1,
    "min": 2,
    "max": 2,
    "clamp": 3,
    "rand": 0,
}

# EWRAM base address reserved for KinoScript globals & arrays (240 KB available: 0x02004000..0x0203FFFF)
KS_RAM_BASE = 0x02004000


class KinoScriptError(Exception):
    """Compile-time error with line number for KinoScript."""

    def __init__(self, message: str, line: int = 0) -> None:
        self.line = line
        super().__init__(f"Line {line}: {message}" if line > 0 else message)


@dataclass
class _GlobalVar:
    name: str
    offset: int          # byte offset from R9 (KS_RAM_BASE)
    is_array: bool
    length: int          # 1 for scalar, N for array
    init_vals: List[int] # initial 32-bit values


def _eval_const_int(node: ast.AST, consts: Dict[str, int]) -> int:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, bool)):
        return int(node.value)
    if isinstance(node, ast.Name) and node.id in consts:
        return int(consts[node.id])
    if isinstance(node, ast.UnaryOp):
        v = _eval_const_int(node.operand, consts)
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.UAdd):
            return v
        if isinstance(node.op, ast.Invert):
            return ~v
    if isinstance(node, ast.BinOp):
        a = _eval_const_int(node.left, consts)
        b = _eval_const_int(node.right, consts)
        if isinstance(node.op, ast.Add): return a + b
        if isinstance(node.op, ast.Sub): return a - b
        if isinstance(node.op, ast.Mult): return a * b
        if isinstance(node.op, (ast.FloorDiv, ast.Div)) and b != 0: return int(a // b)
        if isinstance(node.op, ast.Mod) and b != 0: return int(a % b)
        if isinstance(node.op, ast.LShift): return a << b
        if isinstance(node.op, ast.RShift): return a >> b
        if isinstance(node.op, ast.BitOr): return a | b
        if isinstance(node.op, ast.BitAnd): return a & b
        if isinstance(node.op, ast.BitXor): return a ^ b
    raise KinoScriptError("Expected constant integer expression at module level", getattr(node, "lineno", 0))


# ---------------------------------------------------------------------------
# Native ARM7TDMI Compiler for KinoScript
# ---------------------------------------------------------------------------
class KinoScriptArmCompiler:
    """Compiles a Python-syntax KinoScript directly into ARM7TDMI machine code on an ArmAssembler."""

    def __init__(self, source: str, font_index: Dict[str, int]) -> None:
        self.source = source
        self.font_index = font_index
        self.globals: Dict[str, _GlobalVar] = {}
        self.consts: Dict[str, int] = dict(KS_CONSTANTS)
        self.functions: Dict[str, ast.FunctionDef] = {}
        self.strings: List[Tuple[str, bytes]] = []  # (label, encoded FONT_INDEX bytes + 0xFF terminator)
        self._str_cache: Dict[str, str] = {}
        self._lbl_counter: int = 0
        self._loop_stack: List[Tuple[str, str]] = []  # (continue_lbl, break_lbl)
        self._cur_fn: str = ""
        self._cur_params: Dict[str, int] = {}   # param_name -> positive offset from FP (R8)
        self._cur_locals: Dict[str, int] = {}   # local_name -> negative offset from FP (R8)
        self._cur_epilogue: str = ""
        self.ram_bytes_used: int = 0

        try:
            self.tree = ast.parse(source)
        except SyntaxError as exc:
            raise KinoScriptError(f"Syntax error: {exc.msg}", exc.lineno or 0) from exc

        self._collect_top_level()

    def _new_label(self, prefix: str) -> str:
        self._lbl_counter += 1
        return f"ks_{prefix}_{self._lbl_counter}"

    def _intern_string(self, text: str) -> str:
        clean = text.upper()
        if clean in self._str_cache:
            return self._str_cache[clean]
        lbl = self._new_label("str")
        data = bytearray()
        for ch in clean[:60]:
            data.append(self.font_index.get(ch, 0))
        data.append(0xFF)  # terminator
        self.strings.append((lbl, bytes(data)))
        self._str_cache[clean] = lbl
        return lbl

    def _collect_top_level(self) -> None:
        next_off = 0
        for stmt in self.tree.body:
            if isinstance(stmt, ast.FunctionDef):
                if stmt.name in KS_BUILTINS:
                    raise KinoScriptError(f"Cannot redefine built-in '{stmt.name}'", stmt.lineno)
                self.functions[stmt.name] = stmt
            elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                name = stmt.targets[0].id
                if name in KS_BUILTINS:
                    raise KinoScriptError(f"Cannot use built-in name '{name}' as variable", stmt.lineno)
                val = stmt.value
                # Array declaration: [0] * N  OR  [1, 2, 3, ...]
                if isinstance(val, ast.BinOp) and isinstance(val.op, ast.Mult) and isinstance(val.left, ast.List) and len(val.left.elts) == 1:
                    fill_v = _eval_const_int(val.left.elts[0], self.consts)
                    n = _eval_const_int(val.right, self.consts)
                    if n <= 0 or n > 8192:
                        raise KinoScriptError(f"Array '{name}' size {n} out of range (1..8192)", stmt.lineno)
                    self.globals[name] = _GlobalVar(name, next_off, True, n, [fill_v] * n)
                    next_off += n * 4
                elif isinstance(val, ast.List):
                    vals = [_eval_const_int(e, self.consts) for e in val.elts]
                    if not vals:
                        raise KinoScriptError(f"Array '{name}' cannot be empty", stmt.lineno)
                    self.globals[name] = _GlobalVar(name, next_off, True, len(vals), vals)
                    next_off += len(vals) * 4
                else:
                    v = _eval_const_int(val, self.consts)
                    self.globals[name] = _GlobalVar(name, next_off, False, 1, [v])
                    self.consts[name] = v
                    next_off += 4
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                # Module docstring — allowed!
                continue
            elif isinstance(stmt, ast.Pass):
                continue
            else:
                raise KinoScriptError(
                    "Top-level statements must be variable/array declarations or 'def' functions",
                    getattr(stmt, "lineno", 0),
                )
        self.ram_bytes_used = next_off
        if self.ram_bytes_used > 200 * 1024:
            raise KinoScriptError("Total script RAM exceeds 200 KB EWRAM budget")
        if "on_frame" not in self.functions:
            raise KinoScriptError("KinoScript must define 'def on_frame():'", 1)

    def _maybe_flush_pool(self, asm: ArmAssembler) -> None:
        if not asm._pending_pool:
            return
        oldest = asm._pending_pool[0][0]
        if (asm.offset - oldest) >= 1400 or len(asm._pending_pool) >= 48:
            skip = self._new_label("poolskip")
            asm.b(skip)
            asm.pool()
            asm.label(skip)

    def _emit_load_global_addr(self, asm: ArmAssembler, rd: int, byte_off: int) -> None:
        if byte_off == 0:
            asm.mov_reg(rd, R9)
        else:
            asm.ldr_lit(rd, byte_off)
            asm.add_reg(rd, R9, rd)

    def _emit_fp_load(self, asm: ArmAssembler, rd: int, fp_off: int) -> None:
        if -4095 <= fp_off <= 4095:
            asm.ldr(rd, R8, fp_off)
        else:
            asm.ldr_lit(R12, fp_off)
            asm.ldr_reg(rd, R8, R12)

    def _emit_fp_store(self, asm: ArmAssembler, rd: int, fp_off: int) -> None:
        if -4095 <= fp_off <= 4095:
            asm.str(rd, R8, fp_off)
        else:
            asm.ldr_lit(R12, fp_off)
            asm.str_reg(rd, R8, R12)

    def emit_code_and_data(self, asm: ArmAssembler) -> None:
        """Emit __ks_init_globals, all user functions, and string/init data tables."""
        # 1. __ks_init_globals: copies initial global values into EWRAM (R9 = KS_RAM_BASE)
        asm.label("ks_init_globals")
        asm.push([R4, R5, LR])
        if self.ram_bytes_used > 0:
            asm.ldr_lit(R0, "ROM_KS_INIT_RAM")
            asm.mov_reg(R1, R9)
            asm.ldr_lit(R2, self.ram_bytes_used // 2)
            asm.bl("copy_halfwords")
        if "on_init" in self.functions:
            asm.bl("ks_fn_on_init")
        asm.pop([R4, R5, PC])
        asm.pool()

        # 2. Emit every user function
        for fn_name, fn_node in self.functions.items():
            self._emit_function(asm, fn_name, fn_node)

        # 3. Emit String Literal Table & Global Initializer Blob
        asm.align(4)
        for lbl, raw in self.strings:
            asm.align(4)
            asm.label(lbl)
            asm.emit_bytes(raw)

        asm.align(4)
        asm.label("ROM_KS_INIT_RAM")
        for gv in self.globals.values():
            for v in gv.init_vals:
                asm.emit32(v & 0xFFFFFFFF)
        if self.ram_bytes_used == 0:
            asm.emit32(0)

    def _collect_locals(self, fn_node: ast.FunctionDef, param_names: Set[str]) -> List[str]:
        found: List[str] = []
        seen: Set[str] = set()

        def visit(node: ast.AST) -> None:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        nm = tgt.id
                        if nm not in param_names and nm not in self.globals and nm not in KS_CONSTANTS and nm not in seen:
                            seen.add(nm)
                            found.append(nm)
            elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                nm = node.target.id
                if nm not in param_names and nm not in self.globals and nm not in KS_CONSTANTS and nm not in seen:
                    seen.add(nm)
                    found.append(nm)
            elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                nm = node.target.id
                if nm not in param_names and nm not in self.globals and nm not in KS_CONSTANTS and nm not in seen:
                    seen.add(nm)
                    found.append(nm)
            for child in ast.iter_child_nodes(node):
                visit(child)

        for st in fn_node.body:
            visit(st)
        return found

    def _emit_function(self, asm: ArmAssembler, fn_name: str, fn_node: ast.FunctionDef) -> None:
        self._cur_fn = fn_name
        self._cur_epilogue = f"ks_ep_{fn_name}"
        params = [a.arg for a in fn_node.args.args]
        argc = len(params)
        self._cur_params = {p: 8 + (argc - 1 - i) * 4 for i, p in enumerate(params)}
        local_names = self._collect_locals(fn_node, set(params))
        self._cur_locals = {nm: -(i + 1) * 4 for i, nm in enumerate(local_names)}

        asm.label(f"ks_fn_{fn_name}")
        asm.push([R8, LR])
        asm.mov_reg(R8, SP)
        nloc = len(local_names)
        if nloc > 0:
            bytes_loc = nloc * 4
            asm.ldr_lit(R0, bytes_loc)
            asm.sub_reg(SP, SP, R0)
            # Zero-clear local slots
            asm.mov_imm(R1, 0)
            for i in range(nloc):
                self._emit_fp_store(asm, R1, -(i + 1) * 4)

        for st in fn_node.body:
            self._emit_stmt(asm, st)
            self._maybe_flush_pool(asm)

        asm.mov_imm(R0, 0)
        asm.label(self._cur_epilogue)
        asm.mov_reg(SP, R8)
        asm.pop([R8, PC])
        asm.pool()

    def _emit_stmt(self, asm: ArmAssembler, node: ast.AST) -> None:
        if isinstance(node, ast.Pass):
            return
        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return
            self._emit_expr(asm, node.value)
            return
        if isinstance(node, ast.Return):
            if node.value is not None:
                self._emit_expr(asm, node.value)
            else:
                asm.mov_imm(R0, 0)
            asm.b(self._cur_epilogue)
            return
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                raise KinoScriptError("Chained assignments not supported", node.lineno)
            self._emit_store_target(asm, node.targets[0], node.value)
            return
        if isinstance(node, ast.AugAssign):
            # Rewrite x op= rhs cleanly using load + op + store
            self._emit_aug_assign(asm, node)
            return
        if isinstance(node, ast.If):
            else_lbl = self._new_label("else")
            end_lbl = self._new_label("endif")
            self._emit_expr(asm, node.test)
            asm.cmp_imm(R0, 0)
            asm.b(else_lbl if node.orelse else end_lbl, "EQ")
            for st in node.body:
                self._emit_stmt(asm, st)
                self._maybe_flush_pool(asm)
            if node.orelse:
                asm.b(end_lbl)
                asm.label(else_lbl)
                for st in node.orelse:
                    self._emit_stmt(asm, st)
                    self._maybe_flush_pool(asm)
            asm.label(end_lbl)
            return
        if isinstance(node, ast.While):
            top_lbl = self._new_label("while")
            end_lbl = self._new_label("endwhile")
            self._loop_stack.append((top_lbl, end_lbl))
            asm.label(top_lbl)
            self._emit_expr(asm, node.test)
            asm.cmp_imm(R0, 0)
            asm.b(end_lbl, "EQ")
            for st in node.body:
                self._emit_stmt(asm, st)
                self._maybe_flush_pool(asm)
            asm.b(top_lbl)
            asm.label(end_lbl)
            self._loop_stack.pop()
            return
        if isinstance(node, ast.For):
            self._emit_for_range(asm, node)
            return
        if isinstance(node, ast.Break):
            if not self._loop_stack:
                raise KinoScriptError("'break' outside loop", node.lineno)
            asm.b(self._loop_stack[-1][1])
            return
        if isinstance(node, ast.Continue):
            if not self._loop_stack:
                raise KinoScriptError("'continue' outside loop", node.lineno)
            asm.b(self._loop_stack[-1][0])
            return
        if isinstance(node, ast.Global):
            return
        raise KinoScriptError(f"Unsupported statement: {type(node).__name__}", getattr(node, "lineno", 0))

    def _emit_for_range(self, asm: ArmAssembler, node: ast.For) -> None:
        if not (isinstance(node.target, ast.Name) and isinstance(node.iter, ast.Call)
                and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range"):
            raise KinoScriptError("'for' loops must use 'for var in range(...):'", node.lineno)
        args = node.iter.args
        if len(args) == 1:
            start_n, stop_n, step_n = ast.Constant(0), args[0], ast.Constant(1)
        elif len(args) == 2:
            start_n, stop_n, step_n = args[0], args[1], ast.Constant(1)
        elif len(args) == 3:
            start_n, stop_n, step_n = args[0], args[1], args[2]
        else:
            raise KinoScriptError("range() expects 1..3 arguments", node.lineno)

        var_name = node.target.id
        # Initialize loop var = start
        self._emit_expr(asm, start_n)
        self._emit_store_var_r0(asm, var_name, node.lineno)

        # Evaluate stop & step once and keep on stack: [SP+4]=stop, [SP+0]=step
        self._emit_expr(asm, stop_n)
        asm.push([R0])
        self._emit_expr(asm, step_n)
        asm.push([R0])

        top_lbl = self._new_label("for_top")
        cont_lbl = self._new_label("for_cont")
        end_lbl = self._new_label("for_end")
        # Wait: inside loop, break must pop 2 words! So use a clean break trampoline!
        brk_lbl = self._new_label("for_brk")
        self._loop_stack.append((cont_lbl, brk_lbl))

        asm.label(top_lbl)
        self._emit_load_var_r0(asm, var_name, node.lineno)  # R0 = i
        asm.ldr(R1, SP, 4)                                  # R1 = stop
        asm.ldr(R2, SP, 0)                                  # R2 = step
        asm.cmp_imm(R2, 0)
        asm.b(f"{top_lbl}_neg", "LT")
        asm.cmp_reg(R0, R1)
        asm.b(end_lbl, "GE")
        asm.b(f"{top_lbl}_body")
        asm.label(f"{top_lbl}_neg")
        asm.cmp_reg(R0, R1)
        asm.b(end_lbl, "LE")
        asm.label(f"{top_lbl}_body")

        for st in node.body:
            self._emit_stmt(asm, st)
            self._maybe_flush_pool(asm)

        asm.label(cont_lbl)
        self._emit_load_var_r0(asm, var_name, node.lineno)
        asm.ldr(R2, SP, 0)
        asm.add_reg(R0, R0, R2)
        self._emit_store_var_r0(asm, var_name, node.lineno)
        asm.b(top_lbl)

        asm.label(brk_lbl)
        asm.label(end_lbl)
        asm.add_imm(SP, SP, 8)
        self._loop_stack.pop()

    def _emit_load_var_r0(self, asm: ArmAssembler, name: str, lineno: int) -> None:
        if name in self._cur_params:
            self._emit_fp_load(asm, R0, self._cur_params[name])
        elif name in self._cur_locals:
            self._emit_fp_load(asm, R0, self._cur_locals[name])
        elif name in self.globals:
            gv = self.globals[name]
            if gv.is_array:
                raise KinoScriptError(f"Array '{name}' must be indexed with []", lineno)
            self._emit_load_global_addr(asm, R1, gv.offset)
            asm.ldr(R0, R1, 0)
        elif name in KS_CONSTANTS:
            asm.ldr_lit(R0, KS_CONSTANTS[name])
        else:
            raise KinoScriptError(f"Undefined variable '{name}'", lineno)

    def _emit_store_var_r0(self, asm: ArmAssembler, name: str, lineno: int) -> None:
        if name in self._cur_params:
            self._emit_fp_store(asm, R0, self._cur_params[name])
        elif name in self._cur_locals:
            self._emit_fp_store(asm, R0, self._cur_locals[name])
        elif name in self.globals:
            gv = self.globals[name]
            if gv.is_array:
                raise KinoScriptError(f"Cannot assign scalar to array '{name}' without index", lineno)
            self._emit_load_global_addr(asm, R1, gv.offset)
            asm.str(R0, R1, 0)
        else:
            raise KinoScriptError(f"Undefined variable '{name}'", lineno)

    def _emit_store_target(self, asm: ArmAssembler, target: ast.AST, value_expr: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self._emit_expr(asm, value_expr)
            self._emit_store_var_r0(asm, target.id, target.lineno)
        elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
            arr_name = target.value.id
            if arr_name not in self.globals or not self.globals[arr_name].is_array:
                raise KinoScriptError(f"'{arr_name}' is not a declared array", target.lineno)
            gv = self.globals[arr_name]
            self._emit_expr(asm, target.slice)
            asm.push([R0])  # save index
            self._emit_expr(asm, value_expr)
            asm.pop([R1])   # R1 = index, R0 = value
            # Safe bounds clamp 0..length-1
            asm.cmp_imm(R1, 0)
            asm.mov_imm(R1, 0, cond="LT")
            asm.ldr_lit(R2, gv.length - 1)
            asm.cmp_reg(R1, R2)
            asm.mov_reg(R1, R2, cond="GT")
            self._emit_load_global_addr(asm, R2, gv.offset)
            asm.str_reg(R0, R2, R1, shift_amt=2)
        else:
            raise KinoScriptError("Unsupported assignment target", getattr(target, "lineno", 0))

    def _emit_aug_assign(self, asm: ArmAssembler, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            self._emit_load_var_r0(asm, node.target.id, node.lineno)
            asm.push([R0])
            self._emit_expr(asm, node.value)
            asm.pop([R1])
            self._emit_binop_r1_r0(asm, node.op, node.lineno)
            self._emit_store_var_r0(asm, node.target.id, node.lineno)
        elif isinstance(node.target, ast.Subscript) and isinstance(node.target.value, ast.Name):
            arr_name = node.target.value.id
            if arr_name not in self.globals or not self.globals[arr_name].is_array:
                raise KinoScriptError(f"'{arr_name}' is not a declared array", node.lineno)
            gv = self.globals[arr_name]
            self._emit_expr(asm, node.target.slice)
            asm.cmp_imm(R0, 0)
            asm.mov_imm(R0, 0, cond="LT")
            asm.ldr_lit(R2, gv.length - 1)
            asm.cmp_reg(R0, R2)
            asm.mov_reg(R0, R2, cond="GT")
            asm.push([R0])  # save clamped index
            self._emit_load_global_addr(asm, R2, gv.offset)
            asm.ldr_reg(R1, R2, R0, shift_amt=2)
            asm.push([R1])  # save old value
            self._emit_expr(asm, node.value)
            asm.pop([R1])   # R1 = old val, R0 = rhs
            self._emit_binop_r1_r0(asm, node.op, node.lineno)
            asm.pop([R1])   # R1 = clamped index
            self._emit_load_global_addr(asm, R2, gv.offset)
            asm.str_reg(R0, R2, R1, shift_amt=2)
        else:
            raise KinoScriptError("Unsupported augmented assignment", node.lineno)

    def _emit_binop_r1_r0(self, asm: ArmAssembler, op: ast.operator, lineno: int) -> None:
        """Compute R0 = R1 <op> R0."""
        if isinstance(op, ast.Add):
            asm.add_reg(R0, R1, R0)
        elif isinstance(op, ast.Sub):
            asm.sub_reg(R0, R1, R0)
        elif isinstance(op, ast.Mult):
            asm.mov_reg(R2, R0)
            asm.mul(R0, R1, R2)
        elif isinstance(op, (ast.FloorDiv, ast.Div)):
            asm.mov_reg(R2, R0)
            asm.mov_reg(R0, R1)
            asm.mov_reg(R1, R2)
            asm.bl("ks_rt_divmod")
        elif isinstance(op, ast.Mod):
            asm.mov_reg(R2, R0)
            asm.mov_reg(R0, R1)
            asm.mov_reg(R1, R2)
            asm.bl("ks_rt_divmod")
            asm.mov_reg(R0, R1)
        elif isinstance(op, ast.BitAnd):
            asm.and_reg(R0, R1, R0)
        elif isinstance(op, ast.BitOr):
            asm.orr_reg(R0, R1, R0)
        elif isinstance(op, ast.BitXor):
            asm.eor_reg(R0, R1, R0)
        elif isinstance(op, ast.LShift):
            asm.mov_reg(R2, R0)
            asm.mov_reg(R0, R1)
            asm.mov_reg(R1, R2)
            asm.bl("ks_rt_shl")
        elif isinstance(op, ast.RShift):
            asm.mov_reg(R2, R0)
            asm.mov_reg(R0, R1)
            asm.mov_reg(R1, R2)
            asm.bl("ks_rt_shr")
        else:
            raise KinoScriptError(f"Unsupported binary operator: {type(op).__name__}", lineno)

    def _emit_expr(self, asm: ArmAssembler, node: ast.AST) -> None:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, bool)):
                asm.ldr_lit(R0, int(node.value) & 0xFFFFFFFF)
                return
            raise KinoScriptError(f"Unsupported literal: {node.value!r}", node.lineno)

        if isinstance(node, ast.Name):
            self._emit_load_var_r0(asm, node.id, node.lineno)
            return

        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            arr_name = node.value.id
            if arr_name not in self.globals or not self.globals[arr_name].is_array:
                raise KinoScriptError(f"'{arr_name}' is not a declared array", node.lineno)
            gv = self.globals[arr_name]
            self._emit_expr(asm, node.slice)
            asm.cmp_imm(R0, 0)
            asm.mov_imm(R0, 0, cond="LT")
            asm.ldr_lit(R2, gv.length - 1)
            asm.cmp_reg(R0, R2)
            asm.mov_reg(R0, R2, cond="GT")
            self._emit_load_global_addr(asm, R1, gv.offset)
            asm.ldr_reg(R0, R1, R0, shift_amt=2)
            return

        if isinstance(node, ast.UnaryOp):
            self._emit_expr(asm, node.operand)
            if isinstance(node.op, ast.USub):
                asm.rsb_imm(R0, R0, 0)
            elif isinstance(node.op, ast.UAdd):
                pass
            elif isinstance(node.op, ast.Invert):
                asm.mvn_reg(R0, R0)
            elif isinstance(node.op, ast.Not):
                asm.cmp_imm(R0, 0)
                asm.mov_imm(R0, 1, cond="EQ")
                asm.mov_imm(R0, 0, cond="NE")
            else:
                raise KinoScriptError(f"Unsupported unary op: {type(node.op).__name__}", node.lineno)
            return

        if isinstance(node, ast.BinOp):
            self._emit_expr(asm, node.left)
            asm.push([R0])
            self._emit_expr(asm, node.right)
            asm.pop([R1])
            self._emit_binop_r1_r0(asm, node.op, node.lineno)
            return

        if isinstance(node, ast.BoolOp):
            end_lbl = self._new_label("bool_end")
            is_and = isinstance(node.op, ast.And)
            for idx, v in enumerate(node.values):
                self._emit_expr(asm, v)
                asm.cmp_imm(R0, 0)
                if idx < len(node.values) - 1:
                    if is_and:
                        asm.mov_imm(R0, 0, cond="EQ")
                        asm.b(end_lbl, "EQ")
                    else:
                        asm.mov_imm(R0, 1, cond="NE")
                        asm.b(end_lbl, "NE")
                else:
                    asm.mov_imm(R0, 1, cond="NE")
                    asm.mov_imm(R0, 0, cond="EQ")
            asm.label(end_lbl)
            return

        if isinstance(node, ast.Compare):
            if len(node.ops) == 1:
                self._emit_expr(asm, node.left)
                asm.push([R0])
                self._emit_expr(asm, node.comparators[0])
                asm.pop([R1])
                self._emit_cmp_r1_r0(asm, node.ops[0], node.lineno)
                return
            # Chained comparisons: a < b < c
            fail_lbl = self._new_label("cmp_fail")
            end_lbl = self._new_label("cmp_end")
            self._emit_expr(asm, node.left)
            asm.push([R0])
            for op, comp in zip(node.ops, node.comparators):
                self._emit_expr(asm, comp)
                asm.pop([R1])
                asm.push([R0])  # save current right as next left
                self._emit_cmp_r1_r0(asm, op, node.lineno)
                asm.cmp_imm(R0, 0)
                asm.b(fail_lbl, "EQ")
            asm.add_imm(SP, SP, 4)
            asm.mov_imm(R0, 1)
            asm.b(end_lbl)
            asm.label(fail_lbl)
            asm.add_imm(SP, SP, 4)
            asm.mov_imm(R0, 0)
            asm.label(end_lbl)
            return

        if isinstance(node, ast.IfExp):
            else_lbl = self._new_label("tern_e")
            end_lbl = self._new_label("tern_end")
            self._emit_expr(asm, node.test)
            asm.cmp_imm(R0, 0)
            asm.b(else_lbl, "EQ")
            self._emit_expr(asm, node.body)
            asm.b(end_lbl)
            asm.label(else_lbl)
            self._emit_expr(asm, node.orelse)
            asm.label(end_lbl)
            return

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            self._emit_call(asm, node.func.id, node.args, node.lineno)
            return

        raise KinoScriptError(f"Unsupported expression: {type(node).__name__}", getattr(node, "lineno", 0))

    def _emit_cmp_r1_r0(self, asm: ArmAssembler, op: ast.cmpop, lineno: int) -> None:
        asm.cmp_reg(R1, R0)
        cond_map = {
            ast.Eq: ("EQ", "NE"),
            ast.NotEq: ("NE", "EQ"),
            ast.Lt: ("LT", "GE"),
            ast.LtE: ("LE", "GT"),
            ast.Gt: ("GT", "LE"),
            ast.GtE: ("GE", "LT"),
        }
        for cls, (t_c, f_c) in cond_map.items():
            if isinstance(op, cls):
                asm.mov_imm(R0, 1, cond=t_c)
                asm.mov_imm(R0, 0, cond=f_c)
                return
        raise KinoScriptError(f"Unsupported comparison: {type(op).__name__}", lineno)

    def _emit_call(self, asm: ArmAssembler, name: str, args: List[ast.AST], lineno: int) -> None:
        # Built-in API Calls
        if name in KS_BUILTINS:
            exp = KS_BUILTINS[name]
            if len(args) != exp:
                raise KinoScriptError(f"Built-in '{name}' expects {exp} argument(s), got {len(args)}", lineno)
            if name == "draw_text":
                if not (isinstance(args[2], ast.Constant) and isinstance(args[2].value, str)):
                    raise KinoScriptError("draw_text(tx, ty, text) requires a string literal for text", lineno)
                slbl = self._intern_string(args[2].value)
                self._emit_expr(asm, args[0])
                asm.push([R0])
                self._emit_expr(asm, args[1])
                asm.pop([R1])  # R1 = tx, R0 = ty
                asm.mov_reg(R2, R0)
                asm.mov_reg(R0, R1)
                asm.mov_reg(R1, R2)
                asm.ldr_lit(R2, slbl)
                asm.bl("ks_rt_draw_text")
                return

            # Inline ultra-fast builtins
            if name == "abs":
                self._emit_expr(asm, args[0])
                asm.cmp_imm(R0, 0)
                asm.rsb_imm(R0, R0, 0, cond="LT")
                return
            if name in ("min", "max"):
                self._emit_expr(asm, args[0])
                asm.push([R0])
                self._emit_expr(asm, args[1])
                asm.pop([R1])
                asm.cmp_reg(R1, R0)
                asm.mov_reg(R0, R1, cond=("LT" if name == "min" else "GT"))
                return
            if name == "clamp":
                self._emit_expr(asm, args[0]); asm.push([R0])
                self._emit_expr(asm, args[1]); asm.push([R0])
                self._emit_expr(asm, args[2])  # R0 = hi
                asm.pop([R1])                  # R1 = lo
                asm.pop([R2])                  # R2 = x
                asm.cmp_reg(R2, R1)
                asm.mov_reg(R2, R1, cond="LT")
                asm.cmp_reg(R2, R0)
                asm.mov_reg(R2, R0, cond="GT")
                asm.mov_reg(R0, R2)
                return

            # Standard runtime calls (up to 4 args in R0..R3; 7 args for set_sprite via stack!)
            if name == "set_sprite":
                for a in args:
                    self._emit_expr(asm, a)
                    asm.push([R0])
                # Stack: [SP+24]=slot, [SP+20]=x, [SP+16]=y, [SP+12]=sp_idx, [SP+8]=frame, [SP+4]=pal, [SP+0]=hflip
                asm.mov_reg(R0, SP)
                asm.bl("ks_rt_set_sprite")
                asm.add_imm(SP, SP, 28)
                return

            if name == "draw_bar":
                for a in args:
                    self._emit_expr(asm, a)
                    asm.push([R0])
                # Stack: [SP+16]=tx, [SP+12]=ty, [SP+8]=w, [SP+4]=cur, [SP+0]=maxv
                asm.mov_reg(R0, SP)
                asm.bl("ks_rt_draw_bar")
                asm.add_imm(SP, SP, 20)
                return

            for a in args:
                self._emit_expr(asm, a)
                asm.push([R0])
            for r_i in range(len(args) - 1, -1, -1):
                asm.pop([r_i])  # pops into R(n-1)..R0 cleanly!
            asm.bl(f"ks_rt_{name}")
            return

        # User-defined function call
        if name not in self.functions:
            raise KinoScriptError(f"Undefined function '{name}'", lineno)
        fn_def = self.functions[name]
        exp_argc = len(fn_def.args.args)
        if len(args) != exp_argc:
            raise KinoScriptError(f"Function '{name}' expects {exp_argc} arg(s), got {len(args)}", lineno)
        for a in args:
            self._emit_expr(asm, a)
            asm.push([R0])
        asm.bl(f"ks_fn_{name}")
        if exp_argc > 0:
            asm.add_imm(SP, SP, exp_argc * 4)


# ---------------------------------------------------------------------------
# Live 60 FPS Python VM Runtime (1:1 Hardware Parity Inside KinoPixel Playtester!)
# ---------------------------------------------------------------------------
class _AutoGlobalTransformer(ast.NodeTransformer):
    """Automatically injects `global ...` for all top-level KinoScript variables inside defs."""

    def __init__(self, global_names: Set[str]) -> None:
        self.global_names = global_names

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        params = {a.arg for a in node.args.args}
        to_glob = sorted(self.global_names - params)
        if to_glob:
            node.body.insert(0, ast.Global(names=to_glob))
        return node


class KinoScriptLiveRuntime:
    """Executes a KinoScript at 60 FPS inside KinoPixel's Playtest tab with 1:1 GBA hardware parity."""

    def __init__(
        self,
        project,
        source: str,
        on_sfx: Optional[Callable[[int], None]] = None,
        on_dma: Optional[Callable[[], None]] = None,
    ) -> None:
        self.project = project
        self.source = source
        self.on_sfx = on_sfx
        self.on_dma = on_dma
        self.room_idx: int = 0
        self.cells: List[List[int]] = []
        self.ui_tiles: List[List[Tuple[int, int]]] = [[(0, 15) for _ in range(32)] for _ in range(32)]
        self.bg2_tiles: List[List[Tuple[int, int]]] = [[(0, 0) for _ in range(32)] for _ in range(32)]
        self.bg_scroll: List[Tuple[int, int]] = [(0, 0), (0, 0), (0, 0)]
        self.oam: List[Optional[Tuple[int, int, int, int, int, int]]] = [None] * 128
        self.sram: bytearray = bytearray(32 * 1024)
        self.curr_keys: int = 0
        self.prev_keys: int = 0
        self.press_keys: int = 0
        self.rel_keys: int = 0
        self.frame: int = 0
        self.rng_state: int = 0x12345678
        self.bgm_on: bool = True
        self.fade_level: int = 0  # -16 (black) .. 0 (normal) .. +16 (white flash)
        self.error: str = ""
        self._ns: Dict[str, Any] = {}
        self._load_room(0)
        self._compile_and_init()

    def _load_room(self, idx: int) -> None:
        rooms = self.project.rooms or [self.project.level]
        self.room_idx = max(0, min(len(rooms) - 1, int(idx)))
        rm = rooms[self.room_idx]
        self.cells = copy.deepcopy(rm.cells)

    def _compile_and_init(self) -> None:
        from .gba_compiler import FONT_INDEX
        self._font_index = FONT_INDEX
        try:
            tree = ast.parse(self.source)
            top_globals: Set[str] = set()
            for st in tree.body:
                if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                    top_globals.add(st.targets[0].id)
            tree = _AutoGlobalTransformer(top_globals).visit(tree)
            ast.fix_missing_locations(tree)
            code = compile(tree, "<kinoscript>", "exec")
        except Exception as exc:
            self.error = str(exc)
            return

        ns: Dict[str, Any] = dict(KS_CONSTANTS)
        ns.update({
            "range": range,
            "key_held": lambda m: 1 if (self.curr_keys & int(m)) else 0,
            "key_pressed": lambda m: 1 if (self.press_keys & int(m)) else 0,
            "key_released": lambda m: 1 if (self.rel_keys & int(m)) else 0,
            "frame_count": lambda: self.frame,
            "load_room": self._api_load_room,
            "room_width": lambda: len(self.cells[0]) if self.cells else 30,
            "room_height": lambda: len(self.cells),
            "get_tile": self._api_get_tile,
            "get_tile_type": self._api_get_tile_type,
            "set_tile": self._api_set_tile,
            "set_ui_tile": self._api_set_ui_tile,
            "set_bg2_tile": self._api_set_bg2_tile,
            "scroll_bg": self._api_scroll_bg,
            "draw_text": self._api_draw_text,
            "draw_num": self._api_draw_num,
            "draw_box": self._api_draw_box,
            "draw_window": self._api_draw_window,
            "draw_bar": self._api_draw_bar,
            "set_fade": self._api_set_fade,
            "clear_ui_rect": self._api_clear_ui_rect,
            "clear_ui": self._api_clear_ui,
            "set_sprite": self._api_set_sprite,
            "hide_sprite": self._api_hide_sprite,
            "hide_all_sprites": self._api_hide_all_sprites,
            "play_sfx": self._api_play_sfx,
            "play_dma": self._api_play_dma,
            "bgm_enable": lambda on: setattr(self, "bgm_on", bool(on)),
            "sram_write": self._api_sram_write,
            "sram_read": self._api_sram_read,
            "abs": lambda x: abs(int(x)),
            "min": lambda a, b: min(int(a), int(b)),
            "max": lambda a, b: max(int(a), int(b)),
            "clamp": lambda x, lo, hi: max(int(lo), min(int(hi), int(x))),
            "rand": self._api_rand,
        })
        self._ns = ns
        try:
            exec(code, ns)
            if "on_init" in ns and callable(ns["on_init"]):
                ns["on_init"]()
        except Exception as exc:
            self.error = str(exc)

    def _api_load_room(self, idx: int) -> int:
        self._load_room(idx)
        return 0

    def _api_get_tile(self, tx: int, ty: int) -> int:
        tx, ty = int(tx), int(ty)
        if 0 <= ty < len(self.cells) and 0 <= tx < len(self.cells[ty]):
            return int(self.cells[ty][tx])
        return 0

    def _api_get_tile_type(self, tx: int, ty: int) -> int:
        ti = self._api_get_tile(tx, ty)
        if 0 <= ti < len(self.project.tiles):
            return int(self.project.tiles[ti].tile_type)
        return 0

    def _api_set_tile(self, tx: int, ty: int, tid: int) -> int:
        tx, ty, tid = int(tx), int(ty), int(tid)
        if 0 <= ty < len(self.cells) and 0 <= tx < len(self.cells[ty]):
            self.cells[ty][tx] = tid & 0xFF
        return 0

    def _api_set_ui_tile(self, tx: int, ty: int, tid: int, pal: int) -> int:
        tx, ty = int(tx), int(ty)
        if 0 <= ty < 32 and 0 <= tx < 32:
            self.ui_tiles[ty][tx] = (int(tid) & 0x3FF, int(pal) & 0xF)
        return 0

    def _api_set_bg2_tile(self, tx: int, ty: int, tid: int, pal: int) -> int:
        tx, ty = int(tx), int(ty)
        if 0 <= ty < 32 and 0 <= tx < 32:
            self.bg2_tiles[ty][tx] = (int(tid) & 0x3FF, int(pal) & 0xF)
        return 0

    def _api_scroll_bg(self, layer: int, x: int, y: int) -> int:
        li = max(0, min(2, int(layer)))
        self.bg_scroll[li] = (int(x), int(y))
        return 0

    def _api_draw_text(self, tx: int, ty: int, text: str) -> int:
        from .gba_compiler import FONT_SOLID_OFFSET
        tx, ty = int(tx), int(ty)
        for i, ch in enumerate(str(text).upper()):
            cx = tx + i
            if 0 <= ty < 32 and 0 <= cx < 32:
                gid = self._font_index.get(ch, 0)
                if self.ui_tiles[ty][cx][0] != 0:
                    gid += FONT_SOLID_OFFSET
                self.ui_tiles[ty][cx] = (gid, 15)
        return 0

    def _api_draw_num(self, tx: int, ty: int, val: int, digits: int) -> int:
        d = max(1, min(6, int(digits)))
        v = max(0, int(val))
        s = str(v).rjust(d, "0")[-d:]
        return self._api_draw_text(tx, ty, s)

    def _api_draw_box(self, tx: int, ty: int, w: int, h: int) -> int:
        tx, ty, w, h = int(tx), int(ty), int(w), int(h)
        box_id = self._font_index["BOX"]
        for yy in range(ty, ty + h):
            for xx in range(tx, tx + w):
                if 0 <= yy < 32 and 0 <= xx < 32:
                    self.ui_tiles[yy][xx] = (box_id, 15)
        return 0

    def _api_draw_window(self, tx: int, ty: int, w: int, h: int) -> int:
        tx, ty, w, h = int(tx), int(ty), int(w), int(h)
        if w < 2 or h < 2:
            return 0
        self._api_draw_box(tx, ty, w, h)
        fi = self._font_index
        for xx in range(tx + 1, tx + w - 1):
            if 0 <= xx < 32:
                if 0 <= ty < 32: self.ui_tiles[ty][xx] = (fi["WIN_T"], 15)
                if 0 <= ty + h - 1 < 32: self.ui_tiles[ty + h - 1][xx] = (fi["WIN_B"], 15)
        for yy in range(ty + 1, ty + h - 1):
            if 0 <= yy < 32:
                if 0 <= tx < 32: self.ui_tiles[yy][tx] = (fi["WIN_L"], 15)
                if 0 <= tx + w - 1 < 32: self.ui_tiles[yy][tx + w - 1] = (fi["WIN_R"], 15)
        for px, py, k in ((tx, ty, "WIN_UL"), (tx + w - 1, ty, "WIN_UR"), (tx, ty + h - 1, "WIN_BL"), (tx + w - 1, ty + h - 1, "WIN_BR")):
            if 0 <= py < 32 and 0 <= px < 32:
                self.ui_tiles[py][px] = (fi[k], 15)
        return 0

    def _api_draw_bar(self, tx: int, ty: int, w: int, cur: int, maxv: int) -> int:
        tx, ty, w = int(tx), int(ty), int(w)
        if w < 1 or not (0 <= ty < 32):
            return 0
        maxv = max(1, int(maxv))
        cur = max(0, int(cur))
        filled = (cur * w) // maxv
        fi = self._font_index
        on_id = fi["BAR_LO"] if (filled * 3 <= w) else fi["BAR_ON"]
        off_id = fi["BAR_OF"]
        for i in range(w):
            cx = tx + i
            if 0 <= cx < 32:
                self.ui_tiles[ty][cx] = (on_id if i < filled else off_id, 15)
        return 0

    def _api_set_fade(self, level: int) -> int:
        self.fade_level = max(-16, min(16, int(level)))
        return 0

    def _api_clear_ui_rect(self, tx: int, ty: int, w: int, h: int) -> int:
        tx, ty, w, h = int(tx), int(ty), int(w), int(h)
        for yy in range(ty, ty + h):
            for xx in range(tx, tx + w):
                if 0 <= yy < 32 and 0 <= xx < 32:
                    self.ui_tiles[yy][xx] = (0, 15)
        return 0

    def _api_clear_ui(self) -> int:
        for yy in range(32):
            for xx in range(32):
                self.ui_tiles[yy][xx] = (0, 15)
        return 0

    def _api_set_sprite(self, slot: int, x: int, y: int, sp_idx: int, frame: int, pal: int, hflip: int) -> int:
        sl = int(slot)
        if 0 <= sl < 128:
            self.oam[sl] = (int(x), int(y), int(sp_idx), int(frame), int(pal), 1 if hflip else 0)
        return 0

    def _api_hide_sprite(self, slot: int) -> int:
        sl = int(slot)
        if 0 <= sl < 128:
            self.oam[sl] = None
        return 0

    def _api_hide_all_sprites(self) -> int:
        for i in range(128):
            self.oam[i] = None
        return 0

    def _api_play_sfx(self, idx: int) -> int:
        if self.on_sfx:
            self.on_sfx(int(idx))
        return 0

    def _api_play_dma(self) -> int:
        if self.on_dma:
            self.on_dma()
        return 0

    def _api_sram_write(self, addr: int, val: int) -> int:
        self.sram[int(addr) & 0x7FFF] = int(val) & 0xFF
        return 0

    def _api_sram_read(self, addr: int) -> int:
        return int(self.sram[int(addr) & 0x7FFF])

    def _api_rand(self) -> int:
        self.rng_state = (self.rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        return self.rng_state >> 16

    def step(self, pressed_buttons: Set[str]) -> None:
        if self.error:
            return
        self.frame += 1
        self.prev_keys = self.curr_keys
        mask = 0
        for b in pressed_buttons:
            mask |= BUTTON_BITS.get(b.upper(), 0)
        self.curr_keys = mask
        self.press_keys = self.curr_keys & ~self.prev_keys
        self.rel_keys = self.prev_keys & ~self.curr_keys
        fn = self._ns.get("on_frame")
        if callable(fn):
            try:
                fn()
            except Exception as exc:
                self.error = str(exc)


def validate_kinoscript(source: str) -> Tuple[bool, str, int]:
    """Validate & dry-compile a KinoScript to ARM7TDMI machine code. Returns (ok, message, ram_bytes)."""
    from .gba_compiler import FONT_INDEX
    try:
        comp = KinoScriptArmCompiler(source, FONT_INDEX)
        test_asm = ArmAssembler(base_addr=0x08000000)
        # Emit stub labels for dry-run verification
        for stub in (
            "copy_halfwords", "hide_all_oam", "play_sfx", "play_dma_pcm",
            "ks_rt_divmod", "ks_rt_shl", "ks_rt_shr",
            "ks_rt_key_held", "ks_rt_key_pressed", "ks_rt_key_released", "ks_rt_frame_count",
            "ks_rt_load_room", "ks_rt_room_width", "ks_rt_room_height",
            "ks_rt_get_tile", "ks_rt_get_tile_type", "ks_rt_set_tile",
            "ks_rt_set_ui_tile", "ks_rt_set_bg2_tile", "ks_rt_scroll_bg",
            "ks_rt_draw_text", "ks_rt_draw_num", "ks_rt_draw_box",
            "ks_rt_draw_window", "ks_rt_draw_bar", "ks_rt_set_fade",
            "ks_rt_clear_ui_rect", "ks_rt_clear_ui", "ks_rt_set_sprite",
            "ks_rt_hide_sprite", "ks_rt_hide_all_sprites", "ks_rt_play_sfx",
            "ks_rt_play_dma", "ks_rt_bgm_enable", "ks_rt_sram_write",
            "ks_rt_sram_read", "ks_rt_rand",
        ):
            test_asm.label(stub)
            test_asm.bx(LR)
        before = test_asm.offset
        comp.emit_code_and_data(test_asm)
        raw = test_asm.finalize()
        code_bytes = len(raw) - before
        return True, f"Valid KinoScript · {len(comp.functions)} func(s) · {code_bytes:,} B ARM7TDMI · {comp.ram_bytes_used:,} B RAM", comp.ram_bytes_used
    except KinoScriptError as exc:
        return False, str(exc), 0
    except Exception as exc:
        return False, f"Compiler error: {exc}", 0
