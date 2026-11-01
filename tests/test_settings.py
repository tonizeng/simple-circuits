import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QPushButton
from PySide6.QtGui import QColor
from main import CircuitWindow
from schematic import ComponentSymbol, NetWire, highlight_color


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.window = CircuitWindow()
        self.window.preferences = QSettings(str(Path(self.temp.name) / "settings.ini"), QSettings.Format.IniFormat)
        path = Path(__file__).resolve().parents[1] / "examples/01_led_series.json"
        self.window.load_topology(path.read_bytes())

    def tearDown(self):
        self.window.close()
        self.temp.cleanup()

    def test_apply_updates_hover_glow_nodes_and_current_and_saves(self):
        colors = {"component": "#ff9900", "node": "#009999", "current": "#9900cc"}
        self.window.apply_highlight_colors(colors)
        symbol = next(s for s in self.window.scene.items() if isinstance(s, ComponentSymbol))
        symbol.result_box.highlight(True)
        self.assertEqual(symbol.result_box.pen().color().name(), colors["component"])
        self.assertEqual(symbol.value_label.glow.color().name(), colors["component"])
        self.assertEqual(symbol.value_label.brush().color().name(), "#222222")
        self.assertEqual(highlight_color(symbol, "current").name(), colors["current"])
        wire = next(s for s in self.window.scene.items() if isinstance(s, NetWire))
        wire.highlight(True)
        self.assertEqual(wire.pen().color().name(), colors["node"])
        self.assertEqual(self.window.preferences.value("highlights/current"), colors["current"])

    def test_cancel_does_not_apply_chosen_color(self):
        before = dict(self.window.highlight_colors)
        def cancel(dialog):
            button = next(b for b in dialog.findChildren(QPushButton)
                          if b.accessibleName() == "Components colour")
            button.click()
            return QDialog.DialogCode.Rejected
        with patch("main.QColorDialog.getColor", return_value=QColor("#ff0000")), \
             patch.object(QDialog, "exec", cancel):
            self.window.settings_button.click()
        self.assertEqual(self.window.highlight_colors, before)
        self.assertIsNone(self.window.preferences.value("highlights/component"))
