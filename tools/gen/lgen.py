"""Tiny Logisim-evolution .circ generator.

Circuits are described as components plus *net names* on their ports.
Building is two-pass:

1. every component is written without wires and the file is loaded by
   Logisim itself (tools/portdump/PortDump.java) to learn the exact location
   of every port;
2. each connected port gets a short wire stub pointing away from its
   component, ending in a Tunnel labelled with the net name (or in a Constant
   when the port is tied to a value).

Ports are addressed by index (Logisim end order) or, for subcircuit
instances, by the name of the pin inside the subcircuit.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
JAVA = os.environ.get("JAVA", "/opt/homebrew/opt/openjdk@21/bin/java")
LOGISIM_JAR = os.environ.get(
    "LOGISIM_JAR",
    "/Applications/Logisim-evolution.app/Contents/app/logisim-evolution-4.1.0-all.jar",
)
PORTDUMP_DIR = os.path.join(ROOT, "tools", "portdump")

LIB = {"wiring": "0", "gates": "1", "plexers": "2", "arith": "3", "memory": "5", "io": "6", "base": "9"}

STUB = 20


@dataclass
class Tie:
    """Port tied to a constant value instead of a net."""

    value: int


@dataclass
class Comp:
    lib: str | None  # None for subcircuit instances
    name: str
    x: int
    y: int
    attrs: dict = field(default_factory=dict)
    conns: dict = field(default_factory=dict)  # port key -> net name | Tie
    stub: int = STUB

    def xml(self) -> str:
        lib = f' lib="{self.lib}"' if self.lib is not None else ""
        body = "".join(
            # multi-line values (memory contents) use element text, as Logisim writes them
            f'\n      <a name="{k}">{escape(str(v))}</a>' if "\n" in str(v) else
            f'\n      <a name="{k}" val="{escape(str(v), {chr(34): "&quot;"})}"/>'
            for k, v in sorted(self.attrs.items())
        )
        return f'    <comp{lib} loc="({self.x},{self.y})" name="{escape(self.name)}">{body}\n    </comp>'


class Circuit:
    def __init__(self, name: str):
        self.name = name
        self.comps: list[Comp] = []
        self.texts: list[tuple[int, int, str]] = []
        self.wires: list[tuple[int, int, int, int]] = []

    # -- generic -----------------------------------------------------------
    def add(self, lib, name, x, y, attrs=None, conns=None, stub=STUB) -> Comp:
        assert x % 10 == 0 and y % 10 == 0, (name, x, y)
        c = Comp(LIB[lib] if lib else None, name, x, y, dict(attrs or {}), dict(conns or {}), stub)
        self.comps.append(c)
        return c

    def text(self, x, y, s):
        self.texts.append((x, y, s))

    # -- wiring library ----------------------------------------------------
    def pin_in(self, label, width, x, y, net=None):
        return self.add("wiring", "Pin", x, y,
                        {"appearance": "classic", "label": label, "width": width, "radix": 16 if width > 1 else 2},
                        {0: net or label})

    def pin_out(self, label, width, x, y, net=None):
        return self.add("wiring", "Pin", x, y,
                        {"appearance": "classic", "label": label, "width": width, "type": "output",
                         "facing": "west", "radix": 16 if width > 1 else 2},
                        {0: net or label})

    def const(self, value, width, x, y, net):
        return self.add("wiring", "Constant", x, y, {"width": width, "value": hex(value)}, {0: net})

    def splitter(self, x, y, incoming, groups, net_in, nets_out, facing="east"):
        """groups: list of (lo, hi) bit ranges, one per fan-out end."""
        attrs = {"incoming": incoming, "fanout": len(groups), "facing": facing, "appear": "center",
                 "spacing": 2}
        owner = ["none"] * incoming
        for gi, (lo, hi) in enumerate(groups):
            for b in range(lo, hi + 1):
                owner[b] = gi
        for b in range(incoming):
            attrs[f"bit{b}"] = owner[b]
        conns = {0: net_in}
        for i, n in enumerate(nets_out):
            if n is not None:
                conns[i + 1] = n
        return self.add("wiring", "Splitter", x, y, attrs, conns)

    def extend(self, x, y, win, wout, kind, net_in, net_out):
        # ends: [0] out, [1] in
        return self.add("wiring", "Bit Extender", x, y,
                        {"in_width": win, "out_width": wout, "type": kind}, {0: net_out, 1: net_in})

    def clock(self, x, y, net):
        return self.add("wiring", "Clock", x, y, {}, {0: net})

    # -- gates ---------------------------------------------------------------
    def gate(self, kind, x, y, ins, out, width=1, negate=None):
        """kind: AND OR XOR NAND NOR XNOR. ends: [0] out, [1..n] inputs.
        negate: 0-based indexes of inputs to invert."""
        n = len(ins)
        attrs = {"inputs": n, "width": width, "size": 30}
        conns = {0: out}
        for i, net in enumerate(ins):
            conns[i + 1] = net
        if negate:
            for i in negate:
                attrs[f"negate{i}"] = "true"
        return self.add("gates", f"{kind} Gate", x, y, attrs, conns)

    def not_(self, x, y, a, out, width=1):
        return self.add("gates", "NOT Gate", x, y, {"width": width, "size": 20}, {0: out, 1: a})

    # -- plexers -------------------------------------------------------------
    def mux(self, x, y, sel_bits, width, ins, sel, out):
        """ends: d0..d(n-1), sel, out."""
        n = 1 << sel_bits
        conns = {}
        for i, net in enumerate(ins):
            if net is not None:
                conns[i] = net
        conns[n] = sel
        conns[n + 1] = out
        return self.add("plexers", "Multiplexer", x, y,
                        {"select": sel_bits, "width": width, "enable": "false"}, conns)

    def decoder(self, x, y, sel_bits, sel, outs):
        """ends: q0..q(n-1), sel."""
        n = 1 << sel_bits
        conns = {i: net for i, net in enumerate(outs) if net is not None}
        conns[n] = sel
        return self.add("plexers", "Decoder", x, y, {"select": sel_bits, "enable": "false"}, conns)

    # -- arithmetic ------------------------------------------------------------
    def adder(self, x, y, width, a, b, out, cin=None, cout=None):
        conns = {0: a, 1: b, 2: out}
        if cin is not None:
            conns[3] = cin
        if cout is not None:
            conns[4] = cout
        return self.add("arith", "Adder", x, y, {"width": width}, conns)

    def comparator(self, x, y, width, a, b, gt=None, eq=None, lt=None, signed=True):
        conns = {0: a, 1: b}
        for i, n in ((2, gt), (3, eq), (4, lt)):
            if n is not None:
                conns[i] = n
        return self.add("arith", "Comparator", x, y,
                        {"width": width, "mode": "twosComplement" if signed else "unsigned"}, conns)

    # -- memory ----------------------------------------------------------------
    def register(self, x, y, width, d, q, clk, en=None, rst=None, label=""):
        """ends: [0] Q, [1] D, [2] clk, [3] reset, [4] enable."""
        conns = {0: q, 1: d, 2: clk}
        if rst is not None:
            conns[3] = rst
        if en is not None:
            conns[4] = en
        attrs = {"width": width, "appearance": "logisim_evolution", "trigger": "rising"}
        if label:
            attrs["label"] = label
            attrs["showInTab"] = "true"
        return self.add("memory", "Register", x, y, attrs, conns)

    # -- subcircuits -------------------------------------------------------------
    def sub(self, name, x, y, conns, label=""):
        attrs = {"label": label} if label else {}
        return self.add(None, name, x, y, attrs, conns)

    # -- output ----------------------------------------------------------------
    def xml(self, with_stubs: bool) -> str:
        parts = [
            f'  <circuit name="{escape(self.name)}">',
            '    <a name="appearance" val="logisim_evolution"/>',
            f'    <a name="circuit" val="{escape(self.name)}"/>',
            '    <a name="circuitnamedboxfixedsize" val="true"/>',
            '    <a name="simulationFrequency" val="1.0"/>',
        ]
        parts += [c.xml() for c in self.comps]
        for x, y, s in self.texts:
            parts.append(f'    <comp lib="9" loc="({x},{y})" name="Text">\n      <a name="text" val="{escape(s)}"/>\n    </comp>')
        if with_stubs:
            parts += self._stub_xml
        for x0, y0, x1, y1 in self.wires:
            parts.append(f'    <wire from="({x0},{y0})" to="({x1},{y1})"/>')
        parts.append("  </circuit>")
        return "\n".join(parts)

    _stub_xml: list[str] = []


HEADER = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<project source="4.1.0" version="1.0">
  This file is intended to be loaded by Logisim-evolution v4.1.0(https://github.com/logisim-evolution/).

  <lib desc="#Wiring" name="0">
    <tool name="Pin">
      <a name="appearance" val="classic"/>
    </tool>
  </lib>
  <lib desc="#Gates" name="1"/>
  <lib desc="#Plexers" name="2"/>
  <lib desc="#Arithmetic" name="3"/>
  <lib desc="#FPArithmetic" name="4"/>
  <lib desc="#Memory" name="5"/>
  <lib desc="#I/O" name="6"/>
  <lib desc="#TTL" name="7"/>
  <lib desc="#TCL" name="8"/>
  <lib desc="#Base" name="9"/>
  <lib desc="#BFH-Praktika" name="10"/>
  <lib desc="#Input/Output-Extra" name="11"/>
  <lib desc="#Soc" name="12"/>
  <main name="{main}"/>
  <options>
    <a name="gateUndefined" val="ignore"/>
    <a name="simlimit" val="1000"/>
    <a name="simrand" val="0"/>
  </options>
  <mappings>
    <tool lib="9" map="Button2" name="Poke Tool"/>
    <tool lib="9" map="Button3" name="Menu Tool"/>
    <tool lib="9" map="Ctrl Button1" name="Menu Tool"/>
  </mappings>
  <toolbar>
    <tool lib="9" name="Poke Tool"/>
    <tool lib="9" name="Edit Tool"/>
    <tool lib="9" name="Wiring Tool"/>
    <tool lib="9" name="Text Tool"/>
    <sep/>
    <tool lib="0" name="Pin"/>
    <tool lib="0" name="Pin">
      <a name="facing" val="west"/>
      <a name="type" val="output"/>
    </tool>
    <sep/>
    <tool lib="1" name="NOT Gate"/>
    <tool lib="1" name="AND Gate"/>
    <tool lib="1" name="OR Gate"/>
    <tool lib="1" name="XOR Gate"/>
    <tool lib="1" name="NAND Gate"/>
    <tool lib="1" name="NOR Gate"/>
    <sep/>
    <tool lib="5" name="D Flip-Flop"/>
    <tool lib="5" name="Register"/>
  </toolbar>
"""


def portdump(path: str) -> dict:
    cp = f"{LOGISIM_JAR}:{PORTDUMP_DIR}"
    r = subprocess.run([JAVA, "-Djava.awt.headless=true", "-cp", cp, "PortDump", path],
                       capture_output=True, text=True, timeout=300)
    out = r.stdout
    start = out.find("{")
    if r.returncode != 0 or start < 0:
        raise RuntimeError(f"PortDump failed:\n{r.stderr[-3000:]}\n{out[-2000:]}")
    return json.loads(out[start:])


class Project:
    def __init__(self, main: str):
        self.main = main
        self.circuits: list[Circuit] = []
        self.raw: list[str] = []  # verbatim <circuit> blocks kept from another file

    def circuit(self, name) -> Circuit:
        c = Circuit(name)
        self.circuits.append(c)
        return c

    def keep_raw(self, xml_block: str):
        self.raw.append(xml_block)

    def _write(self, path, with_stubs):
        with open(path, "w") as f:
            f.write(HEADER.replace("{main}", escape(self.main)))
            for c in self.circuits:
                f.write(c.xml(with_stubs) + "\n")
            for r in self.raw:
                f.write(r + "\n")
            f.write("</project>\n")

    def build(self, path: str) -> dict:
        tmp = path + ".pass1.circ"
        for c in self.circuits:
            c._stub_xml = []
        self._write(tmp, with_stubs=False)
        dump = portdump(tmp)
        os.remove(tmp)
        for c in self.circuits:
            self._resolve(c, dump[c.name])
        self._write(path, with_stubs=True)
        return self.check(path)

    # ------------------------------------------------------------------------
    def _resolve(self, c: Circuit, info: dict):
        by_loc = {}
        for d in info["comps"]:
            by_loc.setdefault((d["name"], d["loc"][0], d["loc"][1]), []).append(d)
        out = []
        c.net_ends = {}
        for comp in c.comps:
            if not comp.conns:
                continue
            key = (comp.name, comp.x, comp.y)
            cands = by_loc.get(key)
            if not cands:
                raise RuntimeError(f"{c.name}: component {key} not found after load")
            d = cands[0]
            bx, by, bw, bh = d["bounds"]
            placed = []
            for pk, net in comp.conns.items():
                port = self._port(c, comp, d, pk)
                px, py = port["x"], port["y"]
                # Pick the side of the bounding box the port sits on.
                dists = {"W": abs(px - bx), "E": abs(px - (bx + bw)), "N": abs(py - by), "S": abs(py - (by + bh))}
                placed.append((pk, net, port, min(dists, key=dists.get)))
            # Ports closer than 20px on the same side get alternating stub
            # lengths so their tunnels do not sit on top of each other.
            lengths = {}
            for sd in "WENS":
                group = sorted((p for p in placed if p[3] == sd),
                               key=lambda p: p[2]["y"] if sd in "WE" else p[2]["x"])
                coords = [p[2]["y"] if sd in "WE" else p[2]["x"] for p in group]
                dense = any(b - a < 20 for a, b in zip(coords, coords[1:]))
                longest = max((len(p[1]) if isinstance(p[1], str) else 2 + (p[2]["w"] + 3) // 4
                               for p in group), default=0)
                for i, p in enumerate(group):
                    extra = (((longest * 7 + 30) // 10) * 10) if dense and i % 2 else 0
                    lengths[p[0]] = comp.stub + extra
            for pk, net, port, side in placed:
                px, py, w = port["x"], port["y"], port["w"]
                L = lengths[pk]
                ex, ey = {"W": (px - L, py), "E": (px + L, py), "N": (px, py - L), "S": (px, py + L)}[side]
                facing = {"W": "east", "E": "west", "N": "south", "S": "north"}[side]
                out.append(f'    <wire from="({min(px, ex)},{min(py, ey)})" to="({max(px, ex)},{max(py, ey)})"/>')
                if isinstance(net, Tie):
                    out.append(f'    <comp lib="0" loc="({ex},{ey})" name="Constant">\n'
                               f'      <a name="facing" val="{facing}"/>\n'
                               f'      <a name="value" val="{hex(net.value)}"/>\n'
                               f'      <a name="width" val="{w}"/>\n    </comp>')
                else:
                    out.append(f'    <comp lib="0" loc="({ex},{ey})" name="Tunnel">\n'
                               f'      <a name="facing" val="{facing}"/>\n'
                               f'      <a name="label" val="{escape(net)}"/>\n'
                               f'      <a name="width" val="{w}"/>\n    </comp>')
                    c.net_ends.setdefault(net, []).append((comp.name, pk, port["dir"], w))
        c._stub_xml = out

    @staticmethod
    def _port(c, comp, d, pk):
        ports = d["ports"]
        if isinstance(pk, int):
            if pk >= len(ports):
                raise RuntimeError(f"{c.name}: {comp.name}@({comp.x},{comp.y}) has no port {pk} (has {len(ports)})")
            return ports[pk]
        for p in ports:
            if p["tip"] == pk or p["tip"].split(":")[0].strip() == pk:
                return p
        raise RuntimeError(f"{c.name}: {comp.name}@({comp.x},{comp.y}) has no port named {pk!r}; "
                           f"tips={[p['tip'] for p in ports]}")

    def check(self, path) -> dict:
        """Reload the final file and report problems per circuit."""
        dump = portdump(path)
        problems = {}
        for c in self.circuits:
            info = dump[c.name]
            errs = []
            if info["widthErrors"]:
                errs.append(f"width conflicts at {info['widthErrors']}")
            for net, ends in c.net_ends.items():
                drivers = [e for e in ends if e[2] in ("out", "io")]
                widths = {e[3] for e in ends}
                if len(ends) < 2:
                    errs.append(f"net {net!r} has a single end {ends}")
                elif not drivers:
                    errs.append(f"net {net!r} has no driver {ends}")
                if len(widths) > 1:
                    errs.append(f"net {net!r} mixes widths {ends}")
            # Every connected port must touch exactly its own stub, and an
            # unconnected port nothing at all; anything else is an accidental
            # short between neighbouring stubs/components.
            for d in info["comps"]:
                for i, p in enumerate(d["ports"]):
                    if p["touch"] > 1 and d["name"] not in ("Tunnel",):
                        errs.append(f"port {i} of {d['name']}@{d['loc']} touches {p['touch']} things")
                    if d["name"] == "Tunnel" and p["touch"] != 1:
                        errs.append(f"tunnel {d['label']!r}@{d['loc']} touches {p['touch']} things")
            # Bodies (including stub tunnels/constants) must not overlap.
            # (shrunk by 2px: 22px-tall tunnels on a 20px pitch just touch)
            boxes = [([d["bounds"][0] + 2, d["bounds"][1] + 2, d["bounds"][2] - 4, d["bounds"][3] - 4],
                      d["name"], d["loc"], d["label"]) for d in info["comps"] if d["name"] != "Text"]
            boxes.sort(key=lambda b: b[0][0])
            for i, (b1, n1, l1, lab1) in enumerate(boxes):
                for b2, n2, l2, lab2 in boxes[i + 1:]:
                    if b2[0] >= b1[0] + b1[2]:
                        break
                    if b2[1] < b1[1] + b1[3] and b1[1] < b2[1] + b2[3]:
                        errs.append(f"overlap: {n1}{l1}{lab1!r} with {n2}{l2}{lab2!r}")
            if errs:
                problems[c.name] = errs
        return problems
