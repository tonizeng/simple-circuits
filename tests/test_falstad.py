import json
import os
import unittest
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch
from dataclasses import replace

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

    def test_all_examples_export_and_links_contain_complete_text(self):
        for path in sorted(EXAMPLES.glob("*.json")):
            with self.subTest(path=path.name):
                circuit = parse_topology(path.read_bytes())
                text = export_falstad(circuit)
                self.assertEqual(parse_qs(urlparse(falstad_url(circuit)).query)["cct"], [text])
                rows = [line.split() for line in text.splitlines()]
                self.assertEqual(sum(row[0] == "g" for row in rows), 1)
                for row in rows[1:]:
                    self.assertNotEqual(row[1:3], row[3:5])
                    self.assertTrue(all(int(v) % 8 == 0 for v in row[1:5]))

    def test_extended_parameters_and_initial_conditions(self):
        cases = ((6, "diode", "d", "forward_voltage_v"),
                 (7, "capacitor", "c", "capacitance_f"),
                 (8, "inductor", "l", "inductance_h"))
        for number, kind, tag, parameter in cases:
            data = example(number)
            device = next(c for c in data["components"] if c["type"] == kind)
            if kind == "capacitor":
                device["parameters"]["initial_voltage_v"] = 1.25
            if kind == "inductor":
                device["parameters"]["initial_current_a"] = -0.02
            row = next(line.split() for line in export_falstad(parse_topology(data)).splitlines()
                       if line.startswith(tag + " "))
            self.assertEqual(float(row[6]), device["parameters"][parameter])
            if kind == "capacitor":
                self.assertEqual(list(map(float, row[7:])), [1.25, 1.25])
            if kind == "inductor":
                self.assertEqual(float(row[7]), -0.02)

    def test_potentiometer_wiper_and_exact_endpoints(self):
        for position in (0, 0.25, 0.5, 1):
            data = example(9)
            data["components"][1]["parameters"]["wiper_position"] = position
            rows = [line.split() for line in export_falstad(parse_topology(data)).splitlines()]
            # First source, then the two track sections and the wiper connection.
            first, second, wiper = rows[2:5]
            self.assertEqual(first[3:5], second[1:3])
            self.assertEqual(wiper[0], "w")
            self.assertEqual(wiper[1:3], first[3:5])
            for row, fraction in ((first, position), (second, 1-position)):
                if fraction == 0:
                    self.assertEqual(row[0], "w")
                else:
                    self.assertEqual(row[0], "r")
                    self.assertEqual(float(row[6]), 10000 * fraction)

    def test_photodiode_current_polarity_and_parallel_connections(self):
        for photocurrent in (0, 1e-5):
            data = example(10)
            data["components"][2]["parameters"]["photocurrent_a"] = photocurrent
            rows = [line.split() for line in export_falstad(parse_topology(data)).splitlines()]
            diode = next(row for row in rows if row[0] == "d")
            source = next(row for row in rows if row[0] == "i")
            self.assertEqual(float(source[6]), photocurrent)
            self.assertEqual(float(diode[6]), 0.7)
            parents = {}
            def find(point):
                parents.setdefault(point, point)
                if parents[point] != point:
                    parents[point] = find(parents[point])
                return parents[point]
            for row in rows:
                if row[0] == "w":
                    parents[find(tuple(row[1:3]))] = find(tuple(row[3:5]))
            self.assertEqual(find(tuple(source[1:3])), find(tuple(diode[3:5])))
            self.assertEqual(find(tuple(source[3:5])), find(tuple(diode[1:3])))
            self.assertNotEqual(find(tuple(source[1:3])), find(tuple(source[3:5])))

    def test_unknown_types_are_not_silently_dropped(self):
        circuit = parse_topology(example(1))
        unknown = replace(circuit.components[1], type="unknown")
        circuit = replace(circuit, components=(circuit.components[0], unknown, circuit.components[2]))
        with self.assertRaisesRegex(FalstadExportError, "unknown"):
            export_falstad(circuit)

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
            opened.assert_called_once()
            query = parse_qs(urlparse(opened.call_args.args[0].toString()).query)
            self.assertEqual(query["cct"][0], export_falstad(window.circuit))
        window.close()
