"""Run headlessly with QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests."""

import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene

from components import COMPONENT_NAMES, contact_closed, engineering
from main import CircuitWindow
from schematic import ComponentSymbol, NetWire, ResultBox, render_circuit
from topology import TopologyError, parse_topology


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class RenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_every_example_parses_renders_and_populates_legend(self):
        window = CircuitWindow()
        kinds = set()
        for path in sorted(EXAMPLES.glob("*.json")):
            with self.subTest(path=path.name):
                data = path.read_bytes()
                circuit = parse_topology(data)
                kinds.update(c.type for c in circuit.components)
                self.assertTrue(window.load_topology(data))
                scene = window.scene
                symbols = {item.component.id: item for item in scene.items()
                           if isinstance(item, ComponentSymbol)}
                self.assertEqual(len(symbols), len(circuit.components))
                self.assertEqual(sum(isinstance(i, NetWire) for i in scene.items()), len(circuit.nets))
                self.assertEqual(sum(isinstance(i, ResultBox) for i in scene.items()), len(circuit.components))
                for terminal in circuit.terminal_nodes():
                    self.assertIn(terminal[1], symbols[terminal[0]].terminals)
                self.assertEqual(window.component_legend.rowCount(), 2 * len({c.type for c in circuit.components}))
                image = QImage(1200, 600, QImage.Format.Format_ARGB32)
                image.fill(0xffffffff)
                painter = QPainter(image)
                try:
                    scene.render(painter)
                finally:
                    painter.end()
                for symbol in symbols.values():
                    output = symbol.result_box.childItems()[0]
                    result = window.simulation_result.components.get(symbol.component.id)
                    voltage = engineering(result.voltage_v, "V") if result is not None and result.voltage_v is not None else "—"
                    current = engineering(abs(result.current_a), "A") if result is not None and result.current_a is not None else "—"
                    self.assertEqual(output.text(), f"V: {voltage}\nI: {current}")
                    symbol.result_box.highlight(True)
                    self.assertTrue(symbol.highlighted)
                    symbol.result_box.highlight(False)
        self.assertEqual(kinds, set(COMPONENT_NAMES))
        window.close()

    def test_current_arrows_follow_signed_results_and_rotate_with_symbols(self):
        window = CircuitWindow()
        window.load_topology((EXAMPLES / "01_led_series.json").read_bytes())
        symbols = {item.component.id: item for item in window.scene.items()
                   if isinstance(item, ComponentSymbol)}
        source = symbols["V1"]
        start, end = source.current_arrow_points()
        self.assertGreater(source.mapToScene(start).y(), source.mapToScene(end).y())
        resistor = symbols["R1"]
        start, end = resistor.current_arrow_points()
        self.assertLess(resistor.mapToScene(start).x(), resistor.mapToScene(end).x())
        for current in (None, 0, 1e-13):
            source.current_a = current
            self.assertIsNone(source.current_arrow_points())
        window.close()

    def test_potentiometer_wiper_required_and_not_valid_on_resistor(self):
        data = json.loads((EXAMPLES / "09_potentiometer_divider.json").read_text())
        circuit = parse_topology(data)
        self.assertEqual(circuit.terminal_nodes()[("P1", "3")], "n2")
        del data["nets"][-1]
        with self.assertRaisesRegex(TopologyError, "P1.3"):
            parse_topology(data)
        data = json.loads((EXAMPLES / "02_voltage_divider.json").read_text())
        data["nets"][0]["terminals"][1]["terminal"] = "3"
        with self.assertRaisesRegex(TopologyError, "unknown terminal"):
            parse_topology(data)

    def test_new_parameter_ranges_and_contact_states(self):
        invalid = [("07_rc_charging.json", "C1", "capacitance_f", -1),
                   ("08_rl_step.json", "L1", "initial_current_a", float("inf")),
                   ("09_potentiometer_divider.json", "P1", "wiper_position", 1.5),
                   ("04_switch_led.json", "S1", "closed", "false"),
                   ("05_button_led.json", "SW1", "pressed", 1),
                   ("10_photodiode_sensor.json", "PD1", "photocurrent_a", -1)]
        for filename, cid, field, value in invalid:
            with self.subTest(filename=filename, field=field):
                data = json.loads((EXAMPLES / filename).read_text())
                next(c for c in data["components"] if c["id"] == cid)["parameters"][field] = value
                with self.assertRaises(TopologyError):
                    parse_topology(data)
        from topology import Component
        for normal in (False, True):
            for pressed in (False, True):
                component = Component("SW1", "button", {"normally_closed": normal, "pressed": pressed})
                self.assertEqual(contact_closed(component), normal != pressed)
