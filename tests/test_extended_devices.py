import copy
import json
import unittest
from pathlib import Path
from topology import parse_topology
from simulation import solve_dc

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'

def example(number):
    return json.loads(next(EXAMPLES.glob(f'{number:02d}_*.json')).read_text())

def solve(data):
    return solve_dc(parse_topology(data))

class ExtendedDeviceTests(unittest.TestCase):
    def test_diode_forward_and_reverse(self):
        data = example(6)
        result = solve(data)
        self.assertAlmostEqual(result.components['D1'].voltage_v, .7)
        self.assertAlmostEqual(result.components['D1'].current_a, .0043)
        for net in data['nets']:
            for terminal in net['terminals']:
                if terminal['component_id'] == 'D1':
                    terminal['terminal'] = '2' if terminal['terminal'] == '1' else '1'
        result = solve(data)
        self.assertEqual(result.components['D1'].current_a, 0)
        self.assertAlmostEqual(result.components['D1'].voltage_v, -5)

    def test_capacitor_and_inductor_dc_equilibrium_ignore_initial_conditions(self):
        data = example(7)
        data['components'][2]['parameters']['initial_voltage_v'] = 1
        result = solve(data)
        self.assertEqual(result.components['C1'].current_a, 0)
        self.assertAlmostEqual(result.components['C1'].voltage_v, 5)
        self.assertIn('equilibrium', result.message)
        data = example(8)
        data['components'][2]['parameters']['initial_current_a'] = .01
        result = solve(data)
        self.assertAlmostEqual(result.components['L1'].voltage_v, 0)
        self.assertAlmostEqual(result.components['L1'].current_a, .05)

    def test_potentiometer_positions_and_loaded_wiper(self):
        for position in (0, .25, .5, 1):
            data = example(9)
            data['components'][1]['parameters']['wiper_position'] = position
            result = solve(data)
            self.assertEqual(result.status, 'solved', result.message)
            self.assertAlmostEqual(result.node_voltages['n2'], 5 * (1-position))
            currents = result.components['P1'].terminal_currents_a
            self.assertAlmostEqual(currents['1'], .0005)
            self.assertAlmostEqual(currents['3'], 0)
            self.assertAlmostEqual(sum(currents.values()), 0)
        data = example(9)
        data['components'].append({'id':'Rload','type':'resistor','parameters':{'resistance_ohm':5000}})
        data['nets'][2]['terminals'].append({'component_id':'Rload','terminal':'1'})
        data['nets'][1]['terminals'].append({'component_id':'Rload','terminal':'2'})
        result = solve(data)
        self.assertAlmostEqual(result.node_voltages['n2'], 5/3)
        self.assertAlmostEqual(result.components['P1'].terminal_currents_a['3'], -(5/3)/5000)

    def test_photocurrent_polarity_light_and_dark(self):
        for photocurrent in (0, 1e-5, 2e-5):
            data = example(10)
            data['components'][2]['parameters']['photocurrent_a'] = photocurrent
            result = solve(data)
            self.assertAlmostEqual(result.components['PD1'].current_a, -photocurrent)
            self.assertAlmostEqual(result.components['R1'].voltage_v, photocurrent * 10000)
        # Forward-biased sensor uses its default 0.7 V diode as well as the light source.
        data = example(6)
        data['components'][2] = {'id':'D1','type':'photodiode','parameters':{'photocurrent_a':1e-5}}
        result = solve(data)
        self.assertAlmostEqual(result.components['D1'].voltage_v, .7)
        self.assertAlmostEqual(result.components['D1'].current_a, .0043)

    def test_wire_voltage_and_redundant_wire_loop(self):
        data = example(12)
        result = solve(data)
        self.assertEqual(result.components['W1'].voltage_v, 0)
        self.assertAlmostEqual(result.components['W1'].current_a, 3/330)
        data['components'].append({'id':'W2','type':'wire','parameters':{}})
        for net in data['nets']:
            for t in list(net['terminals']):
                if t['component_id'] == 'W1':
                    net['terminals'].append({'component_id':'W2','terminal':t['terminal']})
        result = solve(data)
        self.assertEqual(result.status, 'partial')
        self.assertIsNone(result.components['W1'].current_a)
        self.assertIsNone(result.components['W2'].current_a)
        self.assertAlmostEqual(result.components['R1'].current_a, 3/330)

    def test_kcl_for_every_example_and_no_input_mutation(self):
        for number in (1,2,3,4,5,6,7,8,9,10,12):
            with self.subTest(number=number):
                data = example(number)
                original = copy.deepcopy(data)
                result = solve(data)
                self.assertIn(result.status, ('solved','partial'), result.message)
                for net in data['nets']:
                    total = 0
                    for terminal in net['terminals']:
                        component = result.components[terminal['component_id']]
                        value = (component.terminal_currents_a[terminal['terminal']] if
                                 component.terminal_currents_a is not None else
                                 component.current_a * (1 if terminal['terminal'] == '1' else -1))
                        total += value
                    self.assertAlmostEqual(total, 0, places=9, msg=net['id'])
                self.assertEqual(data, original)
