"""Build project.circ: RISC-V RV32I CPU (single-cycle + 5-stage pipeline).

Starts from Lab1.circ: the ALU (with the SRA/SLT fixes), ALUControl and
InstructionDecode circuits are kept as drawn; every other circuit is
generated here.

    python3 tools/gen/build_project.py [--program prog.hex]
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lgen  # noqa: E402
from lgen import Tie  # noqa: E402

ROOT = lgen.ROOT
LAB1 = os.path.join(ROOT, "Lab1.circ")
OUT = os.path.join(ROOT, "project.circ")

# MainControl opcodes
OP_R, OP_I, OP_LOAD, OP_STORE, OP_BRANCH = 0x33, 0x13, 0x03, 0x23, 0x63
OP_JAL, OP_JALR, OP_LUI, OP_AUIPC, OP_SYSTEM = 0x6F, 0x67, 0x37, 0x17, 0x73

ROM_ADDR_BITS = 10  # 1024 instructions (4 KiB)
RAM_ADDR_BITS = 10  # 1024 words (4 KiB)


# ---------------------------------------------------------------------------
# Circuits kept from Lab1
# ---------------------------------------------------------------------------
def lab1_block(src: str, name: str) -> str:
    m = re.search(rf'  <circuit name="{name}">.*?</circuit>', src, re.S)
    if not m:
        raise SystemExit(f"Lab1.circ has no circuit {name}")
    return m.group(0)


def patched_alu(src: str) -> str:
    alu = lab1_block(src, "ALU")
    # Third shifter is SRA: arithmetic, not logical, right shift.
    old = '<comp lib="3" loc="(440,950)" name="Shifter">\n      <a name="shift" val="lr"/>'
    assert alu.count(old) == 1
    alu = alu.replace(old, old.replace('val="lr"', 'val="ar"'))
    # SLT/SLTU produce 0/1, so the comparator bit is zero-extended.
    for loc in ("(510,1040)", "(510,1150)"):
        old = f'<comp lib="0" loc="{loc}" name="Bit Extender">\n      <a name="in_width" val="1"/>'
        assert alu.count(old) == 1
        alu = alu.replace(old, old + '\n      <a name="type" val="zero"/>')
    return alu


# ---------------------------------------------------------------------------
# Combinational modules
# ---------------------------------------------------------------------------
def build_immgen(P):
    """Imm = sign-extended immediate of the format picked by ImmSel
    (0=I, 1=S, 2=B, 3=U, 4=J)."""
    c = P.circuit("ImmGen")
    c.pin_in("Instruction", 32, 60, 500, "ins")
    c.pin_in("ImmSel", 3, 60, 1100, "sel")
    c.pin_out("Imm", 32, 1500, 600, "imm")
    c.splitter(200, 500, 32,
               [(7, 7), (8, 11), (12, 19), (20, 20), (21, 24), (25, 30), (31, 31)], "ins",
               ["f7", "f11_8", "f19_12", "f20", "f24_21", "f30_25", "f31"])
    c.text(200, 360, "Instruction fields")
    # I: ins[31:20]
    c.splitter(700, 100, 12, [(0, 0), (1, 4), (5, 10), (11, 11)], "immI12",
               ["f20", "f24_21", "f30_25", "f31"], facing="west")
    c.extend(1000, 100, 12, 32, "sign", "immI12", "immI")
    c.text(600, 30, "I-type")
    # S: ins[31:25] ins[11:7]
    c.splitter(700, 300, 12, [(0, 0), (1, 4), (5, 10), (11, 11)], "immS12",
               ["f7", "f11_8", "f30_25", "f31"], facing="west")
    c.extend(1000, 300, 12, 32, "sign", "immS12", "immS")
    c.text(600, 230, "S-type")
    # B: ins[31] ins[7] ins[30:25] ins[11:8] 0
    c.splitter(700, 520, 13, [(0, 0), (1, 4), (5, 10), (11, 11), (12, 12)], "immB13",
               [Tie(0), "f11_8", "f30_25", "f7", "f31"], facing="west")
    c.extend(1000, 520, 13, 32, "sign", "immB13", "immB")
    c.text(600, 430, "B-type")
    # U: ins[31:12] << 12
    c.splitter(700, 780, 32, [(0, 11), (12, 19), (20, 20), (21, 24), (25, 30), (31, 31)], "immU",
               [Tie(0), "f19_12", "f20", "f24_21", "f30_25", "f31"], facing="west")
    c.text(600, 680, "U-type")
    # J: ins[31] ins[19:12] ins[20] ins[30:21] 0
    c.splitter(700, 1060, 21, [(0, 0), (1, 4), (5, 10), (11, 11), (12, 19), (20, 20)], "immJ21",
               [Tie(0), "f24_21", "f30_25", "f20", "f19_12", "f31"], facing="west")
    c.extend(1000, 1060, 21, 32, "sign", "immJ21", "immJ")
    c.text(600, 950, "J-type")
    c.mux(1300, 600, 3, 32, ["immI", "immS", "immB", "immU", "immJ", Tie(0), Tie(0), Tie(0)], "sel", "imm")


def build_regfile(P):
    """32 x 32-bit registers, x0 hard-wired to 0. Two combinational read
    ports, one write port written on the rising clock edge."""
    c = P.circuit("RegisterFile")
    c.pin_in("clock", 1, 60, 100, "clk")
    c.pin_in("write", 1, 60, 200, "we")
    c.pin_in("rd", 5, 60, 300, "rd")
    c.pin_in("write_data", 32, 60, 400, "wd")
    c.pin_in("rs1", 5, 60, 500, "rs1")
    c.pin_in("rs2", 5, 60, 600, "rs2")
    c.pin_out("rs1_data", 32, 2000, 500, "rs1_data")
    c.pin_out("rs2_data", 32, 2000, 1100, "rs2_data")
    dec = c.add("plexers", "Decoder", 300, 700, {"select": 5, "enable": "true"},
                {i: f"we{i}" for i in range(1, 32)})
    dec.conns[32] = "rd"
    dec.conns[33] = "we"
    c.text(300, 300, "write-enable decoder")
    for i in range(1, 32):
        col, row = divmod(i, 8)
        c.register(560 + 300 * col, 60 + 140 * row, 32, "wd", f"x{i}", "clk", en=f"we{i}", label=f"x{i}")
    regs = [Tie(0)] + [f"x{i}" for i in range(1, 32)]
    c.mux(1800, 500, 5, 32, regs, "rs1", "rs1_data")
    c.mux(1800, 1100, 5, 32, regs, "rs2", "rs2_data")


def build_memory(P):
    """Data memory: 1024 x 32-bit words, word-addressed by Address[11:2].
    Stores happen on the rising clock edge when MemWrite = 1."""
    c = P.circuit("Memory")
    c.pin_in("CLK", 1, 60, 100, "clk")
    c.pin_in("MemWrite", 1, 60, 200, "we")
    c.pin_in("Address", 32, 60, 300, "addr")
    c.pin_in("WriteData", 32, 60, 400, "wd")
    c.pin_out("ReadData", 32, 1000, 300, "rd")
    c.splitter(200, 300, 32, [(2, 2 + RAM_ADDR_BITS - 1)], "addr", ["waddr"])
    c.add("memory", "RAM", 500, 100,
          {"addrWidth": RAM_ADDR_BITS, "dataWidth": 32, "appearance": "logisim_evolution", "label": "DMEM",
           "asyncread": "true"},
          {0: "waddr", 1: "rd", 2: "wd", 3: Tie(1), 4: "we", 5: "clk"})


def build_branch_unit(P):
    """branch_taken = IsBranch and the condition selected by funct3
    (BEQ BNE - - BLT BGE BLTU BGEU)."""
    c = P.circuit("BranchUnit")
    c.pin_in("rs1_data", 32, 60, 100, "a")
    c.pin_in("rs2_data", 32, 60, 200, "b")
    c.pin_in("ext3", 3, 60, 300, "f3")
    c.pin_in("IsBranch", 1, 60, 400, "br")
    c.pin_out("branch_taken", 1, 1200, 300, "taken")
    c.comparator(300, 120, 32, "a", "b", eq="eq", lt="lt", signed=True)
    c.comparator(300, 300, 32, "a", "b", lt="ltu", signed=False)
    c.not_(560, 100, "eq", "ne")
    c.not_(560, 200, "lt", "ge")
    c.not_(560, 300, "ltu", "geu")
    c.mux(800, 300, 3, 1, ["eq", "ne", Tie(0), Tie(0), "lt", "ge", "ltu", "geu"], "f3", "cond")
    c.gate("AND", 1000, 300, ["cond", "br"], "taken")


def build_main_control(P):
    """Decodes the opcode into datapath control signals."""
    c = P.circuit("MainControl")
    c.pin_in("OP", 7, 60, 500, "op")
    outs = [("RegWrite", 1), ("MemRead", 1), ("MemWrite", 1), ("Branch", 1), ("Jal", 1), ("Jalr", 1),
            ("ALUSrcA", 2), ("ALUSrcB", 1), ("ALUOp", 2), ("ImmSel", 3), ("WBSel", 2), ("Halt", 1)]
    for i, (name, w) in enumerate(outs):
        c.pin_out(name, w, 1300, 100 + 100 * i, name)
    kinds = [("isR", OP_R), ("isI", OP_I), ("isLoad", OP_LOAD), ("isStore", OP_STORE), ("isBranch", OP_BRANCH),
             ("isJal", OP_JAL), ("isJalr", OP_JALR), ("isLui", OP_LUI), ("isAuipc", OP_AUIPC), ("isSys", OP_SYSTEM)]
    for i, (net, code) in enumerate(kinds):
        c.comparator(300, 100 + 120 * i, 7, "op", Tie(code), eq=net, signed=False)
        c.text(380, 70 + 120 * i, f"{net[2:]} = 0x{code:02X}")
    c.gate("OR", 700, 100, ["isR", "isI", "isLoad", "isJal", "isJalr", "isLui", "isAuipc"], "RegWrite")
    c.gate("OR", 700, 300, ["isI", "isLoad", "isStore", "isJalr", "isLui", "isAuipc"], "ALUSrcB")
    c.gate("OR", 700, 480, ["isI", "isBranch"], "aluop0")
    c.gate("OR", 700, 580, ["isR", "isI"], "aluop1")
    c.gate("OR", 700, 700, ["isStore", "isLui", "isAuipc"], "imm0")
    c.gate("OR", 700, 820, ["isBranch", "isLui", "isAuipc"], "imm1")
    c.gate("OR", 700, 940, ["isJal", "isJalr"], "wb1")
    c.splitter(1000, 700, 2, [(0, 0), (1, 1)], "ALUSrcA", ["isAuipc", "isLui"], facing="west")
    c.splitter(1000, 820, 2, [(0, 0), (1, 1)], "ALUOp", ["aluop0", "aluop1"], facing="west")
    c.splitter(1000, 960, 3, [(0, 0), (1, 1), (2, 2)], "ImmSel", ["imm0", "imm1", "isJal"], facing="west")
    c.splitter(1000, 1140, 2, [(0, 0), (1, 1)], "WBSel", ["isLoad", "wb1"], facing="west")
    # single-signal outputs are the decoded opcode lines themselves
    for pin, net in (("MemRead", "isLoad"), ("MemWrite", "isStore"), ("Branch", "isBranch"),
                     ("Jal", "isJal"), ("Jalr", "isJalr"), ("Halt", "isSys")):
        for comp in c.comps:
            if comp.name == "Pin" and comp.attrs.get("label") == pin:
                comp.conns[0] = net


def rom(c, x, y, addr_net, data_net, words=None):
    contents = f"addr/data: {ROM_ADDR_BITS} 32\n" + " ".join(f"{w:x}" for w in (words or [0])) + "\n"
    return c.add("memory", "ROM", x, y,
                 {"addrWidth": ROM_ADDR_BITS, "dataWidth": 32, "appearance": "logisim_evolution",
                  "label": "IMEM", "contents": contents},
                 {0: addr_net, 1: data_net})


def trace_pins(c, x, y, nets):
    """Output pins watched by the TTY test bench (and handy in the GUI)."""
    for i, (label, width, net) in enumerate(nets):
        c.pin_out(label, width, x, y + 80 * i, net)


def cycle_counter(c, x, y):
    c.register(x, y, 32, "cycle_next", "cycle", "clk", en="run", label="CYCLES")
    c.adder(x + 300, y + 30, 32, "cycle", Tie(1), "cycle_next")


def build_single_cycle(P, words):
    c = P.circuit("SingleCycleCPU")
    c.text(700, 40, "RISC-V RV32I single-cycle CPU  (program: IMEM ROM, data: DMEM inside Memory)")
    c.clock(100, 200, "clk")
    c.not_(160, 300, "halt", "run")
    cycle_counter(c, 100, 1500)
    # fetch
    c.register(300, 400, 32, "pc_next", "pc", "clk", en="run", label="PC")
    c.adder(700, 200, 32, "pc", Tie(4), "pc4")
    c.splitter(600, 600, 32, [(2, 2 + ROM_ADDR_BITS - 1)], "pc", ["pc_word"])
    rom(c, 800, 500, "pc_word", "instr", words)
    # decode
    c.sub("InstructionDecode", 1500, 300,
          {"Instruction": "instr", "OP": "op", "rd": "rd", "ext3": "f3", "rs1": "rs1", "rs2": "rs2", "funct7": "f7"})
    c.sub("MainControl", 1500, 1000,
          {"OP": "op", "RegWrite": "RegWrite", "MemWrite": "MemWrite", "Branch": "Branch",
           "Jal": "Jal", "Jalr": "Jalr", "ALUSrcA": "ALUSrcA", "ALUSrcB": "ALUSrcB", "ALUOp": "ALUOp",
           "ImmSel": "ImmSel", "WBSel": "WBSel", "Halt": "halt"})
    c.sub("RegisterFile", 2100, 300,
          {"clock": "clk", "write": "RegWrite", "rd": "rd", "write_data": "wb_data", "rs1": "rs1", "rs2": "rs2",
           "rs1_data": "r1", "rs2_data": "r2"})
    c.sub("ImmGen", 2100, 900, {"Instruction": "instr", "ImmSel": "ImmSel", "Imm": "imm"})
    c.sub("ALUControl", 2100, 1300, {"funct7": "f7", "ext3": "f3", "ALUOp": "ALUOp", "ALUCtrl": "aluctrl"})
    # execute
    c.mux(2800, 300, 2, 32, ["r1", "pc", Tie(0), Tie(0)], "ALUSrcA", "alu_a")
    c.mux(2800, 600, 1, 32, ["r2", "imm"], "ALUSrcB", "alu_b")
    c.sub("ALU", 3200, 400, {"rs1_data": "alu_a", "rs2_data": "alu_b", "ALUControl": "aluctrl", "result": "alu_res"})
    c.sub("BranchUnit", 3200, 900,
          {"rs1_data": "r1", "rs2_data": "r2", "ext3": "f3", "IsBranch": "Branch", "branch_taken": "taken"})
    c.adder(3200, 1300, 32, "pc", "imm", "br_target")
    c.gate("AND", 3200, 1500, ["alu_res", Tie(0xFFFFFFFE)], "jalr_target", width=32)
    c.gate("OR", 3200, 1700, ["taken", "Jal"], "take_br")
    # next PC
    c.mux(3900, 1300, 1, 32, ["pc4", "br_target"], "take_br", "pc_a")
    c.mux(4300, 1400, 1, 32, ["pc_a", "jalr_target"], "Jalr", "pc_next")
    # memory + write back
    c.sub("Memory", 3900, 400,
          {"CLK": "clk", "MemWrite": "MemWrite", "Address": "alu_res", "WriteData": "r2", "ReadData": "mem_data"})
    c.mux(4400, 500, 2, 32, ["alu_res", "mem_data", "pc4", Tie(0)], "WBSel", "wb_data")
    trace_pins(c, 4900, 200, [("halt", 1, "halt"), ("cycle", 32, "cycle"), ("pc", 32, "pc"), ("instr", 32, "instr"),
                              ("wb_en", 1, "RegWrite"), ("wb_rd", 5, "rd"), ("wb_data", 32, "wb_data"),
                              ("mem_we", 1, "MemWrite"), ("mem_addr", 32, "alu_res"), ("mem_wdata", 32, "r2")])


# ---------------------------------------------------------------------------
# Pipeline support circuits
# ---------------------------------------------------------------------------
IF_ID_FIELDS = [("pc", 32), ("instr", 32)]
ID_EX_FIELDS = [("pc", 32), ("instr", 32), ("r1", 32), ("r2", 32), ("imm", 32), ("rs1", 5), ("rs2", 5),
                ("rd", 5), ("f3", 3), ("aluctrl", 4), ("alusrca", 2), ("alusrcb", 1), ("regwrite", 1),
                ("memread", 1), ("memwrite", 1), ("branch", 1), ("jal", 1), ("jalr", 1), ("wbsel", 2),
                ("halt", 1)]
EX_MEM_FIELDS = [("instr", 32), ("result", 32), ("alu", 32), ("sdata", 32), ("rd", 5), ("regwrite", 1),
                 ("memwrite", 1), ("wbsel", 2), ("halt", 1)]
MEM_WB_FIELDS = [("instr", 32), ("result", 32), ("rdata", 32), ("rd", 5), ("regwrite", 1), ("wbsel", 2),
                 ("halt", 1)]


def build_pipe_reg(P, name, fields, flush):
    """One register per field, all clocked together. en=0 holds (stall);
    flush=1 loads zeros, i.e. a bubble (opcode 0 has no control signals)."""
    c = P.circuit(name)
    c.pin_in("clk", 1, 60, 60, "clk")
    c.pin_in("en", 1, 60, 120, "en")
    if flush:
        c.pin_in("flush", 1, 60, 180, "flush")
    for i, (f, w) in enumerate(fields):
        y = 300 + 130 * i
        c.pin_in(f, w, 60, y, f"{f}_in")
        if flush:
            c.mux(400, y, 1, w, [f"{f}_in", Tie(0)], "flush", f"{f}_d")
        c.register(640, y - 30, w, f"{f}_d" if flush else f"{f}_in", f"{f}_q", "clk", en="en", label=f)
        c.pin_out(f"{f}_q", w, 1000, y, f"{f}_q")


def build_hazard_unit(P):
    """stall = load in EX whose rd is read by the instruction in ID."""
    c = P.circuit("HazardUnit")
    c.pin_in("ex_memread", 1, 60, 100, "memread")
    c.pin_in("ex_rd", 5, 60, 200, "ex_rd")
    c.pin_in("id_rs1", 5, 60, 300, "rs1")
    c.pin_in("id_rs2", 5, 60, 400, "rs2")
    c.pin_out("stall", 1, 1000, 250, "stall")
    c.comparator(300, 120, 5, "ex_rd", "rs1", eq="m1", signed=False)
    c.comparator(300, 260, 5, "ex_rd", "rs2", eq="m2", signed=False)
    c.comparator(300, 400, 5, "ex_rd", Tie(0), eq="rd_zero", signed=False)
    c.gate("OR", 560, 190, ["m1", "m2"], "uses")
    c.not_(560, 400, "rd_zero", "rd_nz")
    c.gate("AND", 800, 250, ["memread", "uses", "rd_nz"], "stall")


def build_forwarding_unit(P):
    """fwd = 2: take EX/MEM result, 1: take MEM/WB result, 0: register value.
    The younger instruction (EX/MEM) wins; x0 is never forwarded."""
    c = P.circuit("ForwardingUnit")
    c.pin_in("ex_rs1", 5, 60, 100, "rs1")
    c.pin_in("ex_rs2", 5, 60, 200, "rs2")
    c.pin_in("mem_rd", 5, 60, 300, "mem_rd")
    c.pin_in("mem_regwrite", 1, 60, 400, "mem_rw")
    c.pin_in("wb_rd", 5, 60, 500, "wb_rd")
    c.pin_in("wb_regwrite", 1, 60, 600, "wb_rw")
    c.pin_out("fwdA", 2, 1500, 200, "fwdA")
    c.pin_out("fwdB", 2, 1500, 600, "fwdB")
    c.comparator(300, 760, 5, "mem_rd", Tie(0), eq="mem_rd0", signed=False)
    c.comparator(300, 900, 5, "wb_rd", Tie(0), eq="wb_rd0", signed=False)
    c.gate("AND", 560, 760, ["mem_rw", "mem_rd0"], "mem_ok", negate=[1])
    c.gate("AND", 560, 900, ["wb_rw", "wb_rd0"], "wb_ok", negate=[1])
    for k, (rs, out, y) in enumerate((("rs1", "fwdA", 100), ("rs2", "fwdB", 400))):
        s = "ab"[k]
        c.comparator(300, y + 40, 5, "mem_rd", rs, eq=f"{s}_mem_eq", signed=False)
        c.comparator(300, y + 180, 5, "wb_rd", rs, eq=f"{s}_wb_eq", signed=False)
        c.gate("AND", 700, y + 40, ["mem_ok", f"{s}_mem_eq"], f"{s}_mem")
        c.gate("AND", 700, y + 180, ["wb_ok", f"{s}_wb_eq", f"{s}_mem"], f"{s}_wb", negate=[2])
        c.splitter(1100, y + 100, 2, [(0, 0), (1, 1)], out, [f"{s}_wb", f"{s}_mem"], facing="west")


def build_wb_bypass(P):
    """Register-file bypass in ID: a value being written back this cycle is
    passed straight to the instruction reading it (write and read in the
    same cycle)."""
    c = P.circuit("WBBypass")
    c.pin_in("wb_regwrite", 1, 60, 100, "rw")
    c.pin_in("wb_rd", 5, 60, 200, "rd")
    c.pin_in("wb_data", 32, 60, 300, "wd")
    c.pin_in("rs1", 5, 60, 400, "rs1")
    c.pin_in("rs2", 5, 60, 500, "rs2")
    c.pin_in("rf_rs1_data", 32, 60, 600, "rf1")
    c.pin_in("rf_rs2_data", 32, 60, 700, "rf2")
    c.pin_out("rs1_data", 32, 1300, 300, "o1")
    c.pin_out("rs2_data", 32, 1300, 600, "o2")
    c.comparator(300, 120, 5, "rd", Tie(0), eq="rd0", signed=False)
    c.gate("AND", 560, 120, ["rw", "rd0"], "ok", negate=[1])
    c.comparator(300, 300, 5, "rd", "rs1", eq="eq1", signed=False)
    c.comparator(300, 480, 5, "rd", "rs2", eq="eq2", signed=False)
    c.gate("AND", 700, 300, ["ok", "eq1"], "sel1")
    c.gate("AND", 700, 480, ["ok", "eq2"], "sel2")
    c.mux(1000, 300, 1, 32, ["rf1", "wd"], "sel1", "o1")
    c.mux(1000, 600, 1, 32, ["rf2", "wd"], "sel2", "o2")


def pipe_conns(fields, src_prefix, dst_prefix, rename=None):
    rename = rename or {}
    conns = {}
    for f, _ in fields:
        conns[f] = rename.get(f, f"{src_prefix}{f}")
        conns[f"{f}_q"] = f"{dst_prefix}{f}"
    return conns


def build_pipeline(P, words):
    c = P.circuit("PipelineCPU")
    c.text(900, 40, "RISC-V RV32I 5-stage pipeline:  IF -> ID -> EX -> MEM -> WB"
                    "   (forwarding, load-use stall, branch/jump resolved in EX with 2-instruction flush)")
    c.clock(100, 200, "clk")
    c.not_(160, 300, "wb_halt", "run")
    c.not_(160, 400, "stall", "nstall")
    c.gate("AND", 450, 400, ["run", "nstall"], "fetch_en")
    cycle_counter(c, 100, 1900)

    # ---------------- IF ----------------
    c.text(600, 120, "IF")
    c.register(300, 700, 32, "pc_next", "pc", "clk", en="fetch_en", label="PC")
    c.adder(700, 500, 32, "pc", Tie(4), "pc4")
    c.splitter(600, 900, 32, [(2, 2 + ROM_ADDR_BITS - 1)], "pc", ["pc_word"])
    rom(c, 800, 800, "pc_word", "if_instr", words)
    c.mux(700, 1700, 1, 32, ["pc4", "redirect_target"], "redirect", "pc_next")
    c.sub("IF_ID", 1500, 300, dict(clk="clk", en="fetch_en", flush="redirect",
                                   **pipe_conns(IF_ID_FIELDS, "", "id_", {"pc": "pc", "instr": "if_instr"})),
          label="IF/ID")

    # ---------------- ID ----------------
    c.text(2300, 120, "ID")
    c.sub("InstructionDecode", 2000, 300,
          {"Instruction": "id_instr", "OP": "id_op", "rd": "id_rd", "ext3": "id_f3", "rs1": "id_rs1",
           "rs2": "id_rs2", "funct7": "id_f7"})
    c.sub("MainControl", 2000, 900,
          {"OP": "id_op", "RegWrite": "id_regwrite", "MemRead": "id_memread", "MemWrite": "id_memwrite",
           "Branch": "id_branch", "Jal": "id_jal", "Jalr": "id_jalr", "ALUSrcA": "id_alusrca",
           "ALUSrcB": "id_alusrcb", "ALUOp": "id_aluop", "ImmSel": "id_immsel", "WBSel": "id_wbsel",
           "Halt": "id_halt"})
    c.sub("RegisterFile", 2700, 300,
          {"clock": "clk", "write": "wb_regwrite", "rd": "wb_rd", "write_data": "wb_data", "rs1": "id_rs1",
           "rs2": "id_rs2", "rs1_data": "rf_r1", "rs2_data": "rf_r2"})
    c.sub("WBBypass", 3300, 300,
          {"wb_regwrite": "wb_regwrite", "wb_rd": "wb_rd", "wb_data": "wb_data", "rs1": "id_rs1", "rs2": "id_rs2",
           "rf_rs1_data": "rf_r1", "rf_rs2_data": "rf_r2", "rs1_data": "id_r1", "rs2_data": "id_r2"})
    c.sub("ImmGen", 2700, 1000, {"Instruction": "id_instr", "ImmSel": "id_immsel", "Imm": "id_imm"})
    c.sub("ALUControl", 2700, 1400, {"funct7": "id_f7", "ext3": "id_f3", "ALUOp": "id_aluop", "ALUCtrl": "id_aluctrl"})
    c.sub("HazardUnit", 3300, 1000,
          {"ex_memread": "ex_memread", "ex_rd": "ex_rd", "id_rs1": "id_rs1", "id_rs2": "id_rs2", "stall": "stall"})
    c.gate("OR", 3400, 1400, ["stall", "redirect"], "id_flush")
    c.sub("ID_EX", 3900, 300, dict(clk="clk", en="run", flush="id_flush",
                                   **pipe_conns(ID_EX_FIELDS, "id_", "ex_")), label="ID/EX")

    # ---------------- EX ----------------
    c.text(4700, 120, "EX")
    c.sub("ForwardingUnit", 4400, 1500,
          {"ex_rs1": "ex_rs1", "ex_rs2": "ex_rs2", "mem_rd": "mem_rd", "mem_regwrite": "mem_regwrite",
           "wb_rd": "wb_rd", "wb_regwrite": "wb_regwrite", "fwdA": "fwdA", "fwdB": "fwdB"})
    c.mux(4600, 300, 2, 32, ["ex_r1", "wb_data", "mem_result", Tie(0)], "fwdA", "fa")
    c.mux(4600, 700, 2, 32, ["ex_r2", "wb_data", "mem_result", Tie(0)], "fwdB", "fb")
    c.mux(5000, 300, 2, 32, ["fa", "ex_pc", Tie(0), Tie(0)], "ex_alusrca", "alu_a")
    c.mux(5000, 700, 1, 32, ["fb", "ex_imm"], "ex_alusrcb", "alu_b")
    c.sub("ALU", 5400, 400, {"rs1_data": "alu_a", "rs2_data": "alu_b", "ALUControl": "ex_aluctrl", "result": "ex_alu"})
    c.sub("BranchUnit", 5400, 900,
          {"rs1_data": "fa", "rs2_data": "fb", "ext3": "ex_f3", "IsBranch": "ex_branch", "branch_taken": "ex_taken"})
    c.adder(5400, 1300, 32, "ex_pc", Tie(4), "ex_pc4")
    c.adder(5400, 1500, 32, "ex_pc", "ex_imm", "ex_target")
    c.gate("AND", 5400, 1700, ["ex_alu", Tie(0xFFFFFFFE)], "jalr_target", width=32)
    c.gate("OR", 5400, 1900, ["ex_taken", "ex_jal", "ex_jalr"], "redirect")
    c.mux(5900, 1600, 1, 32, ["ex_target", "jalr_target"], "ex_jalr", "redirect_target")
    c.splitter(5800, 2000, 2, [(0, 0), (1, 1)], "ex_wbsel", [None, "ex_link"])
    c.mux(5900, 1200, 1, 32, ["ex_alu", "ex_pc4"], "ex_link", "ex_result")
    c.sub("EX_MEM", 6400, 300, dict(clk="clk", en="run",
                                    **pipe_conns(EX_MEM_FIELDS, "ex_", "mem_",
                                                 {"result": "ex_result", "alu": "ex_alu", "sdata": "fb"})),
          label="EX/MEM")

    # ---------------- MEM ----------------
    c.text(7100, 120, "MEM")
    c.gate("AND", 7000, 1000, ["mem_memwrite", "run"], "mem_we")
    c.sub("Memory", 7200, 400,
          {"CLK": "clk", "MemWrite": "mem_we", "Address": "mem_alu", "WriteData": "mem_sdata", "ReadData": "mem_rdata"})
    c.sub("MEM_WB", 7900, 300, dict(clk="clk", en="run",
                                    **pipe_conns(MEM_WB_FIELDS, "mem_", "wb_", {"rdata": "mem_rdata"})),
          label="MEM/WB")

    # ---------------- WB ----------------
    c.text(8600, 120, "WB")
    c.splitter(8400, 1000, 2, [(0, 0), (1, 1)], "wb_wbsel", ["wb_load", None])
    c.mux(8700, 600, 1, 32, ["wb_result", "wb_rdata"], "wb_load", "wb_data")
    trace_pins(c, 9200, 200, [("halt", 1, "wb_halt"), ("cycle", 32, "cycle"), ("pc", 32, "pc"),
                              ("if_instr", 32, "if_instr"), ("id_instr", 32, "id_instr"),
                              ("ex_instr", 32, "ex_instr"), ("mem_instr", 32, "mem_instr"),
                              ("wb_instr", 32, "wb_instr"), ("stall", 1, "stall"), ("flush", 1, "redirect"),
                              ("wb_en", 1, "wb_regwrite"), ("wb_rd", 5, "wb_rd"), ("wb_data", 32, "wb_data"),
                              ("mem_we", 1, "mem_we"), ("mem_addr", 32, "mem_alu"), ("mem_wdata", 32, "mem_sdata")])


def build_modules(P):
    build_immgen(P)
    build_regfile(P)
    build_memory(P)
    build_branch_unit(P)
    build_main_control(P)
    build_hazard_unit(P)
    build_forwarding_unit(P)
    build_wb_bypass(P)
    build_pipe_reg(P, "IF_ID", IF_ID_FIELDS, flush=True)
    build_pipe_reg(P, "ID_EX", ID_EX_FIELDS, flush=True)
    build_pipe_reg(P, "EX_MEM", EX_MEM_FIELDS, flush=False)
    build_pipe_reg(P, "MEM_WB", MEM_WB_FIELDS, flush=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--program", default=os.path.join(ROOT, "tests", "programs", "05_fibonacci.s"),
                    help="assembly program preloaded into IMEM")
    args = ap.parse_args()
    src = open(LAB1).read()
    P = lgen.Project("PipelineCPU")
    build_pipeline(P, None)
    build_single_cycle(P, None)
    build_modules(P)
    P.keep_raw(patched_alu(src))
    P.keep_raw(lab1_block(src, "ALUControl"))
    P.keep_raw(lab1_block(src, "InstructionDecode"))
    problems = P.build(args.out)
    for circ, errs in problems.items():
        print(f"== {circ}: {len(errs)} problem(s)")
        for e in errs[:40]:
            print("   ", e)
    print("wrote", args.out, "OK" if not problems else "WITH PROBLEMS")
    if args.program:
        sys.path.insert(0, os.path.join(ROOT, "tools", "asm"))
        from rvasm import Assembler, patch_circ
        words, _, _ = Assembler().assemble(open(args.program).read())
        patch_circ(args.out, words)
        print(f"IMEM preloaded with {os.path.relpath(args.program, ROOT)} ({len(words)} instructions)")


if __name__ == "__main__":
    main()
