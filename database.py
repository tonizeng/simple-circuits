"""Minimal SQLite storage of circuit names and self-contained JSON documents."""

import argparse
import json
import copy
import sqlite3
from pathlib import Path


DEFAULT_DATABASE = Path(__file__).resolve().parent / "data" / "circuits.sqlite3"


class CircuitDatabase:
    def __init__(self, path=DEFAULT_DATABASE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS circuits (
                    name TEXT PRIMARY KEY NOT NULL,
                    circuit_json TEXT NOT NULL,
                    origin TEXT NOT NULL DEFAULT 'user'
                )
            """)

            columns = {row[1] for row in connection.execute("PRAGMA table_info(circuits)")}
            if "origin" not in columns:
                connection.execute("ALTER TABLE circuits ADD COLUMN origin TEXT NOT NULL DEFAULT 'legacy'")
            self._classify_legacy_records(connection)

    def _classify_legacy_records(self, connection):
        """Keep legacy records; hide exact stock copies from personal circuits."""
        rows = connection.execute("SELECT name, circuit_json FROM circuits WHERE origin = 'legacy'").fetchall()
        if not rows:
            return
        stock = []
        folder = Path(__file__).resolve().parent / "examples"
        for path in sorted(folder.rglob("*.json")):
            data = json.loads(path.read_bytes())
            stock.append(data)
            legacy = copy.deepcopy(data)
            for c in legacy.get("components", []):
                if c["type"] == "voltage_source":
                    c["parameters"]["voltage_v"] = 5.0
            stock.append(legacy)
            if data.get("circuit_id") == "10_photoresistor_sensor":
                retired = copy.deepcopy(data)
                retired.update(name="Reverse-Biased Photodiode Sensor", circuit_id="10_photodiode_sensor")
                retired["components"][2] = {"id": "PD1", "type": "photodiode", "parameters": {"photocurrent_a": 1e-5}}
                for net in retired["nets"]:
                    for t in net["terminals"]:
                        if t["component_id"] == "LDR1": t["component_id"] = "PD1"
                stock.append(retired)
                old_voltage = copy.deepcopy(retired)
                old_voltage["components"][0]["parameters"]["voltage_v"] = 5.0
                stock.append(old_voltage)
        for name, raw in rows:
            data = json.loads(raw)
            origin = "example" if any(data == sample for sample in stock) else "user"
            connection.execute("UPDATE circuits SET origin = ? WHERE name = ?", (origin, name))

    def save(self, data, origin="user"):

        """Save JSON contents, replacing a record with the same circuit name.

        Storage checks JSON structure/name only, independent of renderer support.
        File paths are not stored: records remain usable if files move.
        """
        if isinstance(data, (str, bytes)):
            data = json.loads(data)
        if not isinstance(data, dict):
            raise ValueError("Circuit JSON must be an object.")
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Circuit JSON must contain a nonempty name.")
        contents = json.dumps(data, allow_nan=False)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO circuits (name, circuit_json, origin) VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET circuit_json = excluded.circuit_json, origin = excluded.origin",
                (name, contents, origin),
            )
        return name

    def save_workspace(self, data, previous_name=None):
        """Save a workspace and atomically rename its own record without collisions."""
        if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not data["name"].strip():
            raise ValueError("Circuit name cannot be empty.")
        name = data["name"]
        contents = json.dumps(data, allow_nan=False)
        with sqlite3.connect(self.path) as connection:
            existing = connection.execute("SELECT circuit_json, origin FROM circuits WHERE name = ?", (name,)).fetchone()
            if existing and existing[1] == "user" and previous_name != name and json.loads(existing[0]) != data:
                raise ValueError("That name already exists. Choose another name.")
            connection.execute("INSERT INTO circuits (name, circuit_json, origin) VALUES (?, ?, 'user') "
                               "ON CONFLICT(name) DO UPDATE SET circuit_json = excluded.circuit_json, origin = 'user'", (name, contents))
            if previous_name is not None and previous_name != name:
                connection.execute("DELETE FROM circuits WHERE name = ?", (previous_name,))
        return name

    def load(self, name):
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT circuit_json FROM circuits WHERE name = ?", (name,)
            ).fetchone()
        if row is None:
            raise KeyError(name)
        return json.loads(row[0])

    def list_names(self, origin=None):
        with sqlite3.connect(self.path) as connection:
            if origin is None:
                rows = connection.execute("SELECT name FROM circuits ORDER BY name COLLATE NOCASE")
            else:
                rows = connection.execute("SELECT name FROM circuits WHERE origin = ? ORDER BY name COLLATE NOCASE", (origin,))
            return [row[0] for row in rows]

    def upgrade_stock_sources(self, folder):
        """Upgrade exact legacy 5 V bundled records, preserving customized circuits."""
        names = set(self.list_names())
        updated = []
        for path in sorted(Path(folder).rglob("*.json")):
            current = json.loads(path.read_bytes())
            if current["name"] not in names:
                continue
            legacy = copy.deepcopy(current)
            for component in legacy["components"]:
                if component["type"] == "voltage_source":
                    component["parameters"]["voltage_v"] = 5.0
            if self.load(current["name"]) == legacy:
                self.save(current)
                updated.append(current["name"])
        return updated

    def upgrade_stock_photoresistor(self, folder):
        """Replace only the exact retired bundled photodiode example, not user edits."""
        path = Path(folder) / "10_photoresistor_sensor.json"
        if not path.exists():
            return False
        current = json.loads(path.read_bytes())
        legacy = copy.deepcopy(current)
        legacy["name"] = "Reverse-Biased Photodiode Sensor"
        legacy["circuit_id"] = "10_photodiode_sensor"
        legacy["components"][2] = {"id": "PD1", "type": "photodiode",
                                     "parameters": {"photocurrent_a": 1e-5}}
        for net in legacy["nets"]:
            for terminal in net["terminals"]:
                if terminal["component_id"] == "LDR1":
                    terminal["component_id"] = "PD1"
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT circuit_json FROM circuits WHERE name = ?",
                                     (legacy["name"],)).fetchone()
            if row is None:
                return False
            stored = json.loads(row[0])
            legacy_5v = copy.deepcopy(legacy)
            legacy_5v["components"][0]["parameters"]["voltage_v"] = 5.0
            if stored not in (legacy, legacy_5v):
                return False
            connection.execute("INSERT OR IGNORE INTO circuits (name, circuit_json) VALUES (?, ?)",
                               (current["name"], json.dumps(current)))
            connection.execute("DELETE FROM circuits WHERE name = ?", (legacy["name"],))
        return True

    def import_folder(self, folder):
        return [self.save(path.read_bytes(), origin="example") for path in sorted(Path(folder).glob("*.json"))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--import-examples", type=Path, metavar="FOLDER")
    args = parser.parse_args()
    database = CircuitDatabase(args.database)
    if args.import_examples:
        imported = database.import_folder(args.import_examples)
        print(f"Imported {len(imported)} circuits.")
    for name in database.list_names():
        print(name)


if __name__ == "__main__":
    main()
