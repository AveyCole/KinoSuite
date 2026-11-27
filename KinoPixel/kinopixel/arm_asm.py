"""Pure-Python ARM7TDMI (ARMv4T 32-bit) Assembler for Game Boy Advance ROM generation.

Supports labels, conditional execution, branches, data processing, multiply,
LDR/STR/LDRB/STRB/LDRH/STRH/LDRSH, PUSH/POP, automatic literal pools, and
raw data directives. Zero external toolchain required.
"""
from __future__ import annotations

import struct
from typing import Dict, List, Optional, Tuple, Union

# ARM Condition codes (bits 31..28)
COND: Dict[str, int] = {
    "EQ": 0x0, "NE": 0x1, "CS": 0x2, "HS": 0x2, "CC": 0x3, "LO": 0x3,
    "MI": 0x4, "PL": 0x5, "VS": 0x6, "VC": 0x7, "HI": 0x8, "LS": 0x9,
    "GE": 0xA, "LT": 0xB, "GT": 0xC, "LE": 0xD, "AL": 0xE, "": 0xE,
}

# Data processing opcodes (bits 24..21)
DP_OP: Dict[str, int] = {
    "AND": 0x0, "EOR": 0x1, "SUB": 0x2, "RSB": 0x3,
    "ADD": 0x4, "ADC": 0x5, "SBC": 0x6, "RSC": 0x7,
    "TST": 0x8, "TEQ": 0x9, "CMP": 0xA, "CMN": 0xB,
    "ORR": 0xC, "MOV": 0xD, "BIC": 0xE, "MVN": 0xF,
}

SHIFT_TYPE: Dict[str, int] = {"LSL": 0, "LSR": 1, "ASR": 2, "ROR": 3}

# Register constants
R0, R1, R2, R3, R4, R5, R6, R7 = 0, 1, 2, 3, 4, 5, 6, 7
R8, R9, R10, R11, R12, SP, LR, PC = 8, 9, 10, 11, 12, 13, 14, 15


def encode_arm_imm(value: int) -> Optional[int]:
    """Encode a 32-bit unsigned integer as ARM 12-bit rotated immediate (rot4 << 8 | imm8)."""
    v = value & 0xFFFFFFFF
    for rot in range(16):
        shift = rot * 2
        # Rotate LEFT by shift to test if rotating RIGHT by shift yields v
        cand = ((v << shift) | (v >> (32 - shift))) & 0xFFFFFFFF if shift else v
        if cand <= 0xFF:
            return (rot << 8) | cand
    return None


class ArmAssembler:
    """Two-pass ARM7TDMI assembler targeting GBA ROM address space (default 0x08000000)."""

    def __init__(self, base_addr: int = 0x08000000) -> None:
        self.base_addr = base_addr
        self.buf = bytearray()
        self.labels: Dict[str, int] = {}
        # (offset_in_buf, cond, is_link, target_label)
        self._branch_fixups: List[Tuple[int, int, int, str]] = []
        # (offset_in_buf, cond, rd, value_or_label)
        self._pending_pool: List[Tuple[int, int, int, Union[int, str]]] = []
        # (offset_in_buf, label_name) for 32-bit absolute address data slots
        self._word_label_fixups: List[Tuple[int, str]] = []

    @property
    def offset(self) -> int:
        return len(self.buf)

    @property
    def pc(self) -> int:
        return self.base_addr + len(self.buf)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"Duplicate ARM label: {name}")
        self.labels[name] = self.pc

    def align(self, boundary: int = 4, fill: int = 0) -> None:
        rem = len(self.buf) % boundary
        if rem:
            self.buf.extend(bytes([fill]) * (boundary - rem))

    def emit32(self, word: int) -> int:
        off = len(self.buf)
        self.buf.extend(struct.pack("<I", word & 0xFFFFFFFF))
        return off

    def emit16(self, half: int) -> int:
        off = len(self.buf)
        self.buf.extend(struct.pack("<H", half & 0xFFFF))
        return off

    def emit_bytes(self, data: bytes) -> int:
        off = len(self.buf)
        self.buf.extend(data)
        return off

    def emit_word_label(self, label_name: str) -> int:
        off = self.emit32(0)
        self._word_label_fixups.append((off, label_name))
        return off

    # ------------------------------------------------------------------
    # Literal Pool Management (LDR Rd, =imm32 / =label)
    # ------------------------------------------------------------------
    def ldr_lit(self, rd: int, val_or_label: Union[int, str], cond: str = "") -> None:
        """Load any 32-bit constant or label address into Rd (uses MOV/MVN when possible)."""
        c = COND[cond.upper()]
        if isinstance(val_or_label, int):
            v = val_or_label & 0xFFFFFFFF
            enc = encode_arm_imm(v)
            if enc is not None:
                self.emit32((c << 28) | (1 << 25) | (DP_OP["MOV"] << 21) | (rd << 12) | enc)
                return
            enc_inv = encode_arm_imm((~v) & 0xFFFFFFFF)
            if enc_inv is not None:
                self.emit32((c << 28) | (1 << 25) | (DP_OP["MVN"] << 21) | (rd << 12) | enc_inv)
                return
        off = self.emit32(0)
        self._pending_pool.append((off, c, rd, val_or_label))

    def pool(self) -> None:
        """Emit pending literal pool words and patch PC-relative LDR instructions."""
        if not self._pending_pool:
            return
        self.align(4)
        # Deduplicate literals within this pool
        placed: Dict[Union[int, str], int] = {}
        for ldr_off, c, rd, item in self._pending_pool:
            if item not in placed:
                lit_off = len(self.buf)
                placed[item] = lit_off
                if isinstance(item, int):
                    self.emit32(item & 0xFFFFFFFF)
                else:
                    self.emit_word_label(item)
            lit_off = placed[item]
            delta = lit_off - (ldr_off + 8)
            u_bit = 1 if delta >= 0 else 0
            mag = abs(delta)
            if mag > 0xFFF:
                raise ValueError(f"Literal pool out of range ({delta} bytes) for {item}")
            insn = (c << 28) | (1 << 26) | (1 << 24) | (u_bit << 23) | (1 << 20) | (PC << 16) | (rd << 12) | mag
            struct.pack_into("<I", self.buf, ldr_off, insn)
        self._pending_pool.clear()

    # ------------------------------------------------------------------
    # Branches
    # ------------------------------------------------------------------
    def b(self, target: str, cond: str = "") -> None:
        off = self.emit32(0)
        self._branch_fixups.append((off, COND[cond.upper()], 0, target))

    def bl(self, target: str, cond: str = "") -> None:
        off = self.emit32(0)
        self._branch_fixups.append((off, COND[cond.upper()], 1, target))

    def bx(self, rn: int, cond: str = "") -> None:
        self.emit32((COND[cond.upper()] << 28) | 0x012FFF10 | (rn & 0xF))

    def nop(self) -> None:
        self.mov_reg(R0, R0)

    # ------------------------------------------------------------------
    # Data Processing
    # ------------------------------------------------------------------
    def _dp_imm(self, op: str, rd: int, rn: int, imm: int, s: bool = False, cond: str = "") -> None:
        enc = encode_arm_imm(imm)
        if enc is None:
            raise ValueError(f"Immediate 0x{imm:X} cannot be encoded in ARM {op}")
        c = COND[cond.upper()]
        self.emit32(
            (c << 28) | (1 << 25) | (DP_OP[op] << 21) | ((1 if s else 0) << 20) |
            ((rn & 0xF) << 16) | ((rd & 0xF) << 12) | enc
        )

    def _dp_reg(
        self, op: str, rd: int, rn: int, rm: int,
        shift_type: str = "LSL", shift_amt: int = 0,
        s: bool = False, cond: str = ""
    ) -> None:
        c = COND[cond.upper()]
        if shift_amt == 0:
            st = 0
            sa = 0
        else:
            st = SHIFT_TYPE[shift_type.upper()]
            sa = shift_amt & 0x1F
        self.emit32(
            (c << 28) | (DP_OP[op] << 21) | ((1 if s else 0) << 20) |
            ((rn & 0xF) << 16) | ((rd & 0xF) << 12) | (sa << 7) | (st << 5) | (rm & 0xF)
        )

    def mov_imm(self, rd: int, imm: int, s: bool = False, cond: str = "") -> None:
        self._dp_imm("MOV", rd, 0, imm, s=s, cond=cond)

    def mvn_imm(self, rd: int, imm: int, s: bool = False, cond: str = "") -> None:
        self._dp_imm("MVN", rd, 0, imm, s=s, cond=cond)

    def mov_reg(self, rd: int, rm: int, shift_type: str = "LSL", shift_amt: int = 0, s: bool = False, cond: str = "") -> None:
        self._dp_reg("MOV", rd, 0, rm, shift_type=shift_type, shift_amt=shift_amt, s=s, cond=cond)

    def mvn_reg(self, rd: int, rm: int, s: bool = False, cond: str = "") -> None:
        self._dp_reg("MVN", rd, 0, rm, s=s, cond=cond)

    def add_imm(self, rd: int, rn: int, imm: int, s: bool = False, cond: str = "") -> None:
        self._dp_imm("ADD", rd, rn, imm, s=s, cond=cond)

    def add_reg(self, rd: int, rn: int, rm: int, shift_type: str = "LSL", shift_amt: int = 0, s: bool = False, cond: str = "") -> None:
        self._dp_reg("ADD", rd, rn, rm, shift_type=shift_type, shift_amt=shift_amt, s=s, cond=cond)

    def sub_imm(self, rd: int, rn: int, imm: int, s: bool = False, cond: str = "") -> None:
        self._dp_imm("SUB", rd, rn, imm, s=s, cond=cond)

    def sub_reg(self, rd: int, rn: int, rm: int, shift_type: str = "LSL", shift_amt: int = 0, s: bool = False, cond: str = "") -> None:
        self._dp_reg("SUB", rd, rn, rm, shift_type=shift_type, shift_amt=shift_amt, s=s, cond=cond)

    def rsb_imm(self, rd: int, rn: int, imm: int, s: bool = False, cond: str = "") -> None:
        self._dp_imm("RSB", rd, rn, imm, s=s, cond=cond)

    def and_imm(self, rd: int, rn: int, imm: int, s: bool = False, cond: str = "") -> None:
        self._dp_imm("AND", rd, rn, imm, s=s, cond=cond)

    def and_reg(self, rd: int, rn: int, rm: int, s: bool = False, cond: str = "") -> None:
        self._dp_reg("AND", rd, rn, rm, s=s, cond=cond)

    def bic_imm(self, rd: int, rn: int, imm: int, s: bool = False, cond: str = "") -> None:
        self._dp_imm("BIC", rd, rn, imm, s=s, cond=cond)

    def bic_reg(self, rd: int, rn: int, rm: int, s: bool = False, cond: str = "") -> None:
        self._dp_reg("BIC", rd, rn, rm, s=s, cond=cond)

    def orr_imm(self, rd: int, rn: int, imm: int, s: bool = False, cond: str = "") -> None:
        self._dp_imm("ORR", rd, rn, imm, s=s, cond=cond)

    def orr_reg(self, rd: int, rn: int, rm: int, shift_type: str = "LSL", shift_amt: int = 0, s: bool = False, cond: str = "") -> None:
        self._dp_reg("ORR", rd, rn, rm, shift_type=shift_type, shift_amt=shift_amt, s=s, cond=cond)

    def eor_imm(self, rd: int, rn: int, imm: int, s: bool = False, cond: str = "") -> None:
        self._dp_imm("EOR", rd, rn, imm, s=s, cond=cond)

    def eor_reg(self, rd: int, rn: int, rm: int, s: bool = False, cond: str = "") -> None:
        self._dp_reg("EOR", rd, rn, rm, s=s, cond=cond)

    def cmp_imm(self, rn: int, imm: int, cond: str = "") -> None:
        if imm < 0:
            self._dp_imm("CMN", 0, rn, -imm, s=True, cond=cond)
        else:
            self._dp_imm("CMP", 0, rn, imm, s=True, cond=cond)

    def cmn_imm(self, rn: int, imm: int, cond: str = "") -> None:
        self._dp_imm("CMN", 0, rn, imm, s=True, cond=cond)

    def cmp_reg(self, rn: int, rm: int, shift_type: str = "LSL", shift_amt: int = 0, cond: str = "") -> None:
        self._dp_reg("CMP", 0, rn, rm, shift_type=shift_type, shift_amt=shift_amt, s=True, cond=cond)

    def tst_imm(self, rn: int, imm: int, cond: str = "") -> None:
        self._dp_imm("TST", 0, rn, imm, s=True, cond=cond)

    def tst_reg(self, rn: int, rm: int, cond: str = "") -> None:
        self._dp_reg("TST", 0, rn, rm, s=True, cond=cond)

    def mul(self, rd: int, rm: int, rs: int, s: bool = False, cond: str = "") -> None:
        if rd == rm:
            raise ValueError("ARMv4 MUL requires Rd != Rm")
        c = COND[cond.upper()]
        self.emit32((c << 28) | ((1 if s else 0) << 20) | ((rd & 0xF) << 16) | ((rs & 0xF) << 8) | 0x90 | (rm & 0xF))

    # ------------------------------------------------------------------
    # Load / Store (Word, Byte, Halfword)
    # ------------------------------------------------------------------
    def _ls_imm(self, is_load: bool, is_byte: bool, rd: int, rn: int, offset: int = 0, cond: str = "") -> None:
        c = COND[cond.upper()]
        u = 1 if offset >= 0 else 0
        mag = abs(offset)
        if mag > 0xFFF:
            raise ValueError(f"LDR/STR offset out of range: {offset}")
        self.emit32(
            (c << 28) | (1 << 26) | (1 << 24) | (u << 23) |
            ((1 if is_byte else 0) << 22) | ((1 if is_load else 0) << 20) |
            ((rn & 0xF) << 16) | ((rd & 0xF) << 12) | mag
        )

    def _ls_reg(
        self, is_load: bool, is_byte: bool, rd: int, rn: int, rm: int,
        shift_type: str = "LSL", shift_amt: int = 0, cond: str = ""
    ) -> None:
        c = COND[cond.upper()]
        st = 0 if shift_amt == 0 else SHIFT_TYPE[shift_type.upper()]
        sa = shift_amt & 0x1F
        self.emit32(
            (c << 28) | (3 << 25) | (1 << 24) | (1 << 23) |
            ((1 if is_byte else 0) << 22) | ((1 if is_load else 0) << 20) |
            ((rn & 0xF) << 16) | ((rd & 0xF) << 12) | (sa << 7) | (st << 5) | (rm & 0xF)
        )

    def ldr(self, rd: int, rn: int, offset: int = 0, cond: str = "") -> None:
        self._ls_imm(True, False, rd, rn, offset, cond)

    def str(self, rd: int, rn: int, offset: int = 0, cond: str = "") -> None:
        self._ls_imm(False, False, rd, rn, offset, cond)

    def ldrb(self, rd: int, rn: int, offset: int = 0, cond: str = "") -> None:
        self._ls_imm(True, True, rd, rn, offset, cond)

    def strb(self, rd: int, rn: int, offset: int = 0, cond: str = "") -> None:
        self._ls_imm(False, True, rd, rn, offset, cond)

    def ldr_reg(self, rd: int, rn: int, rm: int, shift_amt: int = 0, cond: str = "") -> None:
        self._ls_reg(True, False, rd, rn, rm, "LSL", shift_amt, cond)

    def str_reg(self, rd: int, rn: int, rm: int, shift_amt: int = 0, cond: str = "") -> None:
        self._ls_reg(False, False, rd, rn, rm, "LSL", shift_amt, cond)

    def ldrb_reg(self, rd: int, rn: int, rm: int, cond: str = "") -> None:
        self._ls_reg(True, True, rd, rn, rm, "LSL", 0, cond)

    def ldrh(self, rd: int, rn: int, offset: int = 0, cond: str = "") -> None:
        self._lsh_imm(True, 0, 1, rd, rn, offset, cond)

    def strh(self, rd: int, rn: int, offset: int = 0, cond: str = "") -> None:
        self._lsh_imm(False, 0, 1, rd, rn, offset, cond)

    def ldrsh(self, rd: int, rn: int, offset: int = 0, cond: str = "") -> None:
        self._lsh_imm(True, 1, 1, rd, rn, offset, cond)

    def ldrh_reg(self, rd: int, rn: int, rm: int, cond: str = "") -> None:
        c = COND[cond.upper()]
        self.emit32(
            (c << 28) | (1 << 24) | (1 << 23) | (1 << 20) |
            ((rn & 0xF) << 16) | ((rd & 0xF) << 12) | 0xB0 | (rm & 0xF)
        )

    def strh_reg(self, rd: int, rn: int, rm: int, cond: str = "") -> None:
        c = COND[cond.upper()]
        self.emit32(
            (c << 28) | (1 << 24) | (1 << 23) |
            ((rn & 0xF) << 16) | ((rd & 0xF) << 12) | 0xB0 | (rm & 0xF)
        )

    def _lsh_imm(self, is_load: bool, s_bit: int, h_bit: int, rd: int, rn: int, offset: int, cond: str) -> None:
        c = COND[cond.upper()]
        u = 1 if offset >= 0 else 0
        mag = abs(offset)
        if mag > 0xFF:
            raise ValueError(f"LDRH/STRH immediate offset out of range: {offset}")
        self.emit32(
            (c << 28) | (1 << 24) | (u << 23) | (1 << 22) | ((1 if is_load else 0) << 20) |
            ((rn & 0xF) << 16) | ((rd & 0xF) << 12) | ((mag >> 4) << 8) |
            (1 << 7) | (s_bit << 6) | (h_bit << 5) | (1 << 4) | (mag & 0xF)
        )

    # ------------------------------------------------------------------
    # Stack Push / Pop
    # ------------------------------------------------------------------
    def push(self, regs: List[int], cond: str = "") -> None:
        mask = 0
        for r in regs:
            mask |= 1 << r
        self.emit32((COND[cond.upper()] << 28) | 0x092D0000 | mask)

    def pop(self, regs: List[int], cond: str = "") -> None:
        mask = 0
        for r in regs:
            mask |= 1 << r
        self.emit32((COND[cond.upper()] << 28) | 0x08BD0000 | mask)

    # ------------------------------------------------------------------
    # Final Link Pass
    # ------------------------------------------------------------------
    def finalize(self) -> bytes:
        self.pool()
        for off, c, is_link, target in self._branch_fixups:
            if target not in self.labels:
                raise KeyError(f"Undefined ARM branch target: {target}")
            target_addr = self.labels[target]
            pc_addr = self.base_addr + off + 8
            delta = target_addr - pc_addr
            if delta % 4 != 0:
                raise ValueError(f"Unaligned branch target {target}")
            imm24 = (delta >> 2) & 0x00FFFFFF
            insn = (c << 28) | (0b101 << 25) | (is_link << 24) | imm24
            struct.pack_into("<I", self.buf, off, insn)

        for off, target in self._word_label_fixups:
            if target not in self.labels:
                raise KeyError(f"Undefined ARM data label: {target}")
            struct.pack_into("<I", self.buf, off, self.labels[target] & 0xFFFFFFFF)

        return bytes(self.buf)
