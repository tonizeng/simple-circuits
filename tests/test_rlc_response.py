import json
import math
import os
import unittest
from pathlib import Path
import numpy as np
from scipy.linalg import expm
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from topology import parse_topology
from simulation import solve_dc
from simulation.rlc import series_rlc
ROOT=Path(__file__).resolve().parents[1]

class SeriesRLCTests(unittest.TestCase):
    def data(self,resistance=10):
        data=json.loads((ROOT/'examples/13_rlc_series.json').read_text())
        data['components'][1]['parameters']['resistance_ohm']=resistance
        return data

    def model(self,data):
        circuit=parse_topology(data)
        model,reason=series_rlc(circuit)
        self.assertIsNone(reason)
        return circuit,model

    def test_all_damping_regimes_match_matrix_exponential(self):
        for resistance,regime in ((10,'Underdamped'),(20,'Critically damped'),(100,'Overdamped')):
            with self.subTest(regime=regime):
                data=self.data(resistance)
                data['components'][2]['parameters']['initial_current_a']=.012
                data['components'][3]['parameters']['initial_voltage_v']=.8
                circuit,model=self.model(data)
                self.assertEqual(model.regime,regime)
                matrix=np.array([[0,1/.0001],[-1/.01,-resistance/.01]])
                initial=np.array([.8-3.3,.012])
                for fraction in (0,.01,.1,.3,1):
                    time=fraction*model.duration_s
                    expected=expm(matrix*time)@initial
                    vc,current,vl=model.state(time)
                    self.assertAlmostEqual(vc,expected[0]+3.3,places=10)
                    self.assertAlmostEqual(current,expected[1],places=10)
                    self.assertAlmostEqual(vc+resistance*current+vl,3.3)
                vc,current,_=model.state(model.duration_s*10)
                self.assertAlmostEqual(vc,3.3,places=7)
                self.assertAlmostEqual(current,0,places=7)

    def test_snapshot_signs_ground_and_kcl(self):
        data=self.data()
        # Reverse both storage terminal references, retain the physical loop.
        for net in data['nets']:
            for ref in net['terminals']:
                if ref['component_id'] in ('C1','L1'):
                    ref['terminal']='2' if ref['terminal']=='1' else '1'
        data['ground_node']='n2'
        circuit,model=self.model(data)
        final=solve_dc(circuit)
        snapshot=model.snapshot(.001,final)
        vc,current,vl=model.state(.001)
        self.assertAlmostEqual(snapshot.components['C1'].voltage_v,-vc)
        self.assertAlmostEqual(snapshot.components['L1'].voltage_v,-vl)
        self.assertAlmostEqual(snapshot.components['C1'].current_a,-current)
        self.assertAlmostEqual(snapshot.node_voltages['n2'],0)
        for component in circuit.components:
            nodes=circuit.terminal_nodes()
            result=snapshot.components[component.id]
            self.assertAlmostEqual(result.voltage_v,snapshot.node_voltages[nodes[component.id,'1']]-snapshot.node_voltages[nodes[component.id,'2']])
        for net in circuit.nets:
            self.assertAlmostEqual(sum(snapshot.components[t.component_id].current_a*(1 if t.terminal=='1' else -1) for t in net.terminals),0)

    def test_overshoot_and_reversal(self):
        _,model=self.model(self.data())
        samples=[model.state(model.duration_s*i/100) for i in range(101)]
        self.assertGreater(max(v for v,_,_ in samples),3.3)
        self.assertLess(min(i for _,i,_ in samples),0)

    def test_nonseries_and_open_circuits_are_rejected(self):
        data=self.data()
        data['components'].append({'id':'R2','type':'resistor','parameters':{'resistance_ohm':100}})
        for net in data['nets']:
            if net['id'] in ('n1','n2'):
                net['terminals'].append({'component_id':'R2','terminal':'1' if net['id']=='n1' else '2'})
        self.assertIsNone(series_rlc(parse_topology(data))[0])
        data=self.data();data['components'][1]={'id':'R1','type':'switch','parameters':{'closed':False}}
        self.assertIsNone(series_rlc(parse_topology(data))[0])
        _,model=self.model(self.data())
        for t in (-1,float('nan')):
            with self.assertRaises(ValueError):model.state(t)

class RLCPreviewUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_slider_and_both_storage_inspectors(self):
        from main import CircuitWindow
        from rc_response_ui import RCResponseWidget
        w=CircuitWindow();w.load_topology((ROOT/'examples/13_rlc_series.json').read_text())
        final=w.simulation_result;report=w.safety_report
        self.assertFalse(w.canvas.rc_controls.isHidden())
        w.canvas.rc_slider.setValue(100)
        self.assertIn('Underdamped',w.canvas.rc_time_label.text())
        self.assertNotIn('charging',w.canvas.rc_time_label.text())
        self.assertGreater(w.rc_preview_result.components['C1'].voltage_v,3.3)
        self.assertIs(w.simulation_result,final);self.assertIs(w.safety_report,report)
        for cid in ('C1','L1'):
            w.select_component_details(cid)
            widget=w.component_details.findChild(RCResponseWidget,'rlcResponse')
            self.assertIsNotNone(widget)
            self.assertTrue(widget.slider.isHidden())
            self.assertEqual(widget.plots[0].progress,1)
            self.assertNotIn('charging',widget.reading.text())
            self.assertNotIn('τ',widget.reading.text())
            self.assertTrue(all(p.timing.kind=='RLC' for p in widget.plots))
        w.restore_settled_dc();self.assertIsNone(w.rc_preview_result)
        w.load_topology((ROOT/'examples/01_led_series.json').read_text())
        self.assertTrue(w.canvas.rc_controls.isHidden())
        w.close()
