"""Comprehensive KinoPixel verification suite — includes a real ARM7TDMI GBA CPU verifier!"""
from __future__ import annotations

import os
import struct
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kinopixel.audio_sfx import synthesize_sfx_waveform
from kinopixel.gba_compiler import (
    GBA_NINTENDO_LOGO,
    GB_NINTENDO_LOGO,
    compile_gb_rom,
    compile_gba_rom,
    compute_gba_header_checksum,
    export_c_source,
)
from kinopixel.models import BUTTON_BITS, KinoPixelProject
from kinopixel.sample_project import create_starter_project
from kinopixel.simulator import GamePlaytestEngine


# ---------------------------------------------------------------------------
# Minimal Hardware-Accurate ARM7TDMI (ARM32) + GBA Bus Verifier
# ---------------------------------------------------------------------------
class MiniGbaCpu:
    """Executes compiled ARMv4T .gba ROM binaries and checks GBA hardware constraints."""

    def __init__(self, rom: bytes) -> None:
        self.rom = rom
        self.ewram = bytearray(256 * 1024)
        self.iwram = bytearray(32 * 1024)
        self.io = bytearray(0x400)
        self.pal = bytearray(0x400)
        self.vram = bytearray(96 * 1024)
        self.oam = bytearray(0x400)
        self.sram = bytearray(32 * 1024)
        self.regs = [0] * 16
        self.regs[15] = 0x08000000
        self.cpsr_n = 0
        self.cpsr_z = 0
        self.cpsr_c = 0
        self.cpsr_v = 0
        self.vcount = 0
        self.vcount_reads = 0
        self.keyinput = 0x03FF  # active-LOW (all released)
        self.sfx1_triggers = 0
        self.sfx2_triggers = 0
        self.sfx4_triggers = 0
        self.dma1_triggers = 0
        self.steps = 0

    def set_buttons(self, pressed_names: list[str]) -> None:
        mask = 0
        for name in pressed_names:
            mask |= BUTTON_BITS[name]
        self.keyinput = (~mask) & 0x03FF

    def _region(self, addr: int):
        hi = (addr >> 24) & 0xFF
        if hi == 0x02:
            return self.ewram, addr & 0x3FFFF, "EWRAM"
        if hi == 0x03:
            return self.iwram, addr & 0x7FFF, "IWRAM"
        if hi == 0x04:
            return self.io, addr & 0x3FF, "IO"
        if hi == 0x05:
            return self.pal, addr & 0x3FF, "PAL"
        if hi == 0x06:
            off = addr & 0x1FFFF
            if off >= 0x18000:
                off -= 0x8000
            return self.vram, off, "VRAM"
        if hi == 0x07:
            return self.oam, addr & 0x3FF, "OAM"
        if hi == 0x08:
            return self.rom, addr - 0x08000000, "ROM"
        if hi == 0x0E:
            return self.sram, addr & 0x7FFF, "SRAM"
        raise RuntimeError(f"Unmapped GBA memory access at 0x{addr:08X} (PC=0x{self.regs[15]:08X})")

    def read8(self, addr: int) -> int:
        mem, off, _ = self._region(addr)
        return mem[off]

    def read16(self, addr: int) -> int:
        addr &= ~1
        if addr == 0x04000006:  # REG_VCOUNT
            # Simulate scanlines progressing quickly through draw & vblank
            self.vcount_reads += 1
            if self.vcount_reads % 2 == 0:
                self.vcount = 160 if self.vcount < 160 else 0
            return self.vcount
        if addr == 0x04000130:  # REG_KEYINPUT
            return self.keyinput
        mem, off, _ = self._region(addr)
        return struct.unpack_from("<H", mem, off)[0]

    def read32(self, addr: int) -> int:
        addr &= ~3
        mem, off, _ = self._region(addr)
        return struct.unpack_from("<I", mem, off)[0]

    def write8(self, addr: int, val: int) -> None:
        mem, off, name = self._region(addr)
        if name in ("PAL", "VRAM", "OAM", "ROM"):
            raise AssertionError(f"Illegal 8-bit STRB write to {name} at 0x{addr:08X}!")
        mem[off] = val & 0xFF

    def write16(self, addr: int, val: int) -> None:
        addr &= ~1
        if addr == 0x04000064 and (val & 0x8000):
            self.sfx1_triggers += 1
        if addr == 0x0400006C and (val & 0x8000):
            self.sfx2_triggers += 1
        if addr == 0x0400007C and (val & 0x8000):
            self.sfx4_triggers += 1
        if addr == 0x040000C6 and (val & 0x8000):
            self.dma1_triggers += 1
        mem, off, name = self._region(addr)
        if name == "ROM":
            raise AssertionError(f"Write to ROM at 0x{addr:08X}")
        struct.pack_into("<H", mem, off, val & 0xFFFF)

    def write32(self, addr: int, val: int) -> None:
        addr &= ~3
        mem, off, name = self._region(addr)
        if name == "ROM":
            raise AssertionError(f"Write to ROM at 0x{addr:08X}")
        struct.pack_into("<I", mem, off, val & 0xFFFFFFFF)

    def _cond_ok(self, cond: int) -> bool:
        n, z, c, v = self.cpsr_n, self.cpsr_z, self.cpsr_c, self.cpsr_v
        if cond == 0xE: return True
        if cond == 0x0: return z == 1
        if cond == 0x1: return z == 0
        if cond == 0x2: return c == 1
        if cond == 0x3: return c == 0
        if cond == 0x4: return n == 1
        if cond == 0x5: return n == 0
        if cond == 0x8: return c == 1 and z == 0
        if cond == 0x9: return c == 0 or z == 1
        if cond == 0xA: return n == v
        if cond == 0xB: return n != v
        if cond == 0xC: return z == 0 and n == v
        if cond == 0xD: return z == 1 or n != v
        raise RuntimeError(f"Unsupported cond {cond}")

    def _set_nz(self, val: int) -> None:
        v = val & 0xFFFFFFFF
        self.cpsr_n = (v >> 31) & 1
        self.cpsr_z = 1 if v == 0 else 0

    def _set_sub_flags(self, a: int, b: int) -> int:
        a &= 0xFFFFFFFF
        b &= 0xFFFFFFFF
        res = (a - b) & 0xFFFFFFFF
        self._set_nz(res)
        self.cpsr_c = 1 if a >= b else 0
        sa = a if a < 0x80000000 else a - 0x100000000
        sb = b if b < 0x80000000 else b - 0x100000000
        sr = res if res < 0x80000000 else res - 0x100000000
        self.cpsr_v = 1 if (sa - sb) != sr else 0
        return res

    def _set_add_flags(self, a: int, b: int) -> int:
        a &= 0xFFFFFFFF
        b &= 0xFFFFFFFF
        full = a + b
        res = full & 0xFFFFFFFF
        self._set_nz(res)
        self.cpsr_c = 1 if full > 0xFFFFFFFF else 0
        sa = a if a < 0x80000000 else a - 0x100000000
        sb = b if b < 0x80000000 else b - 0x100000000
        sr = res if res < 0x80000000 else res - 0x100000000
        self.cpsr_v = 1 if (sa + sb) != sr else 0
        return res

    def _shift(self, val: int, stype: int, amt: int) -> int:
        val &= 0xFFFFFFFF
        if amt == 0:
            return val
        if stype == 0:  # LSL
            return (val << amt) & 0xFFFFFFFF
        if stype == 1:  # LSR
            return (val >> amt) & 0xFFFFFFFF
        if stype == 2:  # ASR
            s = val if val < 0x80000000 else val - 0x100000000
            return (s >> amt) & 0xFFFFFFFF
        # ROR
        return ((val >> amt) | (val << (32 - amt))) & 0xFFFFFFFF

    def step(self) -> None:
        pc = self.regs[15]
        insn = self.read32(pc)
        self.regs[15] = (pc + 4) & 0xFFFFFFFF
        self.steps += 1

        cond = (insn >> 28) & 0xF
        if not self._cond_ok(cond):
            return

        # BX Rn
        if (insn & 0x0FFFFFF0) == 0x012FFF10:
            rn = insn & 0xF
            self.regs[15] = self.regs[rn] & ~3
            return

        # Branch / BL
        if (insn & 0x0E000000) == 0x0A000000:
            if insn & (1 << 24):
                self.regs[14] = (pc + 4) & 0xFFFFFFFF
            imm24 = insn & 0x00FFFFFF
            if imm24 & 0x800000:
                imm24 -= 0x1000000
            self.regs[15] = (pc + 8 + (imm24 << 2)) & 0xFFFFFFFF
            return

        # Block Data Transfer (PUSH / POP)
        if (insn & 0x0E000000) == 0x08000000:
            p_bit = (insn >> 24) & 1
            u_bit = (insn >> 23) & 1
            w_bit = (insn >> 21) & 1
            l_bit = (insn >> 20) & 1
            rn = (insn >> 16) & 0xF
            mask = insn & 0xFFFF
            regs_list = [r for r in range(16) if mask & (1 << r)]
            base = self.regs[rn]
            if u_bit == 0:  # Decrement (STMDB / PUSH)
                addr = (base - 4 * len(regs_list)) & 0xFFFFFFFF
                if w_bit:
                    self.regs[rn] = addr
                for r in regs_list:
                    self.write32(addr, self.regs[r])
                    addr = (addr + 4) & 0xFFFFFFFF
            else:  # Increment (LDMIA / POP)
                addr = base
                for r in regs_list:
                    if l_bit:
                        self.regs[r] = self.read32(addr)
                    else:
                        self.write32(addr, self.regs[r])
                    addr = (addr + 4) & 0xFFFFFFFF
                if w_bit:
                    self.regs[rn] = addr
            return

        # Multiply (MUL)
        if (insn & 0x0FC000F0) == 0x00000090:
            rd = (insn >> 16) & 0xF
            rs = (insn >> 8) & 0xF
            rm = insn & 0xF
            res = (self.regs[rm] * self.regs[rs]) & 0xFFFFFFFF
            self.regs[rd] = res
            if insn & (1 << 20):
                self._set_nz(res)
            return

        # Halfword Transfer (LDRH / STRH)
        if (insn & 0x0E000090) == 0x00000090 and ((insn >> 5) & 3) != 0:
            u_bit = (insn >> 23) & 1
            i_bit = (insn >> 22) & 1
            l_bit = (insn >> 20) & 1
            rn = (insn >> 16) & 0xF
            rd = (insn >> 12) & 0xF
            off = (((insn >> 4) & 0xF0) | (insn & 0xF)) if i_bit else self.regs[insn & 0xF]
            base = (pc + 8) if rn == 15 else self.regs[rn]
            addr = (base + off if u_bit else base - off) & 0xFFFFFFFF
            if l_bit:
                self.regs[rd] = self.read16(addr)
            else:
                self.write16(addr, self.regs[rd])
            return

        # Single Data Transfer (LDR / STR / LDRB / STRB)
        if (insn & 0x0C000000) == 0x04000000:
            i_bit = (insn >> 25) & 1
            u_bit = (insn >> 23) & 1
            b_bit = (insn >> 22) & 1
            l_bit = (insn >> 20) & 1
            rn = (insn >> 16) & 0xF
            rd = (insn >> 12) & 0xF
            if i_bit == 0:
                off = insn & 0xFFF
            else:
                rm = insn & 0xF
                st = (insn >> 5) & 3
                sa = (insn >> 7) & 0x1F
                off = self._shift(self.regs[rm], st, sa)
            base = (pc + 8) if rn == 15 else self.regs[rn]
            addr = (base + off if u_bit else base - off) & 0xFFFFFFFF
            if l_bit:
                self.regs[rd] = self.read8(addr) if b_bit else self.read32(addr)
            else:
                if b_bit:
                    self.write8(addr, self.regs[rd])
                else:
                    self.write32(addr, self.regs[rd])
            return

        # Data Processing
        if (insn & 0x0C000000) == 0x00000000:
            i_bit = (insn >> 25) & 1
            op = (insn >> 21) & 0xF
            s_bit = (insn >> 20) & 1
            rn = (insn >> 16) & 0xF
            rd = (insn >> 12) & 0xF
            a = (pc + 8) if rn == 15 else self.regs[rn]
            if i_bit:
                rot = ((insn >> 8) & 0xF) * 2
                imm8 = insn & 0xFF
                op2 = ((imm8 >> rot) | (imm8 << (32 - rot))) & 0xFFFFFFFF if rot else imm8
            else:
                rm = insn & 0xF
                st = (insn >> 5) & 3
                sa = (insn >> 7) & 0x1F
                op2 = self._shift(self.regs[rm], st, sa)

            if op == 0x0:  # AND
                r = a & op2
                self.regs[rd] = r
                if s_bit: self._set_nz(r)
            elif op == 0x1:  # EOR
                r = a ^ op2
                self.regs[rd] = r
                if s_bit: self._set_nz(r)
            elif op == 0x2:  # SUB
                r = self._set_sub_flags(a, op2) if s_bit else (a - op2) & 0xFFFFFFFF
                self.regs[rd] = r
            elif op == 0x3:  # RSB
                r = self._set_sub_flags(op2, a) if s_bit else (op2 - a) & 0xFFFFFFFF
                self.regs[rd] = r
            elif op == 0x4:  # ADD
                r = self._set_add_flags(a, op2) if s_bit else (a + op2) & 0xFFFFFFFF
                self.regs[rd] = r
            elif op == 0x8:  # TST
                self._set_nz(a & op2)
            elif op == 0xA:  # CMP
                self._set_sub_flags(a, op2)
            elif op == 0xB:  # CMN
                self._set_add_flags(a, op2)
            elif op == 0xC:  # ORR
                r = a | op2
                self.regs[rd] = r
                if s_bit: self._set_nz(r)
            elif op == 0xD:  # MOV
                self.regs[rd] = op2
                if s_bit: self._set_nz(op2)
            elif op == 0xE:  # BIC
                r = a & (~op2 & 0xFFFFFFFF)
                self.regs[rd] = r
                if s_bit: self._set_nz(r)
            elif op == 0xF:  # MVN
                r = (~op2) & 0xFFFFFFFF
                self.regs[rd] = r
                if s_bit: self._set_nz(r)
            else:
                raise RuntimeError(f"Unhandled DP op {op} at 0x{pc:08X}")
            return

        raise RuntimeError(f"Unhandled ARM instruction 0x{insn:08X} at 0x{pc:08X}")

    def run_frames(self, count: int, max_steps_per_frame: int = 200000) -> None:
        for _ in range(count):
            start_frame = struct.unpack_from("<I", self.iwram, 0x58)[0]
            for _ in range(max_steps_per_frame):
                self.step()
                cur_frame = struct.unpack_from("<I", self.iwram, 0x58)[0]
                if cur_frame > start_frame:
                    # Finish the rest of this frame until next VBlank wait
                    for _ in range(12000):
                        self.step()
                        if self.read16(0x04000000) in (0x1340, 0x1740) and self.vcount == 0 and self.steps % 5 == 0:
                            break
                    break
            else:
                raise AssertionError(f"ROM frame loop stalled at PC=0x{self.regs[15]:08X}")

    def oam_entry(self, idx: int) -> tuple[int, int, int]:
        a0, a1, a2 = struct.unpack_from("<HHH", self.oam, idx * 8)
        return a0, a1, a2


def test_gba_rom_hardware_execution() -> None:
    print("[1/5] Compiling & executing real ARM7TDMI .gba ROM in GBA CPU verifier...")
    proj = create_starter_project("GBA Platformer")
    with tempfile.TemporaryDirectory() as td:
        rom_path = os.path.join(td, "starbit.gba")
        rep = compile_gba_rom(proj, rom_path)
        with open(rom_path, "rb") as f:
            rom = f.read()

        # Verify authentic GBA cartridge header
        assert len(rom) >= 32768 and len(rom) % 32768 == 0
        assert rom[0x04:0xA0] == GBA_NINTENDO_LOGO, "GBA Nintendo logo mismatch!"
        assert rom[0xB2] == 0x96, "GBA fixed 0x96 byte missing!"
        assert rom[0xBD] == compute_gba_header_checksum(rom[:0xC0]), "GBA checksum invalid!"

        cpu = MiniGbaCpu(rom)
        cpu.set_buttons([])
        cpu.run_frames(6)

        # Verify hardware display & sound initialized (v2.0 Mode 0 + BG0 + BG1 + BG2 + OBJ = 0x1740)
        dispcnt = struct.unpack_from("<H", cpu.io, 0x00)[0]
        bg0cnt = struct.unpack_from("<H", cpu.io, 0x08)[0]
        bg1cnt = struct.unpack_from("<H", cpu.io, 0x0A)[0]
        bg2cnt = struct.unpack_from("<H", cpu.io, 0x0C)[0]
        bldcnt = struct.unpack_from("<H", cpu.io, 0x50)[0]
        sndx = struct.unpack_from("<H", cpu.io, 0x84)[0]
        assert dispcnt == 0x1740, f"Unexpected REG_DISPCNT: 0x{dispcnt:04X}"
        assert bg0cnt == 0x5C01, f"Unexpected REG_BG0CNT: 0x{bg0cnt:04X}"
        assert bg1cnt == 0x1E04, f"Unexpected REG_BG1CNT: 0x{bg1cnt:04X}"
        assert bg2cnt == 0x1A02, f"Unexpected REG_BG2CNT: 0x{bg2cnt:04X}"
        assert bldcnt == 0x2044, f"Unexpected REG_BLDCNT: 0x{bldcnt:04X}"
        assert sndx == 0x0080, f"Unexpected REG_SOUNDCNT_X: 0x{sndx:04X}"
        assert b"SRAM_V113" in rom, "Official GBA SRAM_V113 identifier missing!"

        # Hero OAM[0] visible & standing on ground
        a0_0, a1_0, a2_0 = cpu.oam_entry(0)
        assert (a0_0 & 0x0200) == 0, "Hero OAM[0] should be visible!"
        x0 = a1_0 & 0x1FF
        y0 = a0_0 & 0xFF

        # Hold RIGHT for 10 frames -> hero must walk right!
        cpu.set_buttons(["RIGHT"])
        cpu.run_frames(10)
        a0_r, a1_r, _ = cpu.oam_entry(0)
        xr = a1_r & 0x1FF
        assert xr > x0, f"Holding RIGHT should move hero right: {x0} -> {xr}"

        # Press A (Jump) -> hero Y must go UP and Channel 1 PSG Jump SFX must trigger!
        cpu.set_buttons(["A"])
        cpu.run_frames(3)
        a0_j, _, _ = cpu.oam_entry(0)
        yj = a0_j & 0xFF
        assert yj < y0, f"Pressing A should make hero jump UP: {y0} -> {yj}"
        assert cpu.sfx1_triggers >= 1, "Jump button should trigger GBA PSG Channel 1 SFX!"
        assert cpu.sfx2_triggers >= 1, "Embedded Sequence Genie BGM should trigger GBA PSG Channel 2!"

        # Press B (Fireball) -> OAM[1] projectile becomes visible!
        cpu.set_buttons(["B"])
        cpu.run_frames(2)
        pa0, pa1, _ = cpu.oam_entry(1)
        assert (pa0 & 0x0200) == 0, "Pressing B should spawn visible projectile in OAM[1]!"

        # Press SELECT -> hero OBJ palette cycles from 0 to 1!
        cpu.set_buttons(["SELECT"])
        cpu.run_frames(2)
        _, _, a2_p = cpu.oam_entry(0)
        pal_slot = (a2_p >> 12) & 0xF
        assert pal_slot == 1, f"Pressing SELECT should cycle hero palette to 1, got {pal_slot}"

        # Also test GB Classic & GBC targets compiled to .gba + native .gb/.gbc + C header
        gb_proj = create_starter_project("GB Classic (DMG)")
        gb_gba = os.path.join(td, "dmg_on_gba.gba")
        compile_gba_rom(gb_proj, gb_gba)
        with open(gb_gba, "rb") as f:
            gb_cpu = MiniGbaCpu(f.read())
        gb_cpu.run_frames(2)
        # Verify bezel tile written at BG1 (0, 0) = VRAM 0xF000
        bezel_hw = struct.unpack_from("<H", gb_cpu.vram, 0xF000)[0]
        assert (bezel_hw & 0x3FF) > 0, "GB target compiled to .gba should render bezel frame on BG1!"

        native_gb = os.path.join(td, "dmg.gb")
        compile_gb_rom(gb_proj, native_gb)
        with open(native_gb, "rb") as f:
            gb_bytes = f.read()
        assert len(gb_bytes) == 32768
        assert gb_bytes[0x0104:0x0134] == GB_NINTENDO_LOGO
        hchk = 0
        for a in range(0x0134, 0x014D):
            hchk = (hchk - gb_bytes[a] - 1) & 0xFF
        assert gb_bytes[0x014D] == hchk

        c_hdr = export_c_source(proj, td)
        assert os.path.isfile(c_hdr)
        print(f"    PASS! Executed {cpu.steps:,} ARM7TDMI instructions cleanly (ROM {rep.rom_size // 1024} KB, Checksum {rep.checksum_hex})")


def test_metroidvania_v2_gba_hardware() -> None:
    print("[1b/6] Verifying BSL Fusion Metroidvania ROM (16x32 Hero, Morph, 8-Way Aim, Doors, SRAM, Boss, DMA, Dialogue)...")
    from kinopixel.gba_compiler import ST_ABILITIES, ST_DIALOG_ON, ST_MORPHED, ST_PROJS, ST_PX, ST_PY, ST_ROOM_IDX
    proj = create_starter_project("GBA Metroidvania (BSL Sector)")
    assert len(proj.rooms) == 3
    with tempfile.TemporaryDirectory() as td:
        rom_path = os.path.join(td, "bsl_fusion.gba")
        rep = compile_gba_rom(proj, rom_path)
        assert rep.rooms_compiled == 3
        with open(rom_path, "rb") as f:
            rom = f.read()

        cpu = MiniGbaCpu(rom)
        cpu.set_buttons([])
        cpu.run_frames(5)

        # 1. Verify 16x32 Tall Hero Metasprite OAM attributes
        a0, a1, _ = cpu.oam_entry(0)
        assert (a0 & 0x8000) == 0x8000 and (a1 & 0x8000) == 0x8000, f"Expected 16x32 tall hero OAM, got 0x{a0:04X}/0x{a1:04X}"

        # 2. Walk right into Adam Navigation Terminal -> triggers BG1 Dialogue Box!
        cpu.set_buttons(["RIGHT"])
        cpu.run_frames(22)
        dlg_on = struct.unpack_from("<I", cpu.iwram, ST_DIALOG_ON)[0]
        assert dlg_on == 1, "Stepping on Navigation Terminal must open BG1 dialogue box!"
        # Dismiss dialogue with A!
        cpu.set_buttons(["A"])
        cpu.run_frames(2)
        assert struct.unpack_from("<I", cpu.iwram, ST_DIALOG_ON)[0] == 0, "Pressing A must dismiss dialogue!"

        # 3. Walk right into Save Station -> writes checksummed 'KPS2' block into GBA Cartridge SRAM 0x0E000000!
        cpu.set_buttons(["RIGHT"])
        cpu.run_frames(42)
        assert cpu.sram[0:4] == b"KPS2", f"Save Station must write KPS2 SRAM magic, got {cpu.sram[0:4]!r}"
        saved_sram = bytes(cpu.sram)

        # 4. Test 8-way / upward Arm Cannon aim (hold L + press B -> projectile vy < 0!)
        cpu.set_buttons(["L", "B"])
        cpu.run_frames(2)
        p_vy_flags = struct.unpack_from("<I", cpu.iwram, ST_PROJS + 16)[0]
        p_vy = p_vy_flags & 0xFFFF
        if p_vy & 0x8000:
            p_vy -= 0x10000
        assert p_vy < 0, f"Holding L + B should fire upward Arm Cannon shot (vy < 0), got vy={p_vy}"

        # 5. Grant Morph Ball ability -> press SELECT -> hero shrinks to 16x16 Morph Ball OAM!
        struct.pack_into("<I", cpu.iwram, ST_ABILITIES, 0x03)
        cpu.set_buttons(["SELECT"])
        cpu.run_frames(2)
        assert struct.unpack_from("<I", cpu.iwram, ST_MORPHED)[0] == 1, "SELECT should activate Morph Ball!"
        a0_m, a1_m, _ = cpu.oam_entry(0)
        assert (a0_m & 0x8000) == 0 and (a1_m & 0xC000) == 0x4000, "Morphed hero must switch OAM to 16x16 Morph Ball!"

        # 6. Teleport right into East Hatch (tile_x=42 -> hero left edge 41*8 so center x+8 lands on col 42!) -> warps to Room 1!
        struct.pack_into("<I", cpu.iwram, ST_PX, (41 * 8) << 8)
        struct.pack_into("<I", cpu.iwram, ST_PY, (16 * 8) << 8)
        cpu.set_buttons([])
        cpu.run_frames(2)
        assert struct.unpack_from("<I", cpu.iwram, ST_ROOM_IDX)[0] == 1, "Entering East Hatch must warp to Room 1!"

        # 7. Reboot fresh GBA CPU with persisted SRAM -> auto-restores saved KPS2 game!
        cpu2 = MiniGbaCpu(rom)
        cpu2.sram[:] = saved_sram
        cpu2.run_frames(3)
        assert struct.unpack_from("<I", cpu2.iwram, ST_PX)[0] > (4 * 8) << 8, "Rebooting with valid SRAM should restore saved position!"

        # 8. Test live playtester through all 3 rooms & Direct Sound DMA callback!
        dma_fired = []
        sim = GamePlaytestEngine(proj, on_dma=lambda: dma_fired.append(1))
        sim.load_room(2)  # Boss Chamber
        assert any(e.is_32 and e.hp == 12 for e in sim.enemies)
        rgb = sim.render_rgb()
        assert rgb.shape == (160, 240, 3)
        print(f"    PASS! Executed {cpu.steps:,} ARM7TDMI Metroidvania instructions (ROM {rep.rom_size // 1024} KB, 3 Rooms, SRAM + BG2 + DMA + Boss)")


def test_project_roundtrip_and_undo() -> None:
    print("[2/5] Testing .kpx save/load, undo/redo, and all 4 starter templates...")
    for tpl in ("GBA Platformer", "GBA Top-Down RPG", "GBC Adventure", "GB Classic (DMG)"):
        p = create_starter_project(tpl)
        p.title = "TESTGAME"
        p.snapshot_push("Rename")
        assert p.can_undo()
        p.undo()
        assert p.title != "TESTGAME"
        p.redo()
        assert p.title == "TESTGAME"
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test.kpx")
            p.save_kpx(fp)
            loaded = KinoPixelProject.load_kpx(fp)
            assert loaded.title == "TESTGAME"
            assert loaded.target_system == p.target_system
            assert len(loaded.sprites) == len(p.sprites)
            assert len(loaded.button_rules) == len(p.button_rules)
    print("    PASS!")


def test_chiptune_synth() -> None:
    print("[3/5] Testing hardware PSG chiptune synthesizer & Sequence Genie...")
    from kinopixel.sequence_genie import (
        GENIE_SCALES,
        export_genie_wav,
        mutate_phrase,
        render_genie_loop,
        reroll_chord_progression,
        reroll_phrase,
    )
    proj = create_starter_project("GBA Platformer")
    for patch in proj.sfx_list:
        w = synthesize_sfx_waveform(patch)
        assert len(w) > 500
        assert float(abs(w).max()) > 0.01

    assert len(GENIE_SCALES) == 19
    g = proj.sequence_genie
    g.steps[0].locked = True
    locked_note = g.steps[0].note
    reroll_phrase(g, seed=123)
    assert g.steps[0].note == locked_note, "Sequence Genie Reroll must respect locked steps!"
    mutate_phrase(g, seed=456)
    assert g.steps[0].note == locked_note, "Sequence Genie Mutate must respect locked steps!"
    reroll_chord_progression(g, seed=789)
    g.save_slot(2)
    assert g.recall_slot(2)
    loop_pcm = render_genie_loop(g, bars=2)
    assert len(loop_pcm) > 20000 and float(abs(loop_pcm).max()) > 0.05
    with tempfile.TemporaryDirectory() as td:
        wav_p = export_genie_wav(g, os.path.join(td, "genie.wav"), bars=2)
        assert os.path.isfile(wav_p) and os.path.getsize(wav_p) > 40000
    print("    PASS!")


def test_live_playtest_engine() -> None:
    print("[4/5] Testing 60fps live playtest engine...")
    proj = create_starter_project("GBA Platformer")
    sfx_events: list[int] = []
    sim = GamePlaytestEngine(proj, on_sfx=lambda i: sfx_events.append(i))
    for _ in range(10):
        sim.step(set())
    x0 = sim.px
    for _ in range(15):
        sim.step({"RIGHT"})
    assert sim.px > x0
    sim.step({"A"})
    assert sim.vy < 0
    assert len(sfx_events) >= 1
    rgb = sim.render_rgb()
    assert rgb.shape == (160, 240, 3)
    print("    PASS!")


def test_headless_studio_ui() -> None:
    print("[5/5] Testing headless KinoPixel Qt Studio UI & ROM build flow...")
    from PySide6.QtWidgets import QApplication
    from kinopixel.mainwindow import KinoPixelWindow

    app = QApplication.instance() or QApplication([])
    win = KinoPixelWindow()
    for idx in range(5):
        win.stage_tabs.setCurrentIndex(idx)
        app.processEvents()
    win._apply_theme("Light")
    win._apply_theme("High Contrast")
    win._apply_theme("Dark")
    with tempfile.TemporaryDirectory() as td:
        out_rom = os.path.join(td, "ui_build.gba")
        rep = win.page_play.build_gba_dialog(default_path=out_rom)
        assert rep is not None and os.path.isfile(out_rom)
    win.close()
    print("    PASS!")


if __name__ == "__main__":
    test_gba_rom_hardware_execution()
    test_metroidvania_v2_gba_hardware()
    test_project_roundtrip_and_undo()
    test_chiptune_synth()
    test_live_playtest_engine()
    test_headless_studio_ui()
    print("\nALL KINOPIXEL v2.0 TESTS PASSED!")
