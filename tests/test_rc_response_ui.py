import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from PySide6.QtWidgets import QApplication
from simulation.rc import RCTiming
from rc_response_ui import RCResponseWidget

class RCResponseUITests(unittest.TestCase):
    def test_slider_updates_plots_and_readings(self):
        app=QApplication.instance() or QApplication([])
        widget=RCResponseWidget(RCTiming(10000,.0001),0,3.3)
        widget.resize(220,480);widget.show();app.processEvents()
        self.assertIn('330 µA',widget.reading.text())
        widget.slider.setValue(100)
        self.assertIn('2.086 V',widget.reading.text())
        self.assertTrue(all(p.progress==1 for p in widget.plots))
        widget.slider.setValue(500)
        self.assertIn('At t = 5 s (99.3% charging):<br>V =',widget.reading.text())
        self.assertFalse(widget.grab().isNull())
        widget.close()

    def test_inspector_uses_circuit_initial_and_solved_final_values(self):
        from pathlib import Path
        from topology import parse_topology
        from simulation import solve_dc
        from component_details import ComponentDetailsPanel
        app=QApplication.instance() or QApplication([])
        circuit=parse_topology((Path(__file__).resolve().parents[1]/'examples/07_rc_charging.json').read_text())
        panel=ComponentDetailsPanel()
        panel.overview_circuit=circuit
        capacitor=next(c for c in circuit.components if c.id=='C1')
        panel.set_content(capacitor,solve_dc(circuit).components['C1'])
        response=panel.findChild(RCResponseWidget,'rcResponse')
        self.assertIsNotNone(response)
        self.assertEqual(response.initial,0)
        self.assertAlmostEqual(response.final,3.3)
        self.assertAlmostEqual(response.timing.tau_s,1)
        panel.close()

    def test_no_response_when_calculated_results_suppressed(self):
        from pathlib import Path
        from topology import parse_topology
        from component_details import ComponentDetailsPanel
        app=QApplication.instance() or QApplication([])
        circuit=parse_topology((Path(__file__).resolve().parents[1]/'examples/07_rc_charging.json').read_text())
        panel=ComponentDetailsPanel()
        panel.overview_circuit=circuit
        panel.set_content(next(c for c in circuit.components if c.id=='C1'),None)
        self.assertIsNone(panel.findChild(RCResponseWidget,'rcResponse'))
        panel.close()

    def test_discharge_readout(self):
        app=QApplication.instance() or QApplication([])
        widget=RCResponseWidget(RCTiming(10000,.0001),3.3,0)
        widget.inspect_time(500)
        self.assertIn('99.3% discharging',widget.reading.text())
        widget.close()
