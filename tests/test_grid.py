import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QGraphicsScene
from schematic import render_circuit, ComponentSymbol, NetWire
from topology import parse_topology

class GridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_example_terminals_and_wire_bends_align_to_grid_subdivisions(self):
        for path in (Path(__file__).resolve().parents[1] / "examples").rglob("*.json"):
            with self.subTest(circuit=path.name):
                circuit = parse_topology(path.read_bytes())
                scene = QGraphicsScene()
                symbols = render_circuit(scene, circuit)
                for symbol in symbols.values():
                    for terminal in symbol.terminals:
                        point = symbol.terminal_position(terminal)
                        for value in (point.x(), point.y()):
                            self.assertAlmostEqual(value / 10, round(value / 10))
                for wire in (i for i in scene.items() if isinstance(i, NetWire)):
                    path_data = wire.path()
                    for index in range(path_data.elementCount()):
                        point = path_data.elementAt(index)
                        for value in (point.x, point.y):
                            self.assertAlmostEqual(value / 10, round(value / 10))
