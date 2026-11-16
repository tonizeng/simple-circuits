import json
import math
import unittest
from pathlib import Path
from simulation.rc import rc_timing
from topology import parse_topology


class RCTimingTests(unittest.TestCase):
    def data(self):
        return json.loads((Path(__file__).resolve().parents[1] / "examples/07_rc_charging.json").read_text())

    def test_example_and_threshold_delays(self):
        timing, reason = rc_timing(parse_topology(self.data()), "C1")
        self.assertIsNone(reason)
        self.assertAlmostEqual(timing.tau_s, 1)
        self.assertAlmostEqual(timing.delay_s(.9), math.log(10))
        self.assertAlmostEqual(timing.voltage_delay_s(0, 3.3, 1.65), math.log(2))
        self.assertAlmostEqual(timing.voltage_delay_s(3.3, 0, 1.65), math.log(2))
        for target in (3.3, 4, -1):
            with self.assertRaises(ValueError):
                timing.voltage_delay_s(0, 3.3, target)

    def test_parallel_resistance(self):
        data = self.data()
        data["components"].append({"id": "R2", "type": "resistor", "parameters": {"resistance_ohm": 10000}})
        for net in data["nets"]:
            if net["id"] in ("n1", "n2"):
                net["terminals"].append({"component_id": "R2", "terminal": "1" if net["id"] == "n1" else "2"})
        timing, _ = rc_timing(parse_topology(data), "C1")
        self.assertAlmostEqual(timing.tau_s, .5)

    def test_open_contact_has_no_finite_delay(self):
        data = self.data()
        data["components"][1] = {"id": "R1", "type": "switch", "parameters": {"closed": False}}
        timing, reason = rc_timing(parse_topology(data), "C1")
        self.assertIsNone(timing)
        self.assertIn("No resistive", reason)

    def test_charging_and_discharging_response(self):
        timing, _ = rc_timing(parse_topology(self.data()), "C1")
        self.assertEqual(timing.response(0, 0, 3.3)[0], 0)
        self.assertAlmostEqual(timing.response(0, 0, 3.3)[1], .00033)
        v, i = timing.response(1, 0, 3.3)
        self.assertAlmostEqual(v, 3.3*(1-math.exp(-1)))
        self.assertAlmostEqual(i, .00033*math.exp(-1))
        v, i = timing.response(1, 3.3, 0)
        self.assertAlmostEqual(v, 3.3*math.exp(-1))
        self.assertAlmostEqual(i, -.00033*math.exp(-1))
        self.assertEqual(timing.response(3, 1, 1), (1, 0))
        for t in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError): timing.response(t, 0, 3.3)
