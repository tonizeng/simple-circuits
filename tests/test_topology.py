import copy
import json
import unittest

from topology import TopologyError, parse_topology


def example():
    return {
        "name": "Series LED", "ground_node": "n0",
        "components": [
            {"id": "V1", "type": "voltage_source", "parameters": {"voltage_v": 5}},
            {"id": "R1", "type": "resistor", "parameters": {"resistance_ohm": 330}},
            {"id": "L1", "type": "led", "parameters": {
                "forward_voltage_v": 2}},
        ],
        "nets": [
            {"id": "n1", "terminals": [{"component_id": "V1", "terminal": "1"}, {"component_id": "R1", "terminal": "1"}]},
            {"id": "n2", "terminals": [{"component_id": "R1", "terminal": "2"}, {"component_id": "L1", "terminal": "1"}]},
            {"id": "n0", "terminals": [{"component_id": "L1", "terminal": "2"}, {"component_id": "V1", "terminal": "2"}]},
        ],
    }


class TopologyTests(unittest.TestCase):
    def test_json_reconstructs_polarity_and_connections(self):
        circuit = parse_topology(json.dumps(example()))
        self.assertEqual(circuit.terminal_nodes(), {
            ("V1", "1"): "n1", ("V1", "2"): "n0",
            ("R1", "1"): "n1", ("R1", "2"): "n2",
            ("L1", "1"): "n2", ("L1", "2"): "n0",
        })

    def test_invalid_messages(self):
        changes = [
            lambda d: d["components"].append(copy.deepcopy(d["components"][0])),
            lambda d: d["nets"].append(copy.deepcopy(d["nets"][0])),
            lambda d: d["nets"][0]["terminals"][0].update(terminal=1),
            lambda d: d["nets"][0]["terminals"][0].update(component_id="missing"),
            lambda d: d["nets"][1]["terminals"].append(d["nets"][0]["terminals"][0]),
            lambda d: d["nets"][0]["terminals"].pop(),
            lambda d: d.update(ground_node="missing"),
            lambda d: d["components"][1]["parameters"].update(resistance_ohm=0),
            lambda d: d["components"][0]["parameters"].update(voltage_v=float("nan")),
            lambda d: d["components"][0]["parameters"].update(voltage_v=True),
        ]
        for change in changes:
            data = example()
            change(data)
            with self.subTest(change=change), self.assertRaises(TopologyError):
                parse_topology(data)

    def test_singleton_net_preserves_open_terminal(self):
        data = example()
        ref = data["nets"][0]["terminals"].pop()
        data["nets"].append({"id": "open", "terminals": [ref]})
        self.assertEqual(parse_topology(data).terminal_nodes()[("R1", "1")], "open")


if __name__ == "__main__":
    unittest.main()
