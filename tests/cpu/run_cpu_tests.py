#!/usr/bin/env python3
"""Whole-CPU tests: run each program on the Logisim CPUs and compare with the
reference simulator (tools/asm/rvsim.py).

    python3 tests/cpu/run_cpu_tests.py                       # all programs, both CPUs
    python3 tests/cpu/run_cpu_tests.py tests/programs/fib.s  # one program
    python3 tests/cpu/run_cpu_tests.py --cpu PipelineCPU -v

Each CPU top-level circuit has an output pin `halt` (Logisim's TTY mode ticks
the clock until it goes high) and trace pins: wb_en/wb_rd/wb_data (register
write committed this cycle) and mem_we/mem_addr/mem_wdata (store this cycle).
The ordered list of register writes and stores must match the reference
model exactly; the final cycle count gives the CPI.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "asm"))
from rvasm import Assembler, logisim_image, patch_circ  # noqa: E402
from rvsim import run as iss_run  # noqa: E402

JAVA = os.environ.get("JAVA", shutil.which("java") or "java")
JAR = os.environ.get("LOGISIM_JAR",
                     "/Applications/Logisim-evolution.app/Contents/app/logisim-evolution-4.1.0-all.jar")
CPUS = ["SingleCycleCPU", "PipelineCPU"]


def output_pins(circ_src: str, circuit: str):
    """Output pin labels of `circuit` in the order Logisim's TTY prints them."""
    m = re.search(rf'<circuit name="{circuit}">(.*?)</circuit>', circ_src, re.S)
    if not m:
        return None
    pins = []
    for loc, body in re.findall(r'<comp lib="0" loc="\((\d+,\d+)\)" name="Pin">(.*?)</comp>', m.group(1), re.S):
        if 'name="type" val="output"' in body:
            m_label = re.search(r'name="label" val="([^"]*)"', body)
            label = m_label.group(1) if m_label else f"unnamed_{loc}"
            x, y = map(int, loc.split(","))
            pins.append((x, y, label))
    return [p[2] for p in sorted(pins) if p[2] != "halt"]


def run_logisim(circ_path, circuit, data_hex, timeout):
    cmd = [JAVA, "-jar", JAR, "--no-splash", circ_path, "--toplevel-circuit", circuit, "--tty", "table"]
    if data_hex:
        cmd += ["--load", data_hex]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout


def parse_trace(stdout, cols):
    rows = {}
    for line in stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != len(cols):
            continue
        vals = {}
        for name, f in zip(cols, fields):
            bits = f.replace(" ", "")
            vals[name] = int(bits, 2) if re.fullmatch(r"[01]+", bits) else None
        if vals.get("cycle") is not None:
            rows[vals["cycle"]] = vals  # last row printed for a cycle wins
    return [rows[k] for k in sorted(rows)]


def events(trace):
    regs, mems = [], []
    for r in trace:
        if r["wb_en"] and r["wb_rd"]:
            regs.append((r["wb_rd"], r["wb_data"]))
        if r["mem_we"]:
            mems.append((r["mem_addr"], r["mem_wdata"]))
    return regs, mems


def first_diff(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def fmt_reg(e):
    return "none" if e is None else f"x{e[0]} <- 0x{e[1]:08x}" if e[1] is not None else f"x{e[0]} <- ???"


def fmt_mem(e):
    return "none" if e is None else f"mem[0x{e[0]:08x}] <- 0x{e[1]:08x}" if None not in e else str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("programs", nargs="*")
    ap.add_argument("--circ", default=os.path.join(ROOT, "project.circ"))
    ap.add_argument("--cpu", action="append", help="circuit(s) to test (default: both CPUs)")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    programs = args.programs or sorted(glob.glob(os.path.join(ROOT, "tests", "programs", "*.s")))
    src = open(args.circ).read()
    cpus = [c for c in (args.cpu or CPUS) if output_pins(src, c) is not None]
    failures = 0
    tmp = tempfile.mkdtemp(prefix="cputest")
    print(f"{'program':<22}" + "".join(f"{c:>34}" for c in cpus))
    for prog in programs:
        name = os.path.splitext(os.path.basename(prog))[0]
        words, data, _ = Assembler().assemble(open(prog).read())
        ref = iss_run(words, data)
        exp_regs, exp_mems = ref["reg_writes"], ref["mem_writes"]
        circ = os.path.join(tmp, f"{name}.circ")
        shutil.copy(args.circ, circ)
        patch_circ(circ, words)
        data_hex = None
        if data:
            data_hex = os.path.join(tmp, f"{name}.data.hex")
            with open(data_hex, "w") as f:
                f.write(logisim_image([data.get(i, 0) for i in range(max(data) + 1)]))
        cells, notes = [], []
        for cpu in cpus:
            cols = output_pins(src, cpu)
            try:
                out = run_logisim(circ, cpu, data_hex, args.timeout)
            except subprocess.TimeoutExpired:
                cells.append("TIMEOUT")
                failures += 1
                continue
            trace = parse_trace(out, cols)
            got_regs, got_mems = events(trace)
            cycles = trace[-1]["cycle"] + 1 if trace else 0
            ok = got_regs == exp_regs and got_mems == exp_mems and trace and trace[-1]["cycle"] is not None
            if ok:
                cells.append(f"PASS {cycles:>5} cyc CPI {cycles / ref['steps']:.2f}")
            else:
                failures += 1
                cells.append("FAIL")
                if got_regs != exp_regs:
                    i = first_diff(got_regs, exp_regs)
                    notes.append(f"  {cpu}: register write #{i}: got {fmt_reg(got_regs[i] if i < len(got_regs) else None)}"
                                 f", expected {fmt_reg(exp_regs[i] if i < len(exp_regs) else None)}"
                                 f" ({len(got_regs)} vs {len(exp_regs)} writes)")
                if got_mems != exp_mems:
                    i = first_diff(got_mems, exp_mems)
                    notes.append(f"  {cpu}: store #{i}: got {fmt_mem(got_mems[i] if i < len(got_mems) else None)}"
                                 f", expected {fmt_mem(exp_mems[i] if i < len(exp_mems) else None)}")
            if args.verbose:
                notes.append(f"  {cpu}: {len(trace)} cycles traced, {len(got_regs)} reg writes, {len(got_mems)} stores")
        print(f"{name:<22}" + "".join(f"{c:>34}" for c in cells) + f"   ({ref['steps']} instr)")
        for n in notes:
            print(n)
    shutil.rmtree(tmp, ignore_errors=True)
    print("ALL PASSED" if not failures else f"{failures} FAILURE(S)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
