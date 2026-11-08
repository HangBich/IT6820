"""Generate Logisim test vectors (.vec) for every CPU module.

Expected values come from a Python model of RV32I written straight from the
spec, independent of the circuits. Run with run_module_tests.sh.
"""

import os
import random

OUT = os.path.dirname(os.path.abspath(__file__))
M32 = 0xFFFFFFFF
rnd = random.Random(2026)


def sx(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def h(v, bits=32):
    return f"0x{v & ((1 << bits) - 1):0{(bits + 3) // 4}x}"


def interesting32():
    return rnd.choice([0, 1, 2, 31, 32, 0x7FFFFFFF, 0x80000000, M32, 0xFFFFFFFE, 0x12345678,
                       rnd.getrandbits(32), rnd.getrandbits(32), rnd.getrandbits(5), sx(rnd.getrandbits(12), 12) & M32])


def write(name, header, rows):
    with open(os.path.join(OUT, f"{name}.vec"), "w") as f:
        f.write(" ".join(header) + "\n")
        for r in rows:
            f.write(" ".join(r) + "\n")
    print(f"{name}.vec: {len(rows)} vectors")


# --- ALU ------------------------------------------------------------------
ALU_OPS = {
    0: lambda a, b: a + b,
    1: lambda a, b: a - b,
    2: lambda a, b: a & b,
    3: lambda a, b: a | b,
    4: lambda a, b: a ^ b,
    5: lambda a, b: a << (b & 31),
    6: lambda a, b: a >> (b & 31),
    7: lambda a, b: sx(a, 32) >> (b & 31),
    8: lambda a, b: int(sx(a, 32) < sx(b, 32)),
    9: lambda a, b: int(a < b),
}


def alu_vectors():
    rows = []
    for op, fn in ALU_OPS.items():
        for _ in range(25):
            a, b = interesting32(), interesting32()
            rows.append([h(a), h(b), h(op, 4), h(fn(a, b) & M32)])
    write("ALU", ["rs1_data[32]", "rs2_data[32]", "ALUControl[4]", "result[32]"], rows)


# --- ALUControl -------------------------------------------------------------
def alu_ctrl(aluop, f3, f7):
    if aluop == 0:
        return 0
    if aluop == 1:
        return 1
    sub_sra = (f7 >> 5) & 1
    table = {0: 1 if (aluop == 2 and sub_sra) else 0, 1: 5, 2: 8, 3: 9, 4: 4,
             5: 7 if sub_sra else 6, 6: 3, 7: 2}
    return table[f3]


def aluctrl_vectors():
    rows = []
    for aluop in range(4):
        for f3 in range(8):
            for f7 in (0x00, 0x20):
                rows.append([h(aluop, 2), h(f3, 3), h(f7, 7), h(alu_ctrl(aluop, f3, f7), 4)])
    write("ALUControl", ["ALUOp[2]", "ext3[3]", "funct7[7]", "ALUCtrl[4]"], rows)


# --- InstructionDecode ------------------------------------------------------
def idec_vectors():
    rows = []
    for _ in range(40):
        i = rnd.getrandbits(32)
        rows.append([h(i), h(i & 0x7F, 7), h(i >> 7, 5), h(i >> 12, 3), h(i >> 15, 5), h(i >> 20, 5), h(i >> 25, 7)])
    write("InstructionDecode", ["Instruction[32]", "OP[7]", "rd[5]", "ext3[3]", "rs1[5]", "rs2[5]", "funct7[7]"], rows)


# --- ImmGen -------------------------------------------------------------------
def imm_of(i, sel):
    b = lambda hi, lo: (i >> lo) & ((1 << (hi - lo + 1)) - 1)  # noqa: E731
    if sel == 0:
        return sx(b(31, 20), 12)
    if sel == 1:
        return sx((b(31, 25) << 5) | b(11, 7), 12)
    if sel == 2:
        return sx((b(31, 31) << 12) | (b(7, 7) << 11) | (b(30, 25) << 5) | (b(11, 8) << 1), 13)
    if sel == 3:
        return b(31, 12) << 12
    if sel == 4:
        return sx((b(31, 31) << 20) | (b(19, 12) << 12) | (b(20, 20) << 11) | (b(30, 21) << 1), 21)
    return 0


def immgen_vectors():
    rows = []
    for _ in range(30):
        i = rnd.getrandbits(32)
        for sel in range(5):
            rows.append([h(i), h(sel, 3), h(imm_of(i, sel) & M32)])
    write("ImmGen", ["Instruction[32]", "ImmSel[3]", "Imm[32]"], rows)


# --- BranchUnit -------------------------------------------------------------
def br_cond(f3, a, b):
    sa, sb = sx(a, 32), sx(b, 32)
    return {0: a == b, 1: a != b, 2: False, 3: False, 4: sa < sb, 5: sa >= sb, 6: a < b, 7: a >= b}[f3]


def branch_vectors():
    rows = []
    for f3 in range(8):
        for _ in range(12):
            a = interesting32()
            b = a if rnd.random() < 0.3 else interesting32()
            for br in (0, 1):
                rows.append([h(a), h(b), h(f3, 3), str(br), str(int(br and br_cond(f3, a, b)))])
    write("BranchUnit", ["rs1_data[32]", "rs2_data[32]", "ext3[3]", "IsBranch", "branch_taken"], rows)


# --- MainControl ------------------------------------------------------------
#        RegWrite MemRead MemWrite Branch Jal Jalr ALUSrcA ALUSrcB ALUOp ImmSel WBSel Halt
CONTROL = {
    0x33: (1, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0),  # R-type
    0x13: (1, 0, 0, 0, 0, 0, 0, 1, 3, 0, 0, 0),  # I-type ALU
    0x03: (1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0),  # load
    0x23: (0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0),  # store
    0x63: (0, 0, 0, 1, 0, 0, 0, 0, 1, 2, 0, 0),  # branch
    0x6F: (1, 0, 0, 0, 1, 0, 0, 0, 0, 4, 2, 0),  # jal
    0x67: (1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 2, 0),  # jalr
    0x37: (1, 0, 0, 0, 0, 0, 2, 1, 0, 3, 0, 0),  # lui
    0x17: (1, 0, 0, 0, 0, 0, 1, 1, 0, 3, 0, 0),  # auipc
    0x73: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1),  # ecall/ebreak -> halt
    0x00: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),  # bubble
}
CTRL_COLS = [("RegWrite", 1), ("MemRead", 1), ("MemWrite", 1), ("Branch", 1), ("Jal", 1), ("Jalr", 1),
             ("ALUSrcA", 2), ("ALUSrcB", 1), ("ALUOp", 2), ("ImmSel", 3), ("WBSel", 2), ("Halt", 1)]


def control_vectors():
    rows = []
    for op, sig in CONTROL.items():
        rows.append([h(op, 7)] + [h(v, w) if w > 1 else str(v) for v, (_, w) in zip(sig, CTRL_COLS)])
    write("MainControl", ["OP[7]"] + [f"{n}[{w}]" if w > 1 else n for n, w in CTRL_COLS], rows)


# --- RegisterFile (sequential) -----------------------------------------------
def regfile_vectors():
    regs = [0] * 32
    rows, seq = [], 0

    def step(clk, we, wd, rd, rs1, rs2):
        nonlocal seq
        seq += 1
        rows.append(["1", str(seq), str(clk), str(we), h(wd), h(rd, 5), h(rs1, 5), h(rs2, 5),
                     h(regs[rs1]), h(regs[rs2])])

    def write_reg(rd, v, we=1):
        r1, r2 = rnd.randrange(32), rnd.randrange(32)
        step(0, we, v, rd, r1, r2)
        if we and rd:
            regs[rd] = v
        step(1, we, v, rd, r1, r2)

    for r in range(32):
        write_reg(r, rnd.getrandbits(32))
    for _ in range(40):
        write_reg(rnd.randrange(32), rnd.getrandbits(32), we=rnd.choice((0, 1, 1)))
    for r in range(32):
        step(0, 0, 0, 0, r, 31 - r)
    write("RegisterFile", ["<SET>", "<SEQ>", "clock", "write", "write_data[32]", "rd[5]", "rs1[5]", "rs2[5]",
                           "rs1_data[32]", "rs2_data[32]"], rows)


# --- Memory (sequential) -------------------------------------------------------
def memory_vectors():
    mem = {}
    rows, seq = [], 0

    def step(clk, we, addr, wd, check):
        nonlocal seq
        seq += 1
        exp = h(mem.get((addr >> 2) & 1023, 0)) if check else "<DC>"
        rows.append(["1", str(seq), str(clk), str(we), h(addr), h(wd), exp])

    addrs = [rnd.randrange(1024) * 4 for _ in range(30)] + [0, 4, 4092]
    for a in addrs:
        v = rnd.getrandbits(32)
        step(0, 1, a, v, False)
        mem[(a >> 2) & 1023] = v
        step(1, 1, a, v, False)
        step(0, 0, a, 0, True)
    for a in addrs:
        step(0, 0, a, 0, True)
        step(1, 0, a, 0xDEADBEEF, True)  # clock edge without MemWrite must not store
    write("Memory", ["<SET>", "<SEQ>", "CLK", "MemWrite", "Address[32]", "WriteData[32]", "ReadData[32]"], rows)


# --- Pipeline control ------------------------------------------------------------
def hazard_vectors():
    rows = []
    for _ in range(150):
        ex_rd, rs1, rs2 = (rnd.choice([0, 1, 5, 31, rnd.randrange(32)]) for _ in range(3))
        if rnd.random() < 0.4:  # bias towards matches
            rs1 = ex_rd if rnd.random() < 0.5 else rs1
            rs2 = ex_rd if rnd.random() < 0.5 else rs2
        mr = rnd.randrange(2)
        stall = int(mr and ex_rd != 0 and (ex_rd == rs1 or ex_rd == rs2))
        rows.append([str(mr), h(ex_rd, 5), h(rs1, 5), h(rs2, 5), str(stall)])
    write("HazardUnit", ["ex_memread", "ex_rd[5]", "id_rs1[5]", "id_rs2[5]", "stall"], rows)


def forwarding_vectors():
    def fwd(rs, mem_rd, mem_rw, wb_rd, wb_rw):
        if mem_rw and mem_rd and mem_rd == rs:
            return 2
        if wb_rw and wb_rd and wb_rd == rs:
            return 1
        return 0

    rows = []
    for _ in range(250):
        pool = [0, rnd.randrange(32), rnd.randrange(32)]
        rs1, rs2, mem_rd, wb_rd = (rnd.choice(pool) for _ in range(4))
        mem_rw, wb_rw = rnd.randrange(2), rnd.randrange(2)
        rows.append([h(rs1, 5), h(rs2, 5), h(mem_rd, 5), str(mem_rw), h(wb_rd, 5), str(wb_rw),
                     h(fwd(rs1, mem_rd, mem_rw, wb_rd, wb_rw), 2), h(fwd(rs2, mem_rd, mem_rw, wb_rd, wb_rw), 2)])
    write("ForwardingUnit", ["ex_rs1[5]", "ex_rs2[5]", "mem_rd[5]", "mem_regwrite", "wb_rd[5]", "wb_regwrite",
                             "fwdA[2]", "fwdB[2]"], rows)


def bypass_vectors():
    rows = []
    for _ in range(150):
        pool = [0, rnd.randrange(32), rnd.randrange(32)]
        rd, rs1, rs2 = (rnd.choice(pool) for _ in range(3))
        rw = rnd.randrange(2)
        wd, f1, f2 = (rnd.getrandbits(32) for _ in range(3))
        o1 = wd if rw and rd and rd == rs1 else f1
        o2 = wd if rw and rd and rd == rs2 else f2
        rows.append([str(rw), h(rd, 5), h(wd), h(rs1, 5), h(rs2, 5), h(f1), h(f2), h(o1), h(o2)])
    write("WBBypass", ["wb_regwrite", "wb_rd[5]", "wb_data[32]", "rs1[5]", "rs2[5]", "rf_rs1_data[32]",
                       "rf_rs2_data[32]", "rs1_data[32]", "rs2_data[32]"], rows)


def pipe_reg_vectors(name, fields, flush):
    """Sequential: en=0 holds, flush=1 loads zeros, otherwise D is captured."""
    state = {f: 0 for f, _ in fields}
    rows, seq = [], 0
    for _ in range(60):
        en = int(rnd.random() < 0.7)
        fl = int(flush and rnd.random() < 0.25)
        vals = {f: rnd.getrandbits(w) for f, w in fields}
        for clk in (0, 1):
            if clk and en:
                state = {f: 0 for f, _ in fields} if fl else dict(vals)
            seq += 1
            rows.append(["1", str(seq), str(clk), str(en)] + ([str(fl)] if flush else [])
                        + [h(vals[f], w) for f, w in fields] + [h(state[f], w) for f, w in fields])
    header = ["<SET>", "<SEQ>", "clk", "en"] + (["flush"] if flush else []) \
        + [f"{f}[{w}]" if w > 1 else f for f, w in fields] + [f"{f}_q[{w}]" if w > 1 else f"{f}_q" for f, w in fields]
    write(name, header, rows)


IF_ID = [("pc", 32), ("instr", 32)]
ID_EX = [("pc", 32), ("instr", 32), ("r1", 32), ("r2", 32), ("imm", 32), ("rs1", 5), ("rs2", 5), ("rd", 5),
         ("f3", 3), ("aluctrl", 4), ("alusrca", 2), ("alusrcb", 1), ("regwrite", 1), ("memread", 1),
         ("memwrite", 1), ("branch", 1), ("jal", 1), ("jalr", 1), ("wbsel", 2), ("halt", 1)]
EX_MEM = [("instr", 32), ("result", 32), ("alu", 32), ("sdata", 32), ("rd", 5), ("regwrite", 1), ("memwrite", 1),
          ("wbsel", 2), ("halt", 1)]
MEM_WB = [("instr", 32), ("result", 32), ("rdata", 32), ("rd", 5), ("regwrite", 1), ("wbsel", 2), ("halt", 1)]


if __name__ == "__main__":
    hazard_vectors()
    forwarding_vectors()
    bypass_vectors()
    pipe_reg_vectors("IF_ID", IF_ID, True)
    pipe_reg_vectors("ID_EX", ID_EX, True)
    pipe_reg_vectors("EX_MEM", EX_MEM, False)
    pipe_reg_vectors("MEM_WB", MEM_WB, False)
    alu_vectors()
    aluctrl_vectors()
    idec_vectors()
    immgen_vectors()
    branch_vectors()
    control_vectors()
    regfile_vectors()
    memory_vectors()
