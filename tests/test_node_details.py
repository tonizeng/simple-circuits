import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from database import CircuitDatabase
from main import CircuitWindow
from schematic import NetWire

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

class NodeDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.window = CircuitWindow(database=CircuitDatabase(Path(self.folder.name) / "test.sqlite3"))
        self.window.show()
        self.window.load_topology((EXAMPLES / "01_led_series.json").read_bytes())
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.folder.cleanup()

    def text(self):
        return "\n".join(label.text() for label in self.window.component_details.scroll.widget().findChildren(QLabel))

    def test_node_label_click_shows_terminal_membership_and_toggles_off(self):
        wire = next(i for i in self.window.scene.items() if isinstance(i, NetWire) and i.net_id == "n1")
        position = self.window.canvas.mapFromScene(wire.label.sceneBoundingRect().center())
        QTest.mouseClick(self.window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
        self.assertEqual(self.window.component_details.node_id, "n1")
        self.assertTrue(wire.pinned)
        self.assertIn("V1", self.text())
        self.assertIn("Terminal 1", self.text())
        self.assertIn("R1", self.text())
        self.assertIn("3.3 V", self.text())
        QTest.mouseClick(self.window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
        self.assertIsNone(self.window.component_details.node_id)
        self.assertFalse(wire.pinned)

    def test_ground_explanation_and_return_to_component_details(self):
        self.window.select_node_details("n0")
        self.assertIn("0 V reference", self.text())
        self.assertIn("0 V", self.text())
        self.window.select_component_details("R1")
        self.assertIsNone(self.window.component_details.node_id)
        self.assertEqual(self.window.component_details.component_id, "R1")

    def test_only_inspected_node_stays_highlighted(self):
        self.window.select_node_details("n1")
        self.window.select_node_details("n2")
        wires = [i for i in self.window.scene.items() if isinstance(i, NetWire)]
        self.assertEqual([wire.net_id for wire in wires if wire.pinned], ["n2"])
        self.window.select_component_details("R1")
        self.assertFalse(any(wire.pinned for wire in wires))
        self.window.select_node_details("n1")
        self.window.clear_component_selection()
        self.assertFalse(any(wire.pinned for wire in wires))

    def test_faults_hide_node_voltage_but_keep_connection_information(self):
        self.window.load_topology((EXAMPLES / "incomplete/03_parallel_resistors_incomplete.json").read_bytes())
        self.window.select_node_details("n_open")
        self.assertIn("—", self.text())
        self.assertIn("R2", self.text())
        self.assertIn("Terminal 2", self.text())
        self.assertIn("Only one terminal", self.text())
