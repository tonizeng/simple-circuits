import math
import unittest
from pathlib import Path

from layout import series_parallel_layout
from topology import parse_topology


def on_segment(point, a, b):
    x, y = point
    return (min(a[0], b[0]) <= x <= max(a[0], b[0]) and
            min(a[1], b[1]) <= y <= max(a[1], b[1]))


class LayoutTests(unittest.TestCase):
    def test_all_examples_have_connected_orthogonal_routes_to_exact_terminals(self):
        for path in sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.json")):
            with self.subTest(example=path.name):
                circuit = parse_topology(path.read_bytes())
                plan = series_parallel_layout(circuit)
                self.assertIsNotNone(plan)
                self.assertEqual(set(plan.placements), {c.id for c in circuit.components})
                self.assertEqual(set(plan.routes), {n.id for n in circuit.nets})
                for net in circuit.nets:
                    segments = [(a, b) for route in plan.routes[net.id]
                                for a, b in zip(route, route[1:])]
                    for a, b in segments:
                        self.assertTrue(a[0] == b[0] or a[1] == b[1])
                    for terminal in net.terminals:
                        x, y, degrees = plan.placements[terminal.component_id]
                        local = {"1": (-60, 0), "2": (60, 0), "3": (0, 50)}[terminal.terminal]
                        angle = math.radians(degrees)
                        point = (round(x + local[0] * math.cos(angle) - local[1] * math.sin(angle), 6),
                                 round(y + local[0] * math.sin(angle) + local[1] * math.cos(angle), 6))
                        self.assertTrue(any(on_segment(point, a, b) for a, b in segments),
                                        (net.id, terminal, point))
                    # Every drawn segment for a net must join the same connected network.
                    reached, pending = set(), [0]
                    while pending:
                        index = pending.pop()
                        if index in reached:
                            continue
                        reached.add(index)
                        a, b = segments[index]
                        for other, (c, d) in enumerate(segments):
                            if (on_segment(a, c, d) or on_segment(b, c, d) or
                                    on_segment(c, a, b) or on_segment(d, a, b)):
                                pending.append(other)
                    self.assertEqual(len(reached), len(segments), net.id)

    def test_parallel_resistors_share_rails_in_separate_columns(self):
        path = Path(__file__).resolve().parents[1] / "examples/03_parallel_resistors.json"
        plan = series_parallel_layout(parse_topology(path.read_bytes()))
        first, second = (plan.placements[cid] for cid in ("R1", "R2"))
        self.assertEqual(first[1], second[1])
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(first[2], 90)
        self.assertEqual(second[2], 90)
