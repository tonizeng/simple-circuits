import json
import math
import os
import unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from topology import parse_topology
from simulation import solve_dc
from simulation.rl import rl_timing,rl_step_endpoints
from simulation.rc import rc_step_snapshot
ROOT=Path(__file__).resolve().parents[1]

class RLTimingTests(unittest.TestCase):
    def data(self):
        return json.loads((ROOT/'examples/08_rl_step.json').read_text())

    def model(self,data=None):
        circuit=parse_topology(self.data() if data is None else data)
        timing,reason=rl_timing(circuit,'L1')
        self.assertIsNone(reason)
        final=solve_dc(circuit)
        endpoints=rl_step_endpoints(circuit,'L1',timing,final)
        self.assertIsNotNone(endpoints)
        return timing,final,endpoints

    def test_time_constant_and_rising_current(self):
        timing,final,endpoints=self.model()
        self.assertAlmostEqual(timing.tau_s,.0001)
        self.assertEqual(timing.response(0,0,.033),(3.3000000000000003,0))
        v,i=timing.response(timing.tau_s,0,.033)
        self.assertAlmostEqual(v,3.3/math.e)
        self.assertAlmostEqual(i,.033*(1-1/math.e))
        snap=rc_step_snapshot(timing,endpoints,timing.tau_s)
        self.assertAlmostEqual(snap.components['L1'].voltage_v,v)
        self.assertAlmostEqual(snap.components['L1'].current_a,i)
        self.assertAlmostEqual(snap.components['R1'].voltage_v+v,3.3)
        self.assertEqual(final.components['L1'].voltage_v,0)

    def test_nonzero_initial_current_and_decay(self):
        data=self.data();data['components'][2]['parameters']['initial_current_a']=.01
        timing,_,endpoints=self.model(data)
        initial=rc_step_snapshot(timing,endpoints,0).components['L1']
        self.assertAlmostEqual(initial.current_a,.01)
        self.assertAlmostEqual(initial.voltage_v,2.3)
        data['components'][0]['parameters']['voltage_v']=0
        timing,_,endpoints=self.model(data)
        result=rc_step_snapshot(timing,endpoints,timing.tau_s).components['L1']
        self.assertAlmostEqual(result.current_a,.01/math.e)
        self.assertAlmostEqual(result.voltage_v,-1/math.e)

    def test_parallel_resistors_and_reversed_source(self):
        data=self.data();data['components'][0]['parameters']['voltage_v']=-3.3
        data['components'].append({'id':'R2','type':'resistor','parameters':{'resistance_ohm':100}})
        for net in data['nets']:
            if net['id'] in ('n1','n2'):
                net['terminals'].append({'component_id':'R2','terminal':'1' if net['id']=='n1' else '2'})
        timing,final,endpoints=self.model(data)
        self.assertAlmostEqual(timing.resistance_ohm,50)
        self.assertAlmostEqual(timing.tau_s,.0002)
        result=rc_step_snapshot(timing,endpoints,timing.tau_s).components['L1']
        self.assertLess(result.current_a,0)
        self.assertAlmostEqual(result.current_a,final.components['L1'].current_a*(1-1/math.e))

    def test_unsupported_rlc_and_no_resistive_path(self):
        circuit=parse_topology((ROOT/'examples/13_rlc_series.json').read_text())
        self.assertIsNone(rl_timing(circuit,'L1')[0])
        data=self.data();data['components'][1]={'id':'R1','type':'switch','parameters':{'closed':False}}
        self.assertIsNone(rl_timing(parse_topology(data),'L1')[0])
        timing,_,_=self.model()
        for t in (-1,float('nan')):
            with self.assertRaises(ValueError):timing.response(t,0,.033)

class RLPreviewUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_main_slider_inspector_and_dc_restore(self):
        from main import CircuitWindow
        from rc_response_ui import RCResponseWidget
        w=CircuitWindow();w.load_topology((ROOT/'examples/08_rl_step.json').read_text())
        report=w.safety_report
        self.assertFalse(w.canvas.rc_controls.isHidden())
        self.assertIn('RL response',w.canvas.rc_time_label.text())
        w.canvas.rc_slider.setValue(100)
        self.assertAlmostEqual(w.rc_preview_result.components['L1'].current_a,.033*(1-1/math.e))
        self.assertIs(w.safety_report,report)
        self.assertEqual(w.simulation_result.components['L1'].voltage_v,0)
        w.select_component_details('L1')
        response=w.component_details.findChild(RCResponseWidget,'rlResponse')
        self.assertIsNotNone(response)
        self.assertTrue(response.slider.isHidden())
        self.assertEqual(response.plots[1].progress,1)
        self.assertAlmostEqual(response.final,.033)
        self.assertIn('current rise',response.reading.text())
        w.restore_settled_dc();self.assertIsNone(w.rc_preview_result)
        w.load_topology((ROOT/'examples/13_rlc_series.json').read_text())
        self.assertFalse(w.canvas.rc_controls.isHidden())
        self.assertEqual(w.preview_kind, 'RLC')
        w.close()
