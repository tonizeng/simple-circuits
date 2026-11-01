import copy
import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

from scipy.optimize import brentq
from simulation import solve_dc
from simulation.led_model import FalstadLEDModel
from topology import parse_topology


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def example(number):
    return json.loads(next(EXAMPLES.glob(f"{number:02d}_*.json")).read_text())


class NonlinearLEDTests(unittest.TestCase):
    def test_calibration_at_one_amp_and_analytic_derivative(self):
        for vf in (1.6, 2, 3.3):
            model = FalstadLEDModel(vf)
            self.assertAlmostEqual(model.exact_current(vf), 1, places=12)
            voltage = vf - .2
            _, slope = model.evaluate(voltage)
            finite_difference = (model.exact_current(voltage + 1e-6) -
                                 model.exact_current(voltage - 1e-6)) / 2e-6
            self.assertAlmostEqual(slope, finite_difference, places=6)

    def test_against_independent_scalar_shockley_solution(self):
        for vf in (1.6, 2, 3.3):
            for supply, resistance in ((0, 330), (1, 330), (5, 330), (12, 1000)):
                with self.subTest(vf=vf, supply=supply, resistance=resistance):
                    data = example(1)
                    data["components"][0]["parameters"]["voltage_v"] = supply
                    data["components"][1]["parameters"]["resistance_ohm"] = resistance
                    data["components"][2]["parameters"]["forward_voltage_v"] = vf
                    before = copy.deepcopy(data)
                    leakage = 1 / math.expm1(vf / (2 * .025865))
                    expected_v = brentq(lambda voltage: (supply - voltage) / resistance -
                                       leakage * math.expm1(voltage / (2 * .025865)),
                                       0, max(supply, 1e-6), xtol=1e-13)
                    expected_i = (supply - expected_v) / resistance
                    result = solve_dc(parse_topology(data), led_model="falstad")
                    self.assertEqual(result.status, "solved", result.message)
                    self.assertAlmostEqual(result.components["LED1"].voltage_v, expected_v, places=7)
                    self.assertAlmostEqual(result.components["LED1"].current_a, expected_i, places=10)
                    self.assertAlmostEqual(result.components["V1"].current_a, -expected_i, places=10)
                    self.assertEqual(data, before)

    def test_example_one_operating_point_and_optional_fixed_mode(self):
        circuit = parse_topology(example(1))
        result = solve_dc(circuit, led_model="falstad")
        self.assertAlmostEqual(result.components["LED1"].voltage_v, 1.7608123733, places=8)
        self.assertAlmostEqual(result.components["LED1"].current_a, .00981572008, places=10)
        self.assertAlmostEqual(solve_dc(circuit).components["LED1"].voltage_v, 2)

    def test_open_and_closed_contacts(self):
        for number, field in ((4, "closed"), (5, "pressed")):
            for enabled in (False, True):
                data = example(number)
                data["components"][1]["parameters"][field] = enabled
                result = solve_dc(parse_topology(data), led_model="falstad")
                self.assertEqual(result.status, "solved", result.message)
                self.assertAlmostEqual(result.components["R1"].current_a,
                                       .00981572008 if enabled else 0, places=9)
                if not enabled:
                    self.assertAlmostEqual(result.components["LED1"].voltage_v, 0, places=7)

    def test_reversed_led(self):
        data = example(1)
        for net in data["nets"]:
            for terminal in net["terminals"]:
                if terminal["component_id"] == "LED1":
                    terminal["terminal"] = "2" if terminal["terminal"] == "1" else "1"
        result = solve_dc(parse_topology(data), led_model="falstad")
        self.assertEqual(result.status, "solved", result.message)
        self.assertAlmostEqual(result.components["LED1"].voltage_v, -5, places=7)
        self.assertEqual(result.components["LED1"].state, "off")

    def test_identical_parallel_leds_share_current(self):
        data = example(1)
        data["components"].append({"id": "LED2", "type": "led", "parameters": {"forward_voltage_v": 2}})
        data["nets"][1]["terminals"].append({"component_id": "LED2", "terminal": "1"})
        data["nets"][2]["terminals"].append({"component_id": "LED2", "terminal": "2"})
        result = solve_dc(parse_topology(data), led_model="falstad")
        self.assertEqual(result.status, "solved", result.message)
        self.assertAlmostEqual(result.components["LED1"].current_a, result.components["LED2"].current_a, places=10)
        self.assertAlmostEqual(result.components["R1"].current_a,
                               result.components["LED1"].current_a * 2, places=9)

    def test_failure_never_returns_the_fixed_seed_as_a_solution(self):
        with patch("simulation.nonlinear.least_squares") as fitted:
            fitted.side_effect = ValueError("test solver failure")
            result = solve_dc(parse_topology(example(1)), led_model="falstad")
        self.assertEqual(result.status, "numerical_error")
        self.assertFalse(result.components)
