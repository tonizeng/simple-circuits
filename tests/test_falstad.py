import json
import os
import unittest
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from falstad import export_falstad, falstad_url, FalstadExportError
from main import CircuitWindow
from topology import parse_topology


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def example(number):
    return json.loads(next(EXAMPLES.glob(f"{number:02d}_*.json")).read_text())


class FalstadTests(unittest.TestCase):
    def test_five_exports_preserve_connections_and_source_polarity(self):
        for number in range(1, 6):
            with self.subTest(number=number):
                circuit = parse_topology(example(number))
                text = export_falstad(circuit)
                records = [line.split() for line in text.splitlines()]
                self.assertEqual(records[0][0], "$")
                elements = [row for row in records if row[0] in ("r", "v", "162", "s")]
                self.assertEqual(len(elements), len(circuit.components))
                terminals = {}
                parents = {}

                def find(point):
                    parents.setdefault(point, point)
                    if parents[point] != point:
                        parents[point] = find(parents[point])
                    return parents[point]

                for component, row in zip(circuit.components, elements):
                    a, b = tuple(map(int, row[1:3])), tuple(map(int, row[3:5]))
                    self.assertNotEqual(a, b)
                    if component.type == "voltage_source":
                        self.assertEqual(row[0], "v")
                        self.assertEqual(float(row[8]), component.parameters["voltage_v"])
                        a, b = b, a  # CircuitJS's second source post is positive.
                    if component.type == "led":
                        self.assertEqual(row[0], "162")
                        self.assertEqual(row[5], "1")
                        self.assertEqual(float(row[6]), component.parameters["forward_voltage_v"])
                    if component.type == "resistor":
                        self.assertEqual(float(row[6]), component.parameters["resistance_ohm"])
                    terminals[(component.id, "1")] = a
                    terminals[(component.id, "2")] = b
                wires = [row for row in records if row[0] == "w"]
                for row in wires:
                    a, b = tuple(map(int, row[1:3])), tuple(map(int, row[3:5]))
                    self.assertTrue(a[0] == b[0] or a[1] == b[1])
                    parents[find(a)] = find(b)
                net_roots = []
                for net in circuit.nets:
                    roots = {find(terminals[(t.component_id, t.terminal)]) for t in net.terminals}
                    self.assertEqual(len(roots), 1, net.id)
                    net_roots.append(next(iter(roots)))
                self.assertEqual(len(net_roots), len(set(net_roots)))
                ground_row = next(row for row in records if row[0] == "g")
                ground_post = tuple(map(int, ground_row[1:3]))
                ref = next(net for net in circuit.nets if net.id == circuit.ground_node).terminals[0]
                self.assertEqual(find(ground_post), find(terminals[(ref.component_id, ref.terminal)]))
                query = parse_qs(urlparse(falstad_url(circuit)).query)
                self.assertEqual(query["cct"], [text])

    def test_contact_states_and_momentary_flags(self):
        for number in (4, 5):
            for active in (False, True):
                data = example(number)
                component = data["components"][1]
                if number == 4:
                    component["parameters"]["closed"] = active
                else:
                    component["parameters"].update(normally_closed=False, pressed=active)
                record = next(line.split() for line in export_falstad(parse_topology(data)).splitlines()
                              if line.startswith("s "))
                self.assertEqual(record[6], "0" if active else "1")
                self.assertEqual(record[7], "true" if number == 5 else "false")

    def test_unsupported_types_are_not_silently_dropped(self):
        for number in range(6, 13):
            with self.subTest(number=number), self.assertRaises(FalstadExportError):
                export_falstad(parse_topology(example(number)))

    def test_button_opens_encoded_current_circuit_without_actual_browser(self):
        app = QApplication.instance() or QApplication([])
        window = CircuitWindow()
        with patch("main.QDesktopServices.openUrl", return_value=True) as opened:
            window.export_button.click()
            opened.assert_not_called()
            window.load_topology(example(2))
            window.export_button.click()
            opened.assert_called_once()
            query = parse_qs(urlparse(opened.call_args.args[0].toString()).query)
            self.assertEqual(query["cct"][0], export_falstad(window.circuit))
        with patch("main.QDesktopServices.openUrl") as opened:
            window.load_topology(example(7))
            window.export_button.click()
            opened.assert_not_called()
            self.assertIn("not supported", window.statusBar().currentMessage())
        window.close()
