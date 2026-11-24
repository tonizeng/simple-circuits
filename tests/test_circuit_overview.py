import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from main import CircuitWindow
from database import CircuitDatabase

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

class OverviewTests(unittest.TestCase):
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

    def test_overview_badges_lists_and_component_selection(self):
        panel = self.window.component_details
        headings = {button.text(): button for button in panel.scroll.widget().findChildren(QPushButton)}
        self.assertIn("Components (3)", headings)
        self.assertIn("Nodes (3)", headings)
        headings["Components (3)"].click()
        self.assertTrue(self.window.component_legend.isHidden())
        headings["Components (3)"].click()
        self.app.processEvents()
        self.assertTrue(self.window.component_legend.isVisible())
        self.window.component_legend.cellWidget(2, 0).click()
        self.assertEqual(panel.component_id, "R1")
        self.window.clear_component_selection()
        self.app.processEvents()
        self.assertEqual(panel.title.text(), "Circuit Overview")
        self.assertTrue(self.window.component_legend.isVisible())

    def test_node_selection_and_status_card_replaces_floating_overlay(self):
        panel = self.window.component_details
        button = next(b for b in panel.scroll.widget().findChildren(QPushButton) if b.accessibleName() == "Inspect node n1")
        button.click()
        self.assertEqual(panel.node_id, "n1")
        self.window.load_topology((EXAMPLES / "errors/02_short_disconnected_led.json").read_bytes())
        self.assertTrue(self.window.safety_panel.embedded)
        self.assertIs(self.window.safety_panel.parentWidget(), self.window.circuit_status_card)
        self.assertIn("warning", self.window.status_summary.text())
        self.assertFalse(self.window.canvas.viewport().findChildren(type(self.window.safety_panel)))
