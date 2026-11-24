import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QLabel
from main import CircuitWindow

class GuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_guide_is_non_modal_reused_and_preserves_current_circuit(self):
        window = CircuitWindow()
        window.show()
        window.load_topology((Path(__file__).resolve().parents[1] / "examples/01_led_series.json").read_bytes())
        original = window.circuit
        window.select_component_details("R1")
        window.guide_button.click()
        guide = window.guide_dialog
        self.assertFalse(guide.isModal())
        self.assertEqual(guide.tabs.tabText(0), "Getting Started")
        self.assertEqual(guide.tabs.tabText(1), "Understanding the circuit")
        self.assertEqual(guide.tabs.tabText(2), "Navigation")
        self.assertEqual(guide.tabs.tabText(3), "Terminology")
        text = "\n".join(label.text() for label in guide.findChildren(QLabel))
        for phrase in ("Voltage and polarity", "Current direction", "Ground reference", "Unavailable values", "Nominal", "Calculated", "Measured", "Open circuit", "Short circuit"):
            self.assertIn(phrase, text)
        window.guide_button.click()
        self.assertIs(window.guide_dialog, guide)
        window.change_workspace_page(1)
        self.assertTrue(window.guide_button.isEnabled())
        self.assertEqual(window.circuit, original)
        guide.close()
        self.assertIsNone(window.guide_dialog)
        window.close()
        window.deleteLater()
        self.app.processEvents()
