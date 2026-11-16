import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QLabel, QComboBox, QDialog
from main import CircuitWindow
from schematic import ComponentSymbol

ROOT = Path(__file__).resolve().parents[1]

class CurrentModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.window = CircuitWindow()
        self.window.preferences = QSettings(str(Path(self.folder.name) / 'settings.ini'), QSettings.Format.IniFormat)
        self.window.apply_current_display('arrows')
        self.window.load_topology((ROOT / 'examples/01_led_series.json').read_bytes())

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.folder.cleanup()

    def symbol(self, cid):
        return next(i for i in self.window.scene.items() if isinstance(i, ComponentSymbol) and i.component.id == cid)

    def test_signed_mode_removes_arrows_and_preserves_solver_and_voltage_signs(self):
        original = self.window.simulation_result
        self.window.apply_current_display('signed')
        source = self.symbol('V1')
        self.assertFalse(self.window.canvas.current_reference.isHidden())
        self.assertIs(self.window.simulation_result, original)
        self.assertIn('Current: -3.939 mA', source.result_box.childItems()[0].text())
        self.assertIn('Current: +3.939 mA', self.symbol('R1').result_box.childItems()[0].text())
        self.assertTrue(all(self.symbol(c.id).current_arrow_points() is None for c in self.window.circuit.components))
        self.window.select_component_details('V1')
        labels = [l.text() for l in self.window.component_details.scroll.widget().findChildren(QLabel)]
        self.assertIn('-3.939 mA', labels)
        self.assertNotIn('Voltage: V(1) − V(2) · Positive current: 1 → 2', labels)
        self.assertEqual(self.window.preferences.value('display/current'), 'signed')
        self.window.apply_current_display('arrows')
        self.assertIsNotNone(self.symbol('V1').current_arrow_points())
        self.assertFalse(self.window.canvas.current_reference.isHidden())
        self.assertIn("conventional direction", self.window.canvas.current_reference.text())
        self.assertIn('Current: 3.939 mA', self.symbol('V1').result_box.childItems()[0].text())

    def test_fault_results_stay_unavailable_in_signed_mode(self):
        self.window.apply_current_display('signed')
        self.window.load_topology((ROOT / 'examples/incomplete/04_switch_led_incomplete.json').read_bytes())
        for component in self.window.circuit.components:
            symbol = self.symbol(component.id)
            self.assertIn('Current: —', symbol.result_box.childItems()[0].text())
            self.assertIsNone(symbol.current_arrow_points())

    def test_cancel_does_not_change_current_mode(self):
        def cancel(dialog):
            combo = dialog.findChild(QComboBox)
            combo.setCurrentIndex(combo.findData('signed'))
            return QDialog.DialogCode.Rejected
        with patch.object(QDialog, 'exec', cancel):
            self.window.show_settings()
        self.assertEqual(self.window.current_display, 'arrows')
        self.assertEqual(self.window.preferences.value('display/current'), 'arrows')
