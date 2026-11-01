import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from main import CircuitWindow
from schematic import ComponentSymbol


class ContactReadonlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_clicks_do_not_change_contacts_but_updated_topology_does(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        for number, cid, field in ((4, "S1", "closed"), (5, "SW1", "pressed")):
            with self.subTest(number=number):
                data = json.loads(next(examples.glob(f"{number:02d}_*.json")).read_text())
                window = CircuitWindow()
                window.show()
                window.load_topology(data)
                self.app.processEvents()
                original = window.simulation_result.components["R1"].current_a
                symbol = next(item for item in window.scene.items()
                              if isinstance(item, ComponentSymbol) and item.component.id == cid)
                point = window.canvas.mapFromScene(symbol.scenePos())
                QTest.mouseClick(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
                self.app.processEvents()
                self.assertEqual(window.simulation_result.components["R1"].current_a, original)
                data["components"][1]["parameters"][field] = not data["components"][1]["parameters"][field]
                window.load_topology(data)
                self.assertNotEqual(window.simulation_result.components["R1"].current_a, original)
                window.close()
