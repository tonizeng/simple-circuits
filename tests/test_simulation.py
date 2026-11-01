import copy
import json
import unittest
from pathlib import Path

from topology import parse_topology
from simulation import solve_dc


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def example(number):
    return json.loads(next(EXAMPLES.glob(f"{number:02d}_*.json")).read_text())


def solve(data):
    # Retain regression coverage for the optional introductory fixed-drop model.
    return solve_dc(parse_topology(data), led_model="fixed")


class SimulationTests(unittest.TestCase):
    def test_led_series_and_source_sign(self):
        result = solve(example(1))
        self.assertEqual(result.status, "solved")
        self.assertAlmostEqual(result.components["LED1"].voltage_v, 2)
        self.assertAlmostEqual(result.components["R1"].voltage_v, 3)
        self.assertAlmostEqual(result.components["R1"].current_a, 3 / 330)
        self.assertAlmostEqual(result.components["V1"].current_a, -3 / 330)
        self.assertEqual(result.components["LED1"].state, "on")

    def test_divider(self):
        result = solve(example(2))
        self.assertEqual(result.status, "solved")
        self.assertAlmostEqual(result.node_voltages["n2"], 2.5)
        for cid in ("R1", "R2"):
            self.assertAlmostEqual(result.components[cid].current_a, .0025)

    def test_parallel_branches_and_kcl(self):
        data = example(3)
        result = solve(data)
        self.assertEqual(result.status, "solved")
        self.assertAlmostEqual(result.components["R1"].current_a, 5 / 1000)
        self.assertAlmostEqual(result.components["R2"].current_a, 5 / 2200)
        self.assertAlmostEqual(result.components["V1"].current_a, -5 / 1000 - 5 / 2200)
        for net in data["nets"]:
            total = sum(result.components[t["component_id"]].current_a *
                        (1 if t["terminal"] == "1" else -1) for t in net["terminals"])
            self.assertAlmostEqual(total, 0, places=10)

    def test_switch_open_and_closed(self):
        data = example(4)
        result = solve(data)
        self.assertAlmostEqual(result.components["S1"].voltage_v, 0)
        self.assertAlmostEqual(result.components["S1"].current_a, 3 / 330)
        data["components"][1]["parameters"]["closed"] = False
        result = solve(data)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.components["S1"].current_a, 0)
        self.assertIsNone(result.components["S1"].voltage_v)
        self.assertEqual(result.components["R1"].current_a, 0)
        self.assertAlmostEqual(result.components["R1"].voltage_v, 0)
        self.assertEqual(result.components["LED1"].state, "off")

    def test_button_normally_open_and_normally_closed(self):
        for normal in (False, True):
            for pressed in (False, True):
                with self.subTest(normal=normal, pressed=pressed):
                    data = example(5)
                    data["components"][1]["parameters"].update(normally_closed=normal, pressed=pressed)
                    result = solve(data)
                    closed = normal != pressed
                    self.assertEqual(result.components["SW1"].state, "closed" if closed else "open")
                    self.assertAlmostEqual(result.components["R1"].current_a, 3 / 330 if closed else 0)

    def test_led_reverse_below_threshold_and_boundary(self):
        data = example(1)
        for net in data["nets"]:
            for terminal in net["terminals"]:
                if terminal["component_id"] == "LED1":
                    terminal["terminal"] = "2" if terminal["terminal"] == "1" else "1"
        result = solve(data)
        self.assertEqual(result.status, "solved")
        self.assertAlmostEqual(result.components["LED1"].voltage_v, -5)
        self.assertEqual(result.components["LED1"].current_a, 0)
        for voltage in (0, 1, 2):
            data = example(1)
            data["components"][0]["parameters"]["voltage_v"] = voltage
            result = solve(data)
            self.assertEqual(result.status, "solved")
            self.assertEqual(result.components["LED1"].current_a, 0)
            self.assertEqual(result.components["LED1"].state, "off")

    def test_reference_selection_and_voltage_differences(self):
        data = example(1)
        original = copy.deepcopy(data)
        del data["ground_node"]
        self.assertEqual(solve(data).ground_node, "n0")
        self.assertNotIn("ground_node", data)
        original["ground_node"] = "n1"
        result = solve(original)
        self.assertAlmostEqual(result.node_voltages["n0"], -5)
        self.assertAlmostEqual(result.components["R1"].voltage_v, 3)
        self.assertAlmostEqual(result.components["R1"].current_a, 3 / 330)

    def test_source_short_is_inconsistent(self):
        data = example(3)
        data["components"][1] = {"id": "R1", "type": "switch", "parameters": {"closed": True}}
        self.assertEqual(solve(data).status, "inconsistent")

    def test_parallel_sources_ambiguous_currents_and_inconsistent_values(self):
        data = example(3)
        data["components"][1] = {"id": "R1", "type": "voltage_source", "parameters": {"voltage_v": 5}}
        result = solve(data)
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.components["V1"].current_a)
        self.assertAlmostEqual(result.components["R2"].current_a, 5 / 2200)
        data["components"][1]["parameters"]["voltage_v"] = 6
        self.assertEqual(solve(data).status, "inconsistent")
        del data["ground_node"]
        self.assertEqual(solve(data).status, "invalid")

    def test_floating_resistor_has_unknown_absolute_voltage_but_known_drop(self):
        data = example(3)
        data["components"].append({"id": "R3", "type": "resistor", "parameters": {"resistance_ohm": 1000}})
        data["nets"].extend([
            {"id": "float1", "terminals": [{"component_id": "R3", "terminal": "1"}]},
            {"id": "float2", "terminals": [{"component_id": "R3", "terminal": "2"}]},
        ])
        result = solve(data)
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.node_voltages["float1"])
        self.assertIsNone(result.node_voltages["float2"])
        self.assertEqual(result.components["R3"].current_a, 0)
        self.assertEqual(result.components["R3"].voltage_v, 0)

    def test_parallel_leds_do_not_invent_current_sharing(self):
        data = example(1)
        data["components"].append({"id": "LED2", "type": "led", "parameters": {"forward_voltage_v": 2}})
        data["nets"][1]["terminals"].append({"component_id": "LED2", "terminal": "1"})
        data["nets"][2]["terminals"].append({"component_id": "LED2", "terminal": "2"})
        result = solve(data)
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.components["LED1"].current_a)
        self.assertIsNone(result.components["LED2"].current_a)
        self.assertAlmostEqual(result.components["R1"].current_a, 3 / 330)

    def test_remaining_examples_have_dc_operating_points(self):
        for number in (6, 7, 8, 9, 10, 12):
            with self.subTest(number=number):
                result = solve(example(number))
                self.assertEqual(result.status, "solved", result.message)
                self.assertTrue(result.components)
