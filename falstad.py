"""Export supported circuit components to CircuitJS text and browser URLs.

Format references: CircuitElm, VoltageElm, LEDElm, and SwitchElm in
https://github.com/sharpie7/circuitjs1/tree/master/src/com/lushprojects/circuitjs1/client
The text records below are generated from our model, not copied solver code.
"""

import argparse
from pathlib import Path
from urllib.parse import urlencode

from components import contact_closed, terminal_ids, COMPONENT_NAMES
from layout import series_parallel_layout
from topology import parse_topology


FALSTAD_URL = "https://www.falstad.com/circuit/circuitjs.html"
SUPPORTED_TYPES = set(COMPONENT_NAMES)


class FalstadExportError(ValueError):
    pass


def grid_point(point):
    return tuple(int(round(value / 8)) * 8 for value in point)


def terminal_point(placement, terminal):
    x, y, rotation = placement
    dx, dy = {"1": (-60, 0), "2": (60, 0), "3": (0, 50)}[terminal]
    for _ in range(int(rotation) % 360 // 90):
        dx, dy = -dy, dx
    return grid_point((x + dx, y + dy))


def on_segment(point, a, b):
    return (min(a[0], b[0]) <= point[0] <= max(a[0], b[0]) and
            min(a[1], b[1]) <= point[1] <= max(a[1], b[1]) and
            (a[0] == b[0] == point[0] or a[1] == b[1] == point[1]))


def split_wires(segments, posts):
    """Split at all same-net taps and remove duplicate/overlapping segments."""
    result = set()
    for a, b in segments:
        points = sorted({p for p in posts if on_segment(p, a, b)} | {a, b})
        for start, end in zip(points, points[1:]):
            if start != end:
                result.add((start, end))
    return sorted(result)


def record(kind, a, b, flags=0, *parameters):
    return " ".join(map(str, (kind, *a, *b, flags, *parameters)))


def export_falstad(circuit):
    """Return a self-contained CircuitJS dump, without requiring an MNA solve.

    Supports single-source series/parallel circuits made from the types used in
    all bundled examples. Source endpoint order is reversed relative to our terminal IDs:
    CircuitJS's second voltage-source post is positive. LED post 1 is the anode.
    """
    unsupported = sorted({c.type for c in circuit.components} - SUPPORTED_TYPES)
    if unsupported:
        raise FalstadExportError("Falstad export is not supported yet for: " + ", ".join(unsupported))
    if not circuit.components:
        raise FalstadExportError("Load a circuit before exporting.")
    plan = series_parallel_layout(circuit)
    if plan is None:
        raise FalstadExportError("Export currently requires a single DC source and a series/parallel layout.")
    ground = circuit.ground_node
    if ground is None:
        source = next(c for c in circuit.components if c.type == "voltage_source")
        ground = circuit.terminal_nodes()[(source.id, "2")]
    terminals = {(c.id, tid): terminal_point(plan.placements[c.id], tid)
                 for c in circuit.components for tid in terminal_ids(c.type)}
    net_posts, net_segments = {}, {}
    for net in circuit.nets:
        routes = [tuple(grid_point(p) for p in points) for points in plan.routes[net.id]]
        posts = {p for points in routes for p in points}
        posts.update(terminals[(t.component_id, t.terminal)] for t in net.terminals)
        segments = [(a, b) for points in routes for a, b in zip(points, points[1:]) if a != b]
        if any(a[0] != b[0] and a[1] != b[1] for a, b in segments):
            raise FalstadExportError("Export requires orthogonal wires.")
        net_posts[net.id], net_segments[net.id] = posts, split_wires(segments, posts)
    # A photodiode is a diode plus an opposing photocurrent source.
    # Route that parallel source beside the diode, then validate its new taps too.
    photo_sources = {}
    nodes = circuit.terminal_nodes()
    for component in circuit.components:
        if component.type != "photodiode":
            continue
        a, b = terminals[(component.id, "1")], terminals[(component.id, "2")]
        offset = (64, 0) if a[0] == b[0] else (0, 64)
        shifted = [(point[0] + offset[0], point[1] + offset[1]) for point in (a, b)]
        photo_sources[component.id] = shifted
        for tid, point, extra in zip(("1", "2"), (a, b), shifted):
            nid = nodes[(component.id, tid)]
            net_posts[nid].add(extra)
            net_segments[nid] = split_wires(net_segments[nid] + [(point, extra)], net_posts[nid])

    # Never turn distinct electrical nets into one node while snapping to grid.
    for nid, posts in net_posts.items():
        for other, segments in net_segments.items():
            if nid != other and any(on_segment(p, a, b) for p in posts for a, b in segments):
                raise FalstadExportError("Layout contains an ambiguous cross-net junction; export stopped.")

    lines = ["$ 1 0.000005 10.20027730826997 50 5 50"]
    for component in circuit.components:
        a, b = terminals[(component.id, "1")], terminals[(component.id, "2")]
        p = component.parameters
        if component.type == "resistor":
            lines.append(record("r", a, b, 0, p["resistance_ohm"]))
        elif component.type == "voltage_source":
            lines.append(record("v", b, a, 0, 0, 40, p["voltage_v"], 0, 0, 0.5))
        elif component.type == "led":
            # Backward-compatible explicit forward-drop form, with red RGB color.
            lines.append(record(162, a, b, 1, p["forward_voltage_v"], 1, 0, 0, 0.01))
        elif component.type in ("switch", "button"):
            position = 0 if contact_closed(component) else 1
            momentary = "true" if component.type == "button" else "false"
            lines.append(record("s", a, b, 0, position, momentary))
        elif component.type == "wire":
            lines.append(record("w", a, b))
        elif component.type == "capacitor":
            initial = p.get("initial_voltage_v", 0.0)
            lines.append(record("c", a, b, 0, p["capacitance_f"], initial, initial))
        elif component.type == "inductor":
            lines.append(record("l", a, b, 0, p["inductance_h"], p.get("initial_current_a", 0.0)))
        elif component.type in ("diode", "photodiode"):
            lines.append(record("d", a, b, 1, p.get("forward_voltage_v", 0.7)))
            if component.type == "photodiode":
                anode, cathode = photo_sources[component.id]
                lines.append(record("i", cathode, anode, 0, p["photocurrent_a"]))
        elif component.type == "potentiometer":
            midpoint = grid_point(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
            wiper = terminals[(component.id, "3")]
            position = p["wiper_position"]
            for start, end, resistance in (
                (a, midpoint, p["resistance_ohm"] * position),
                (midpoint, b, p["resistance_ohm"] * (1 - position)),
            ):
                lines.append(record("r", start, end, 0, resistance) if resistance > 0
                             else record("w", start, end))
            lines.append(record("w", midpoint, wiper))
    for segments in net_segments.values():
        lines.extend(record("w", a, b) for a, b in segments)
    ground_point = max(net_posts[ground], key=lambda p: (p[1], -p[0]))
    lines.append(record("g", ground_point, (ground_point[0], ground_point[1] + 24)))
    return "\n".join(lines) + "\n"


def falstad_url(circuit):
    return FALSTAD_URL + "?" + urlencode({"cct": export_falstad(circuit), "running": "true"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topology_file", type=Path)
    parser.add_argument("--output", type=Path, help="Save CircuitJS text instead of printing a URL")
    args = parser.parse_args()
    try:
        circuit = parse_topology(args.topology_file.read_bytes())
        if args.output:
            args.output.write_text(export_falstad(circuit), encoding="utf-8")
        else:
            print(falstad_url(circuit))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Export failed: {error}\n")


if __name__ == "__main__":
    main()
