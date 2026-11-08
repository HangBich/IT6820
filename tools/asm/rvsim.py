#!/usr/bin/env python3
"""Reference RV32I instruction-set simulator (golden model for the tests).

    python3 tools/asm/rvsim.py prog.s        # run and print registers / memory writes

Executes the same subset as the CPU, stops at ecall/ebreak, and records the
architectural events (register writes and memory stores) in program order.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rvasm import REGS, Assembler  # noqa: E402

M32 = 0xFFFFFFFF
ABI = {v: k for k, v in REGS.items() if not k.startswith("x") and k != "fp"}


def sx(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


class SimError(Exception):
    pass


def run(words, data=None, max_steps=100000):
    """Returns dict(regs, mem, reg_writes, mem_writes, steps, pc)."""
    regs = [0] * 32
    mem = dict(data or {})  # word index -> value (data memory is 1024 words)
    reg_writes, mem_writes = [], []
    pc = 0
    for steps in range(max_steps):
        if pc % 4 or not 0 <= pc // 4 < 1024:
            raise SimError(f"pc {pc:#x} out of instruction memory")
        ins = words[pc // 4] if pc // 4 < len(words) else 0
        op, rd, f3 = ins & 0x7F, (ins >> 7) & 31, (ins >> 12) & 7
        rs1, rs2, f7 = (ins >> 15) & 31, (ins >> 20) & 31, ins >> 25
        a, b = regs[rs1], regs[rs2]
        imm_i = sx(ins >> 20, 12)
        imm_s = sx(((ins >> 25) << 5) | ((ins >> 7) & 31), 12)
        imm_b = sx((((ins >> 31) & 1) << 12) | (((ins >> 7) & 1) << 11) | (((ins >> 25) & 0x3F) << 5)
                   | (((ins >> 8) & 0xF) << 1), 13)
        imm_u = ins & 0xFFFFF000
        imm_j = sx((((ins >> 31) & 1) << 20) | (((ins >> 12) & 0xFF) << 12) | (((ins >> 20) & 1) << 11)
                   | (((ins >> 21) & 0x3FF) << 1), 21)
        nxt = pc + 4
        result = None

        def alu(x, y, f3, alt):
            if f3 == 0:
                return x - y if alt else x + y
            if f3 == 1:
                return x << (y & 31)
            if f3 == 2:
                return int(sx(x, 32) < sx(y, 32))
            if f3 == 3:
                return int((x & M32) < (y & M32))
            if f3 == 4:
                return x ^ y
            if f3 == 5:
                return (sx(x, 32) >> (y & 31)) if alt else ((x & M32) >> (y & 31))
            if f3 == 6:
                return x | y
            return x & y

        if op == 0x33:
            result = alu(a, b, f3, f7 == 0x20)
        elif op == 0x13:
            result = alu(a, imm_i & M32, f3, f3 == 5 and f7 == 0x20)
        elif op == 0x03:
            if f3 != 2:
                raise SimError(f"pc {pc:#x}: only lw is supported")
            addr = (a + imm_i) & M32
            result = mem.get((addr >> 2) & 1023, 0)
        elif op == 0x23:
            if f3 != 2:
                raise SimError(f"pc {pc:#x}: only sw is supported")
            addr = (a + imm_s) & M32
            mem[(addr >> 2) & 1023] = b
            mem_writes.append((addr, b))
        elif op == 0x63:
            sa, sb = sx(a, 32), sx(b, 32)
            taken = {0: a == b, 1: a != b, 4: sa < sb, 5: sa >= sb, 6: a < b, 7: a >= b}.get(f3)
            if taken is None:
                raise SimError(f"pc {pc:#x}: bad branch funct3 {f3}")
            if taken:
                nxt = pc + imm_b
        elif op == 0x6F:
            result, nxt = pc + 4, pc + imm_j
        elif op == 0x67:
            result, nxt = pc + 4, (a + imm_i) & ~1
        elif op == 0x37:
            result = imm_u
        elif op == 0x17:
            result = pc + imm_u
        elif op == 0x73:
            return dict(regs=regs, mem=mem, reg_writes=reg_writes, mem_writes=mem_writes, steps=steps + 1, pc=pc)
        elif ins == 0:
            pass  # empty instruction memory behaves as a bubble
        else:
            raise SimError(f"pc {pc:#x}: unsupported instruction {ins:#010x}")
        if result is not None and rd:
            regs[rd] = result & M32
            reg_writes.append((rd, regs[rd]))
        pc = nxt & M32
    raise SimError(f"no ecall/ebreak within {max_steps} instructions")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    words, data, _ = Assembler().assemble(open(sys.argv[1]).read())
    r = run(words, data)
    print(f"halted at pc={r['pc']:#x} after {r['steps']} instructions")
    for i in range(32):
        if r["regs"][i]:
            print(f"  x{i:<2} ({ABI[i]:>4}) = 0x{r['regs'][i]:08x}  ({sx(r['regs'][i], 32)})")
    for addr, v in r["mem_writes"]:
        print(f"  mem[0x{addr:08x}] <- 0x{v:08x}")


if __name__ == "__main__":
    main()
