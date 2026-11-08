#!/usr/bin/env python3
"""RV32I assembler for the Logisim CPU.

    python3 tools/asm/rvasm.py prog.s                 # writes prog.hex (+ prog.data.hex)
    python3 tools/asm/rvasm.py prog.s --circ project.circ   # also loads it into every IMEM ROM

Supported instructions: the CPU's ISA
    add sub and or xor slt sltu sll srl sra
    addi andi ori xori slti sltiu slli srli srai
    lw sw   beq bne blt bge bltu bgeu   jal jalr   lui auipc   ecall ebreak
and the pseudo-instructions
    nop li la mv not neg seqz snez j jr ret call
    beqz bnez blez bgez bltz bgtz bgt ble bgtu bleu
Directives: .text .data .word .space/.zero .align (ignored in .text) .globl (ignored)
Comments start with '#' or '//'. Labels end with ':'.

Instruction memory starts at 0x0. The data section is a separate memory that
also starts at 0x0 (Harvard); `la` gives addresses inside it.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

REGS = {f"x{i}": i for i in range(32)}
REGS.update({n: i for i, n in enumerate(
    "zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6".split())})
REGS["fp"] = 8

R_OPS = {  # funct3, funct7
    "add": (0, 0x00), "sub": (0, 0x20), "sll": (1, 0x00), "slt": (2, 0x00), "sltu": (3, 0x00),
    "xor": (4, 0x00), "srl": (5, 0x00), "sra": (5, 0x20), "or": (6, 0x00), "and": (7, 0x00),
}
I_OPS = {"addi": 0, "slti": 2, "sltiu": 3, "xori": 4, "ori": 6, "andi": 7}
SHIFT_I = {"slli": (1, 0x00), "srli": (5, 0x00), "srai": (5, 0x20)}
BRANCHES = {"beq": 0, "bne": 1, "blt": 4, "bge": 5, "bltu": 6, "bgeu": 7}
UNSUPPORTED = {"lb", "lh", "lbu", "lhu", "sb", "sh", "mul", "div", "rem", "fence", "csrrw", "csrrs"}

ROM_WORDS = 1 << 10
RAM_WORDS = 1 << 10


class AsmError(Exception):
    pass


def reg(tok):
    t = tok.strip().lower()
    if t not in REGS:
        raise AsmError(f"unknown register {tok!r}")
    return REGS[t]


def fits_signed(v, bits):
    return -(1 << (bits - 1)) <= v < (1 << (bits - 1))


class Assembler:
    def __init__(self):
        self.labels: dict[str, tuple[str, int]] = {}
        self.text: list[tuple[int, str, list[str], int, str]] = []  # (addr, mnemonic, args, lineno, src)
        self.data: dict[int, int] = {}

    # -- pass 1: sizes and labels -------------------------------------------------
    def size_of(self, mn, args):
        if mn == "li":
            v = self.number(args[1], allow_label=False)
            return 4 if fits_signed(v, 12) else 8
        if mn in ("la", "call"):
            return 8 if mn == "la" else 4
        return 4

    def parse(self, src: str):
        section, pc, dpc = "text", 0, 0
        for lineno, raw in enumerate(src.splitlines(), 1):
            line = re.split(r"#|//", raw, maxsplit=1)[0].strip()
            while True:
                m = re.match(r"^([A-Za-z_.$][\w.$]*)\s*:\s*(.*)$", line)
                if not m:
                    break
                name = m.group(1)
                if name in self.labels:
                    raise AsmError(f"line {lineno}: label {name!r} defined twice")
                self.labels[name] = (section, pc if section == "text" else dpc)
                line = m.group(2).strip()
            if not line:
                continue
            parts = line.split(None, 1)
            mn = parts[0].lower()
            args = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []
            try:
                if mn.startswith("."):
                    if mn == ".text":
                        section = "text"
                    elif mn == ".data":
                        section = "data"
                    elif mn == ".word":
                        if section != "data":
                            raise AsmError(".word is only supported in .data")
                        for a in args:
                            self.data[dpc // 4] = ("expr", a, lineno)
                            dpc += 4
                    elif mn in (".space", ".zero"):
                        n = self.number(args[0], allow_label=False)
                        if section != "data" or n % 4:
                            raise AsmError(f"{mn} needs a multiple of 4 in .data")
                        dpc += n
                    elif mn in (".align", ".globl", ".global", ".section", ".type", ".size"):
                        pass
                    else:
                        raise AsmError(f"unknown directive {mn}")
                    continue
                if section != "text":
                    raise AsmError("instructions must be in .text")
                if mn in UNSUPPORTED:
                    raise AsmError(f"{mn} is not implemented by this CPU (only lw/sw, base RV32I)")
                self.text.append((pc, mn, args, lineno, raw.strip()))
                pc += self.size_of(mn, args)
            except AsmError as e:
                raise AsmError(f"line {lineno}: {e}") from None
        if pc // 4 > ROM_WORDS:
            raise AsmError(f"program is {pc // 4} words; instruction memory holds {ROM_WORDS}")
        if dpc // 4 > RAM_WORDS:
            raise AsmError(f"data is {dpc // 4} words; data memory holds {RAM_WORDS}")

    def number(self, tok, allow_label=True, pc=None):
        t = tok.strip()
        m = re.match(r"^%(hi|lo)\((.+)\)$", t)
        if m:
            v = self.number(m.group(2), allow_label, pc)
            hi = (v + 0x800) >> 12
            return hi & 0xFFFFF if m.group(1) == "hi" else v - (hi << 12)
        try:
            return int(t, 0)
        except ValueError:
            pass
        if re.match(r"^'.'$", t):
            return ord(t[1])
        if allow_label and t in self.labels:
            return self.labels[t][1]
        raise AsmError(f"bad number or unknown label {tok!r}")

    # -- pass 2: encoding ---------------------------------------------------------
    @staticmethod
    def enc_r(f7, rs2, rs1, f3, rd, op):
        return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

    @staticmethod
    def enc_i(imm, rs1, f3, rd, op):
        if not fits_signed(imm, 12):
            raise AsmError(f"immediate {imm} does not fit in 12 bits")
        return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

    @staticmethod
    def enc_s(imm, rs2, rs1, f3, op):
        if not fits_signed(imm, 12):
            raise AsmError(f"offset {imm} does not fit in 12 bits")
        imm &= 0xFFF
        return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 0x1F) << 7) | op

    @staticmethod
    def enc_b(off, rs2, rs1, f3):
        if off % 2 or not fits_signed(off, 13):
            raise AsmError(f"branch offset {off} out of range")
        o = off & 0x1FFF
        return (((o >> 12) & 1) << 31) | (((o >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) \
            | (((o >> 1) & 0xF) << 8) | (((o >> 11) & 1) << 7) | 0x63

    @staticmethod
    def enc_u(imm20, rd, op):
        return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | op

    @staticmethod
    def enc_j(off, rd):
        if off % 2 or not fits_signed(off, 21):
            raise AsmError(f"jump offset {off} out of range")
        o = off & 0x1FFFFF
        return (((o >> 20) & 1) << 31) | (((o >> 1) & 0x3FF) << 21) | (((o >> 11) & 1) << 20) \
            | (((o >> 12) & 0xFF) << 12) | (rd << 7) | 0x6F

    def mem_operand(self, tok):
        m = re.match(r"^(.*)\((\w+)\)$", tok.replace(" ", ""))
        if not m:
            raise AsmError(f"expected offset(reg), got {tok!r}")
        off = self.number(m.group(1)) if m.group(1) else 0
        return off, reg(m.group(2))

    def target(self, tok, pc):
        t = tok.strip()
        if t in self.labels:
            sec, addr = self.labels[t]
            if sec != "text":
                raise AsmError(f"{t!r} is a data label, not a code label")
            return addr - pc
        return self.number(t)

    def expand(self, pc, mn, a):
        """Return a list of machine words for one source line."""
        n = len(a)

        def need(k):
            if n != k:
                raise AsmError(f"{mn} expects {k} operands, got {n}")

        if mn in R_OPS:
            need(3)
            f3, f7 = R_OPS[mn]
            return [self.enc_r(f7, reg(a[2]), reg(a[1]), f3, reg(a[0]), 0x33)]
        if mn in I_OPS:
            need(3)
            return [self.enc_i(self.number(a[2]), reg(a[1]), I_OPS[mn], reg(a[0]), 0x13)]
        if mn in SHIFT_I:
            need(3)
            f3, f7 = SHIFT_I[mn]
            sh = self.number(a[2])
            if not 0 <= sh < 32:
                raise AsmError("shift amount must be 0..31")
            return [self.enc_r(f7, sh, reg(a[1]), f3, reg(a[0]), 0x13)]
        if mn == "lw":
            need(2)
            off, rs1 = self.mem_operand(a[1])
            return [self.enc_i(off, rs1, 2, reg(a[0]), 0x03)]
        if mn == "sw":
            need(2)
            off, rs1 = self.mem_operand(a[1])
            return [self.enc_s(off, reg(a[0]), rs1, 2, 0x23)]
        if mn in BRANCHES:
            need(3)
            return [self.enc_b(self.target(a[2], pc), reg(a[1]), reg(a[0]), BRANCHES[mn])]
        if mn == "jal":
            if n == 1:
                return [self.enc_j(self.target(a[0], pc), 1)]
            need(2)
            return [self.enc_j(self.target(a[1], pc), reg(a[0]))]
        if mn == "jalr":
            if n == 1:
                return [self.enc_i(0, reg(a[0]), 0, 1, 0x67)]
            if n == 2 and "(" in a[1]:
                off, rs1 = self.mem_operand(a[1])
                return [self.enc_i(off, rs1, 0, reg(a[0]), 0x67)]
            need(3)
            return [self.enc_i(self.number(a[2]), reg(a[1]), 0, reg(a[0]), 0x67)]
        if mn in ("lui", "auipc"):
            need(2)
            v = self.number(a[1])
            if not 0 <= v < (1 << 20) and not fits_signed(v, 20):
                raise AsmError(f"{mn} immediate {v} does not fit in 20 bits")
            return [self.enc_u(v, reg(a[0]), 0x37 if mn == "lui" else 0x17)]
        if mn == "ecall":
            return [0x00000073]
        if mn == "ebreak":
            return [0x00100073]
        # pseudo-instructions
        if mn == "nop":
            return [self.enc_i(0, 0, 0, 0, 0x13)]
        if mn == "li":
            need(2)
            rd, v = reg(a[0]), self.number(a[1], allow_label=False)
            if not fits_signed(v, 32) and not 0 <= v <= 0xFFFFFFFF:
                raise AsmError(f"li value {v} does not fit in 32 bits")
            v = ((v + (1 << 31)) & 0xFFFFFFFF) - (1 << 31)
            if fits_signed(v, 12):
                return [self.enc_i(v, 0, 0, rd, 0x13)]
            hi = ((v + 0x800) >> 12) & 0xFFFFF
            lo = v - (((v + 0x800) >> 12) << 12)
            return [self.enc_u(hi, rd, 0x37), self.enc_i(lo, rd, 0, rd, 0x13)]
        if mn == "la":
            need(2)
            rd = reg(a[0])
            if a[1] not in self.labels:
                raise AsmError(f"unknown label {a[1]!r}")
            sec, addr = self.labels[a[1]]
            if sec == "text":  # pc-relative code address
                off = addr - pc
                hi = (off + 0x800) >> 12
                return [self.enc_u(hi, rd, 0x17), self.enc_i(off - (hi << 12), rd, 0, rd, 0x13)]
            hi = (addr + 0x800) >> 12
            return [self.enc_u(hi, rd, 0x37), self.enc_i(addr - (hi << 12), rd, 0, rd, 0x13)]
        if mn == "mv":
            need(2)
            return [self.enc_i(0, reg(a[1]), 0, reg(a[0]), 0x13)]
        if mn == "not":
            need(2)
            return [self.enc_i(-1, reg(a[1]), 4, reg(a[0]), 0x13)]
        if mn == "neg":
            need(2)
            return [self.enc_r(0x20, reg(a[1]), 0, 0, reg(a[0]), 0x33)]
        if mn == "seqz":
            need(2)
            return [self.enc_i(1, reg(a[1]), 3, reg(a[0]), 0x13)]
        if mn == "snez":
            need(2)
            return [self.enc_r(0, reg(a[1]), 0, 3, reg(a[0]), 0x33)]
        if mn == "j":
            need(1)
            return [self.enc_j(self.target(a[0], pc), 0)]
        if mn == "call":
            need(1)
            return [self.enc_j(self.target(a[0], pc), 1)]
        if mn == "jr":
            need(1)
            return [self.enc_i(0, reg(a[0]), 0, 0, 0x67)]
        if mn == "ret":
            return [self.enc_i(0, 1, 0, 0, 0x67)]
        zero_br = {"beqz": ("beq", 0), "bnez": ("bne", 0), "bltz": ("blt", 0), "bgez": ("bge", 0),
                   "blez": ("bge", 1), "bgtz": ("blt", 1)}
        if mn in zero_br:
            need(2)
            base, swap = zero_br[mn]
            r = reg(a[0])
            rs1, rs2 = (0, r) if swap else (r, 0)
            return [self.enc_b(self.target(a[1], pc), rs2, rs1, BRANCHES[base])]
        swapped = {"bgt": "blt", "ble": "bge", "bgtu": "bltu", "bleu": "bgeu"}
        if mn in swapped:
            need(3)
            return [self.enc_b(self.target(a[2], pc), reg(a[0]), reg(a[1]), BRANCHES[swapped[mn]])]
        raise AsmError(f"unknown instruction {mn!r}")

    def assemble(self, src: str):
        self.parse(src)
        words, listing = [], []
        for pc, mn, args, lineno, raw in self.text:
            try:
                ws = self.expand(pc, mn, args)
            except AsmError as e:
                raise AsmError(f"line {lineno}: {e}") from None
            if len(ws) * 4 != self.size_of(mn, args):
                raise AsmError(f"line {lineno}: internal size mismatch")
            for k, w in enumerate(ws):
                listing.append((pc + 4 * k, w, raw if k == 0 else ""))
            words += ws
        data = {}
        for idx, (_, expr, lineno) in self.data.items():
            try:
                data[idx] = self.number(expr) & 0xFFFFFFFF
            except AsmError as e:
                raise AsmError(f"line {lineno}: {e}") from None
        return words, data, listing


# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------
def logisim_image(words: list[int]) -> str:
    """Logisim 'v3.0 hex words addressed' memory image."""
    lines = ["v3.0 hex words addressed"]
    for base in range(0, len(words), 8):
        chunk = " ".join(f"{w:08x}" for w in words[base:base + 8])
        lines.append(f"{base:03x}: {chunk}")
    return "\n".join(lines) + "\n"


def rom_contents_attr(words: list[int], addr_bits=10) -> str:
    """Value of a ROM's 'contents' attribute inside a .circ file."""
    body = []
    for base in range(0, len(words), 8):
        body.append(" ".join(f"{w:x}" for w in words[base:base + 8]))
    return f"addr/data: {addr_bits} 32\n" + "\n".join(body) + ("\n" if body else "")


def patch_circ(path: str, words: list[int], label="IMEM") -> int:
    """Load the program into every ROM labelled `label` in a .circ file."""
    src = open(path).read()
    attr = rom_contents_attr(words).replace("\n", "&#10;")
    pat = re.compile(r'(<comp lib="5" loc="\([0-9,]+\)" name="ROM">)(.*?)(</comp>)', re.S)
    count = 0

    def repl(m):
        nonlocal count
        body = m.group(2)
        if f'<a name="label" val="{label}"/>' not in body:
            return m.group(0)
        count += 1
        body = re.sub(r'\s*<a name="contents">.*?</a>|\s*<a name="contents" val="[^"]*"/>', "", body, flags=re.S)
        return m.group(1) + f'\n      <a name="contents">{attr}</a>' + body + m.group(3)

    out = pat.sub(repl, src)
    if count == 0:
        raise SystemExit(f"no ROM labelled {label} found in {path}")
    with open(path, "w") as f:
        f.write(out)
    return count


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("-o", "--out", help="instruction image (default: <source>.hex)")
    ap.add_argument("--circ", help="also load the program into the IMEM ROMs of this .circ")
    ap.add_argument("--list", action="store_true", help="print an address/word/source listing")
    args = ap.parse_args()
    try:
        words, data, listing = Assembler().assemble(open(args.source).read())
    except AsmError as e:
        sys.exit(f"{args.source}: {e}")
    base = os.path.splitext(args.source)[0]
    out = args.out or base + ".hex"
    with open(out, "w") as f:
        f.write(logisim_image(words))
    print(f"{out}: {len(words)} instructions")
    if data:
        dwords = [data.get(i, 0) for i in range(max(data) + 1)]
        dout = os.path.splitext(out)[0] + ".data.hex"
        with open(dout, "w") as f:
            f.write(logisim_image(dwords))
        print(f"{dout}: {len(dwords)} data words")
    if args.list:
        for pc, w, src in listing:
            print(f"  {pc:04x}: {w:08x}   {src}")
    if args.circ:
        n = patch_circ(args.circ, words)
        print(f"{args.circ}: program loaded into {n} ROM(s)")


if __name__ == "__main__":
    main()
