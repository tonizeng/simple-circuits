import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from main import CircuitWindow
from rc_response_ui import RCResponseWidget

ROOT=Path(__file__).resolve().parents[1]

class MainRCPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=CircuitWindow()
        self.window.load_topology((ROOT/'examples/07_rc_charging.json').read_text())

    def tearDown(self):
        self.window.close()

    def test_preview_updates_circuit_values_without_changing_safety(self):
        w=self.window
        report=w.safety_report
        w.canvas.rc_slider.setValue(100)
        self.assertAlmostEqual(w.rc_preview_result.components['C1'].voltage_v,2.085997844)
        self.assertAlmostEqual(w.rc_preview_result.components['R1'].voltage_v,1.214002156)
        self.assertAlmostEqual(w.rc_preview_result.components['C1'].current_a,.0001214002156)
        self.assertEqual(w.simulation_result.components['C1'].current_a,0)
        self.assertIs(w.safety_report,report)
        w.select_component_details('C1')
        graph=w.component_details.findChild(RCResponseWidget,'rcResponse')
        self.assertTrue(graph.slider.isHidden())
        self.assertEqual(graph.plots[0].progress,1)
        self.assertAlmostEqual(graph.final,3.3)
        w.restore_settled_dc()
        self.assertIsNone(w.rc_preview_result)

    def test_switch_circuit_resets_and_hides_control(self):
        w=self.window
        w.canvas.rc_slider.setValue(200)
        w.load_topology((ROOT/'examples/01_led_series.json').read_text())
        self.assertTrue(w.canvas.rc_controls.isHidden())
        self.assertIsNone(w.rc_preview_result)

    def test_invalid_circuit_cannot_show_transient_values(self):
        import json
        w=self.window
        data=json.loads((ROOT/'examples/07_rc_charging.json').read_text())
        data['components'][0]['parameters']['voltage_v']=5
        w.load_topology(data)
        self.assertTrue(w.current_safety_issues)
        self.assertTrue(w.canvas.rc_controls.isHidden())
        w.preview_rc_time(100)
        self.assertIsNone(w.rc_preview_result)
