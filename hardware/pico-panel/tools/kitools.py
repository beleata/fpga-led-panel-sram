"""Helpers to build a KiCad 9/10 schematic (.kicad_sch) programmatically.

Two pieces:

* ``extract_symbol`` pulls a symbol definition out of a KiCad ``.kicad_sym`` library so the
  generated schematic carries a self-contained ``lib_symbols`` section.
* ``Sch`` assembles the schematic: symbol instances, wires, labels, junctions, no-connects,
  plus a correct pin-position transform so wires actually land on pins.

The schematic coordinate system is Y-down; symbol library coordinates are Y-up, hence the
sign flip in ``pin_abs``. Verified against ``kicad-cli sch export netlist``.
"""
from __future__ import annotations

import math
import os
import re
import uuid

KICAD_SHARE = r"C:\Users\user\Tools\KiCad\share\kicad"
SYMBOL_DIR = os.path.join(KICAD_SHARE, "symbols")


# --------------------------------------------------------------------------- sexp utils
def _find_block(text: str, start: int) -> str:
    """Return the balanced s-expression starting at ``start`` (a '(' char)."""
    depth = 0
    i = start
    in_str = False
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValueError("unbalanced s-expression")


def _top_level_symbols(lib_text: str):
    """Yield (name, block_text) for every top-level symbol in a .kicad_sym file."""
    marker = "(symbol "
    pos = 0
    while True:
        idx = lib_text.find(marker, pos)
        if idx < 0:
            return
        # Cheap context check: only the few characters before the marker matter. Slicing the
        # whole prefix here would be O(n^2) on multi-megabyte libraries like the STM32 ones.
        before = lib_text[max(0, idx - 40):idx].rstrip()
        if before.endswith("(kicad_symbol_lib") or before.endswith(")"):
            m = re.match(r'\(symbol\s+"([^"]+)"', lib_text[idx:idx + 200])
            if m:
                block = _find_block(lib_text, idx)
                yield m.group(1), block
                pos = idx + len(block)
                continue
        pos = idx + len(marker)


class SymbolLibrary:
    """Cache of symbol definitions pulled from the installed KiCad libraries."""

    def __init__(self):
        self._cache: dict[str, str] = {}

    def get(self, lib_id: str) -> str:
        """``Device:R`` -> the definition text, fully resolved, renamed to the qualified id."""
        if lib_id in self._cache:
            return self._cache[lib_id]
        lib, _, name = lib_id.partition(":")
        # KiCad libraries define many parts as derived symbols ("extends"), sometimes in
        # chains; a schematic's lib_symbols section needs graphics and pins spelled out, so
        # walk to the root definition and layer the derived properties back on top.
        chain, cur = [], name
        for _ in range(8):
            block = self._raw(lib, cur)
            chain.append(block)
            m = re.search(r'\(extends\s+"([^"]+)"', block)
            if not m:
                break
            cur = m.group(1)
        resolved = chain[-1]
        for derived in reversed(chain[:-1]):
            resolved = self._merge(resolved, derived, lib_id)
        resolved = re.sub(r'\(symbol\s+"[^"]+"', f'(symbol "{lib_id}"', resolved, count=1)
        # Child unit symbols must carry the SHORT name of the symbol that owns them, otherwise
        # KiCad cannot attach the pins of a derived symbol to its units and refuses to load.
        resolved = re.sub(r'\(symbol\s+"[^"]*_(\d+_\d+)"',
                          lambda m: f'(symbol "{name}_{m.group(1)}"', resolved)
        self._cache[lib_id] = resolved
        return resolved

    def _raw(self, lib: str, name: str) -> str:
        path = os.path.join(SYMBOL_DIR, f"{lib}.kicad_sym")
        if not os.path.exists(path):
            raise FileNotFoundError(f"symbol library not found: {path}")
        text = open(path, encoding="utf-8", errors="replace").read()
        for sym_name, block in _top_level_symbols(text):
            if sym_name == name:
                return block
        raise KeyError(f"{name} not found in {lib}")

    @staticmethod
    def _merge(base: str, derived: str, new_name: str) -> str:
        """Copy the derived symbol's properties onto the base symbol's graphics and pins."""
        out = re.sub(r'\(symbol\s+"[^"]+"', f'(symbol "{new_name}"', base, count=1)
        out = re.sub(r"\n\s*\(extends\s+\"[^\"]+\"\)", "", out, count=1)

        def props(text):
            found = {}
            pos = 0
            while True:
                i = text.find("(property ", pos)
                if i < 0:
                    break
                blk = _find_block(text, i)
                m = re.match(r'\(property\s+"([^"]+)"', blk)
                if m:
                    found[m.group(1)] = blk
                pos = i + len(blk)
            return found

        base_props, derived_props = props(out), props(derived)
        for pname, dblk in derived_props.items():
            if pname in base_props:
                out = out.replace(base_props[pname], dblk, 1)
            else:
                out = out.replace("\n\t(symbol ", "\n\t" + dblk + "\n\t(symbol ", 1)
        return out

    def add_custom(self, lib_id: str, block: str):
        """Register a hand-written symbol definition (custom parts and extra power nets)."""
        self._cache[lib_id] = block
        return lib_id

    @staticmethod
    def pin_blocks(block: str):
        """Yield the balanced s-expression of every pin definition in a symbol."""
        pos = 0
        while True:
            i = block.find("(pin ", pos)
            if i < 0:
                return
            blk = _find_block(block, i)
            yield blk
            pos = i + len(blk)

    @staticmethod
    def pin_offsets(block: str) -> dict[str, tuple[float, float, float]]:
        """Map pin number -> (x, y, angle) in library coordinates, angle in degrees."""
        pins: dict[str, tuple[float, float, float]] = {}
        for blk in SymbolLibrary.pin_blocks(block):
            m_at = re.search(r"\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\)", blk)
            m_num = re.search(r'\(number\s+"([^"]+)"', blk)
            if m_at and m_num:
                pins[m_num.group(1)] = (float(m_at.group(1)), float(m_at.group(2)),
                                        float(m_at.group(3)))
        return pins

    @staticmethod
    def pin_name_map(block: str) -> dict[str, str]:
        """Map pin number -> pin name (empty string when the pin is unnamed)."""
        out: dict[str, str] = {}
        for blk in SymbolLibrary.pin_blocks(block):
            m_num = re.search(r'\(number\s+"([^"]+)"', blk)
            m_name = re.search(r'\(name\s+"([^"]*)"', blk)
            if m_num:
                out[m_num.group(1)] = m_name.group(1) if m_name else ""
        return out


def power_symbol(lib_id: str, net: str, up: bool = True) -> str:
    """Minimal power symbol for an arbitrary rail name (KiCad's power lib only has the basics)."""
    y = 2.54 if up else -2.54
    arrow = ("(polyline (pts (xy -0.762 1.27) (xy 0 2.54)) (stroke (width 0) (type default)) "
             "(fill (type none))) "
             "(polyline (pts (xy 0 0) (xy 0 2.54)) (stroke (width 0) (type default)) "
             "(fill (type none))) "
             "(polyline (pts (xy 0 2.54) (xy 0.762 1.27)) (stroke (width 0) (type default)) "
             "(fill (type none)))")
    if not up:
        arrow = arrow.replace("2.54", "-2.54").replace("1.27", "-1.27")
    return f'''\t\t(symbol "{lib_id}"
\t\t\t(power)
\t\t\t(pin_names
\t\t\t\t(offset 0)
\t\t\t)
\t\t\t(exclude_from_sim no)
\t\t\t(in_bom no)
\t\t\t(on_board yes)
\t\t\t(property "Reference" "#PWR"
\t\t\t\t(at 0 {'-3.81' if up else '3.81'} 0)
\t\t\t\t(effects
\t\t\t\t\t(font
\t\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t\t)
\t\t\t\t\t(hide yes)
\t\t\t\t)
\t\t\t)
\t\t\t(property "Value" "{net}"
\t\t\t\t(at 0 {y} 0)
\t\t\t\t(effects
\t\t\t\t\t(font
\t\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t\t)
\t\t\t\t)
\t\t\t)
\t\t\t(symbol "{net}_0_1"
\t\t\t\t{arrow}
\t\t\t)
\t\t\t(symbol "{net}_1_1"
\t\t\t\t(pin power_in line
\t\t\t\t\t(at 0 0 {'90' if up else '270'})
\t\t\t\t\t(length 0)
\t\t\t\t\t(name "{net}"
\t\t\t\t\t\t(effects
\t\t\t\t\t\t\t(font
\t\t\t\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t\t\t\t)
\t\t\t\t\t\t)
\t\t\t\t\t)
\t\t\t\t\t(number "1"
\t\t\t\t\t\t(effects
\t\t\t\t\t\t\t(font
\t\t\t\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t\t\t\t)
\t\t\t\t\t\t)
\t\t\t\t\t)
\t\t\t\t)
\t\t\t)
\t\t)'''


def pin_abs(pin_xy, inst_xy, rot=0, mirror=None):
    """Absolute schematic position of a pin, given the instance placement.

    KiCad rotates the symbol in library space (Y up) and only then maps it to the schematic
    (Y down). Rotating after the flip - the intuitive order - quietly mirrors every 90/270
    degree part, which swaps the pins of diodes and LEDs. Verified against kicad-cli netlists.
    """
    x, y = pin_xy
    a = math.radians(rot)
    xr = x * math.cos(a) - y * math.sin(a)
    yr = x * math.sin(a) + y * math.cos(a)
    x, y = xr, -yr
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    return (round(inst_xy[0] + x, 4), round(inst_xy[1] + y, 4))


# --------------------------------------------------------------------------- builder
def uid():
    return str(uuid.uuid4())


GRID = 1.27


def snap(v):
    """Put a coordinate on the 1.27 mm schematic grid (ERC flags anything else)."""
    return round(round(float(v) / GRID) * GRID, 4)


def snap_pt(p):
    return (snap(p[0]), snap(p[1]))


def _esc(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Sch:
    def __init__(self, project: str, paper: str = "A3"):
        self.project = project
        self.paper = paper
        self.root_uuid = uid()
        self.libs = SymbolLibrary()
        self.used_libs: dict[str, str] = {}
        self.body: list[str] = []
        self.components: list[dict] = []
        self.segments: list[tuple] = []          # every wire segment, for collision checking
        self.pin_nodes: list[tuple] = []         # (point, ref, pin, net) for every wired pin

    # ------------------------------------------------------------------ symbols
    def symbol(self, lib_id, ref, value, at, footprint="", lcsc="", rot=0, mirror=None,
               props=None, hide_value=False, extra_pins=()):
        block = self.libs.get(lib_id)
        self.used_libs[lib_id] = block
        pins = self.libs.pin_offsets(block)
        x, y = snap_pt(at)
        lines = ["\t(symbol",
                 f'\t\t(lib_id "{lib_id}")',
                 f"\t\t(at {x} {y} {rot})"]
        if mirror:
            lines.append(f"\t\t(mirror {mirror})")
        lines += ["\t\t(unit 1)",
                  "\t\t(exclude_from_sim no)",
                  "\t\t(in_bom yes)",
                  "\t\t(on_board yes)",
                  "\t\t(dnp no)",
                  f'\t\t(uuid "{uid()}")']

        def prop(name, val, px, py, hide=False, size=1.27):
            eff = (f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size {size} {size})\n\t\t\t\t)\n'
                   + ("\t\t\t\t(hide yes)\n" if hide else "") + "\t\t\t)")
            lines.append(f'\t\t(property "{name}" "{_esc(val)}"')
            lines.append(f"\t\t\t(at {px} {py} 0)")
            lines.append(eff)
            lines.append("\t\t)")

        def native_position(name, fallback):
            start = block.find(f'(property "{name}"')
            field = _find_block(block, start) if start >= 0 else ''
            match = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', field)
            return pin_abs((float(match[1]), float(match[2])), (x, y), rot, mirror) if match else fallback
        rx, ry = native_position('Reference', (x + 2.54, y - 1.27))
        vx, vy = native_position('Value', (x + 2.54, y + 1.27))
        prop("Reference", ref, rx, ry)
        prop("Value", value, vx, vy, hide=hide_value)
        prop("Footprint", footprint, x, y, hide=True)
        prop("Datasheet", "~", x, y, hide=True)
        if lcsc:
            prop("LCSC", lcsc, x, y, hide=True)
        for k, v in (props or {}).items():
            prop(k, v, x, y, hide=True)

        for num in sorted(pins, key=lambda n: (len(n), n)):
            if num.startswith("~"):
                continue
            lines.append(f'\t\t(pin "{num}"')
            lines.append(f'\t\t\t(uuid "{uid()}")')
            lines.append("\t\t)")
        lines.append(f'\t\t(instances\n\t\t\t(project "{self.project}"')
        lines.append(f'\t\t\t\t(path "/{self.root_uuid}"')
        lines.append(f'\t\t\t\t\t(reference "{ref}")')
        lines.append("\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)")
        lines.append("\t)")

        self.body.append("\n".join(lines))
        self.components.append({"ref": ref, "lib_id": lib_id, "at": at, "rot": rot,
                                "mirror": mirror, "pins": pins, "value": value,
                                "footprint": footprint, "lcsc": lcsc})
        return self.components[-1]

    def power(self, net, at, rot=0):
        """Place a power symbol such as power:GND / power:+5V."""
        lib_id = {"GND": "power:GND", "+5V": "power:+5V", "+3V3": "power:+3V3"}.get(net)
        if lib_id is None:
            raise KeyError(f"add a custom power symbol for {net}")
        ref = f"#PWR{len([c for c in self.components if c['ref'].startswith('#PWR')]) + 1:03d}"
        return self.symbol(lib_id, ref, net, at, rot=rot, hide_value=True)

    def pin(self, comp, number):
        """Absolute position of a pin, given its number or its name."""
        num = str(number)
        if num not in comp["pins"]:
            num = self.num(comp, number)
        return pin_abs(comp["pins"][num][:2], comp["at"], comp["rot"], comp["mirror"])

    def num(self, comp, name_or_num):
        """Resolve a pin name (e.g. 'VDD') or number to the pin number."""
        block = self.libs.get(comp["lib_id"])
        names = self.libs.pin_name_map(block)
        for num, nm in names.items():
            if nm == name_or_num:
                return num
        if str(name_or_num) in comp["pins"]:
            return str(name_or_num)
        raise KeyError(f"pin {name_or_num!r} not on {comp['ref']} ({comp['lib_id']}); "
                       f"names={sorted(set(names.values()))}")

    def nums(self, comp, name):
        """Every pin number carrying a given name (power pins are stacked duplicates)."""
        block = self.libs.get(comp["lib_id"])
        names = self.libs.pin_name_map(block)
        return [n for n, nm in names.items() if nm == name]

    def dump_library(self, path, lib_prefix="plc8x8:"):
        """Write the hand-made symbols out as a real .kicad_sym so the library is resolvable."""
        entries = []
        for lib_id, block in sorted(self.libs._cache.items()):
            if not lib_id.startswith(lib_prefix):
                continue
            short = lib_id.split(":", 1)[1]
            renamed = re.sub(r'\(symbol\s+"[^"]+"', f'(symbol "{short}"', block, count=1)
            renamed = re.sub(r'\(symbol\s+"[^"]*_(\d+_\d+)"',
                             lambda m: f'(symbol "{short}_{m.group(1)}"', renamed)
            lines = renamed.splitlines()
            pad = min((len(l) - len(l.lstrip("\t")) for l in lines if l.strip()), default=0)
            entries.append("\n".join("\t" + l[pad:] if l.strip() else l for l in lines))
        text = ("(kicad_symbol_lib\n\t(version 20241209)\n\t(generator \"plc8x8-generator\")\n"
                "\t(generator_version \"1.0\")\n" + "\n".join(entries) + "\n)\n")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def pin_dir(self, comp, name_or_num):
        """Unit vector pointing away from the symbol body at that pin (schematic coords)."""
        num = self.num(comp, name_or_num)
        _, _, ang = comp["pins"][num]
        a = math.radians((ang + 180) % 360)
        dx, dy = math.cos(a), math.sin(a)          # library space, Y up
        r = math.radians(comp["rot"])
        dx, dy = dx * math.cos(r) - dy * math.sin(r), dx * math.sin(r) + dy * math.cos(r)
        dy = -dy                                   # same rotate-then-flip order as pin_abs
        if comp["mirror"] == "x":
            dy = -dy
        elif comp["mirror"] == "y":
            dx = -dx
        return (round(dx, 4), round(dy, 4))

    def net(self, comp, name_or_num, net_name, length=2.54, side=None, label_rot=0):
        """Wire a stub out of a pin and label it - the workhorse of this schematic."""
        num = self.num(comp, name_or_num)
        p = self.pin(comp, num)
        dx, dy = self.pin_dir(comp, num)
        if side == "x":      # force horizontal
            dx, dy = (1.0, 0.0) if dx >= 0 else (-1.0, 0.0)
        elif side == "y":    # force vertical
            dx, dy = (0.0, 1.0) if dy >= 0 else (0.0, -1.0)
        end = (round(p[0] + dx * length, 4), round(p[1] + dy * length, 4))
        self.wire(p, end)
        if label_rot == 90 and dy > 0:
            label_rot = 270
        self.label(net_name, end, rot=label_rot,
                   justify="right bottom" if dx < 0 else "left bottom")
        self.pin_nodes.append((snap_pt(p), comp["ref"], str(num), net_name, snap_pt(end)))
        return end

    def verify_label_collisions(self):
        """A label landing on a foreign pin, or on another net's label, merges those nets.

        This is the sneakiest failure mode of a generated schematic: every pin and stub looks
        fine on its own, and ERC only reports a vague "multiple net names" much later.
        """
        pin_at = {pt: (ref, pin, net) for pt, ref, pin, net, _e in self.pin_nodes}
        by_point = {}
        for pt, ref, pin, net, end in self.pin_nodes:
            other = pin_at.get(end)
            if other and other[2] != net:
                yield ("label-on-pin", end, other, (ref, pin, net))
            seen = by_point.get(end)
            if seen and seen[3] != net:
                yield ("label-on-label", end, seen, (pt, ref, pin, net, end))
            by_point.setdefault(end, (pt, ref, pin, net, end))

    def verify(self):
        """Report connection points where a foreign wire passes through a pin.

        KiCad happily merges coincident pins and wires, so a stub drawn across a neighbour's
        pin silently shorts two nets. Every such case shows up here before KiCad sees it.
        """
        problems = []
        for pt, ref, pin, net, end in self.pin_nodes:
            # both the pin itself and the far end of its stub (where the label sits) must be
            # free of foreign wires, otherwise KiCad merges the two nets at that point
            for probe in (pt, end):
                hit = None
                for seg in self.segments:
                    (x1, y1), (x2, y2) = seg
                    if (x1, y1) == probe or (x2, y2) == probe:
                        continue                      # this is the pin's own stub
                    if x1 == x2 == probe[0] and min(y1, y2) < probe[1] < max(y1, y2):
                        hit = seg
                    elif y1 == y2 == probe[1] and min(x1, x2) < probe[0] < max(x1, x2):
                        hit = seg
                    if hit:
                        break
                if hit:
                    problems.append((ref, pin, net, probe, hit))
                    break
        return problems

    def verify_crossings(self):
        """Report interior intersections between two wires.

        Crossing wires touch electrically, so a generator that never intends a crossing
        should find none; every hit here means two nets were merged.
        """
        out = []
        segs = self.segments
        for i, ((ax1, ay1), (ax2, ay2)) in enumerate(segs):
            for (bx1, by1), (bx2, by2) in segs[i + 1:]:
                if ax1 == ax2 and by1 == by2:          # vertical a, horizontal b
                    if min(ay1, ay2) < by1 < max(ay1, ay2) and min(bx1, bx2) < ax1 < max(bx1, bx2):
                        out.append(((ax1, by1), ((ax1, ay1), (ax2, ay2)), ((bx1, by1), (bx2, by2))))
                elif ay1 == ay2 and bx1 == bx2:        # horizontal a, vertical b
                    if min(ax1, ax2) < bx1 < max(ax1, ax2) and min(by1, by2) < ay1 < max(by1, by2):
                        out.append(((bx1, ay1), ((ax1, ay1), (ax2, ay2)), ((bx1, by1), (bx2, by2))))
        return out

    def verify_pin_overlap(self):
        """Report two pins of different nets sitting on exactly the same point."""
        seen, clashes = {}, []
        for pt, ref, pin, net, _end in self.pin_nodes:
            if pt in seen and seen[pt][3] != net:
                clashes.append((pt, seen[pt], (ref, pin, net)))
            seen.setdefault(pt, (pt, ref, pin, net))
        return clashes

    def pwr(self, net_name, at):
        """Place a power symbol for a rail (creating it on first use)."""
        builtin = {"GND": "power:GND", "+5V": "power:+5V", "+3V3": "power:+3V3"}
        lib_id = builtin.get(net_name, f"plc8x8:{net_name}")
        if net_name not in builtin:
            self.libs.add_custom(lib_id, power_symbol(lib_id, net_name, up=True))
        return self.symbol(lib_id, f"#PWR{len([c for c in self.components if c['ref'].startswith('#PWR')]) + 1:03d}",
                           net_name, at, hide_value=True)

    def flag(self, at):
        """PWR_FLAG: tells ERC that a rail is intentionally driven here."""
        return self.symbol("power:PWR_FLAG",
                           f"#FLG{len([c for c in self.components if c['ref'].startswith('#FLG')]) + 1:03d}",
                           "PWR_FLAG", at)

    # ------------------------------------------------------------------ graphics / nets
    def wire(self, *points):
        pts = list(points)
        for i in range(len(pts) - 1):
            (x1, y1), (x2, y2) = snap_pt(pts[i]), snap_pt(pts[i + 1])
            self.segments.append(((x1, y1), (x2, y2)))
            self.body.append(
                f"\t(wire\n\t\t(pts\n\t\t\t(xy {x1} {y1}) (xy {x2} {y2})\n\t\t)\n"
                f"\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n"
                f'\t\t(uuid "{uid()}")\n\t)')

    def junction(self, at):
        at = snap_pt(at)
        self.body.append(f"\t(junction\n\t\t(at {at[0]} {at[1]})\n\t\t(diameter 0)\n"
                         f"\t\t(color 0 0 0 0)\n\t\t(uuid \"{uid()}\")\n\t)")

    def label(self, text, at, rot=0, justify="left bottom"):
        at = snap_pt(at)
        self.body.append(
            f'\t(label "{_esc(text)}"\n\t\t(at {at[0]} {at[1]} {rot})\n'
            f"\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n"
            f"\t\t\t(justify {justify})\n\t\t)\n\t\t(uuid \"{uid()}\")\n\t)")

    def no_connect(self, at):
        at = snap_pt(at)
        self.body.append(f"\t(no_connect\n\t\t(at {at[0]} {at[1]})\n\t\t(uuid \"{uid()}\")\n\t)")

    def text(self, text, at, size=2.0):
        self.body.append(
            f'\t(text "{_esc(text)}"\n\t\t(exclude_from_sim no)\n\t\t(at {at[0]} {at[1]} 0)\n'
            f"\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {size} {size})\n\t\t\t)\n"
            f"\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid \"{uid()}\")\n\t)")

    # ------------------------------------------------------------------ output
    def save(self, path, title="", rev="v1", company=""):
        out = ["(kicad_sch",
               "\t(version 20250114)",
               '\t(generator "eeschema")',
               '\t(generator_version "9.0")',
               f'\t(uuid "{self.root_uuid}")',
               f'\t(paper "{self.paper}")',
               "\t(title_block",
               f'\t\t(title "{_esc(title)}")',
               f'\t\t(rev "{_esc(rev)}")',
               f'\t\t(company "{_esc(company)}")',
               "\t)"]
        out.append("\t(lib_symbols")
        for lib_id, block in sorted(self.used_libs.items()):
            lines = block.splitlines()
            pad = min((len(l) - len(l.lstrip("\t")) for l in lines if l.strip()), default=0)
            out.append("\n".join("\t\t" + l[pad:] if l.strip() else l for l in lines))
        out.append("\t)" )
        out.extend(self.body)
        out.append('\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)')
        out.append(")")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        return path
