import json
import tempfile
import unittest
from pathlib import Path

from database import CircuitDatabase


class DatabaseTests(unittest.TestCase):
    def test_save_update_and_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "circuits.sqlite3"
            database = CircuitDatabase(path)
            data = {"name": "Student's circuit", "components": [], "nets": []}
            database.save(json.dumps(data))
            data["notes"] = "updated"
            database.save(data)
            reopened = CircuitDatabase(path)
            self.assertEqual(reopened.list_names(), [data["name"]])
            self.assertEqual(reopened.load(data["name"]), data)
            with self.assertRaises(KeyError):
                reopened.load("missing")

    def test_examples_round_trip_and_connections(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        with tempfile.TemporaryDirectory() as folder:
            database = CircuitDatabase(Path(folder) / "circuits.sqlite3")
            names = database.import_folder(examples)
            self.assertEqual(len(names), 11)
            self.assertEqual(len(set(names)), 11)
            for path in examples.glob("*.json"):
                data = json.loads(path.read_text())
                self.assertEqual(database.load(data["name"]), data)
                components = {c["id"]: c for c in data["components"]}
                self.assertEqual(len(components), len(data["components"]))
                expected = {(cid, terminal) for cid, c in components.items()
                            for terminal in (("1", "2", "3") if c["type"] == "potentiometer"
                                             else ("1", "2"))}
                actual = [(t["component_id"], t["terminal"])
                          for net in data["nets"] for t in net["terminals"]]
                self.assertEqual(set(actual), expected, path.name)
                self.assertEqual(len(actual), len(set(actual)), path.name)
                self.assertIn(data["ground_node"], [net["id"] for net in data["nets"]])

    def test_rejects_invalid_storage_documents(self):
        with tempfile.TemporaryDirectory() as folder:
            database = CircuitDatabase(Path(folder) / "circuits.sqlite3")
            for data in ([], {}, {"name": " "}, {"name": "x", "value": float("nan")}):
                with self.subTest(data=data), self.assertRaises(ValueError):
                    database.save(data)
            self.assertEqual(database.list_names(), [])

    def test_stock_voltage_upgrade_preserves_custom_records(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        stock = json.loads((examples / "01_led_series.json").read_text())
        legacy = json.loads(json.dumps(stock))
        legacy["components"][0]["parameters"]["voltage_v"] = 5
        with tempfile.TemporaryDirectory() as folder:
            database = CircuitDatabase(Path(folder) / "circuits.sqlite3")
            database.save(legacy)
            self.assertEqual(database.upgrade_stock_sources(examples), [stock["name"]])
            self.assertEqual(database.load(stock["name"]), stock)
            legacy["notes"] = "custom record"
            database.save(legacy)
            self.assertEqual(database.upgrade_stock_sources(examples), [])
            self.assertEqual(database.load(stock["name"]), legacy)
