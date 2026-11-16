import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from pathlib import Path
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from main import CircuitWindow

class PanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = CircuitWindow()
        self.window.show()
        self.window.load_topology((Path(__file__).resolve().parents[1] / "examples/01_led_series.json").read_bytes())
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def drag(self, button):
        view = self.window.canvas
        position = view.viewport().rect().center()
        old_center = view.mapToScene(position)
        scale = view.transform().m11()
        QTest.mousePress(view.viewport(), button, pos=position)
        QTest.mouseMove(view.viewport(), position + QPoint(70, 40))
        QTest.mouseRelease(view.viewport(), button, pos=position + QPoint(70, 40))
        self.app.processEvents()
        self.assertNotEqual(view.mapToScene(view.viewport().rect().center()), old_center)
        self.assertAlmostEqual(view.transform().m11(), scale)
        self.assertIsNone(view.pan_position)
        self.assertIsNone(self.window.component_details.component_id)

    def test_pan_tool_moves_fitted_circuit_without_selecting_components(self):
        self.window.canvas.pan_button.click()
        self.drag(Qt.MouseButton.LeftButton)
        self.window.canvas.pan_button.click()
        self.assertFalse(self.window.canvas.pan_button.isChecked())

    def test_middle_button_pan_remains_available_without_tool(self):
        self.assertFalse(self.window.canvas.pan_button.isChecked())
        self.drag(Qt.MouseButton.MiddleButton)
