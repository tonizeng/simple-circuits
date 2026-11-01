"""Minimal SQLite storage of circuit names and self-contained JSON documents."""

import argparse
import json
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
                    circuit_json TEXT NOT NULL
                )
            """)

    def save(self, data):
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
                "INSERT INTO circuits (name, circuit_json) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET circuit_json = excluded.circuit_json",
                (name, contents),
            )
        return name

    def load(self, name):
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT circuit_json FROM circuits WHERE name = ?", (name,)
            ).fetchone()
        if row is None:
            raise KeyError(name)
        return json.loads(row[0])

    def list_names(self):
        with sqlite3.connect(self.path) as connection:
            return [row[0] for row in connection.execute(
                "SELECT name FROM circuits ORDER BY name COLLATE NOCASE"
            )]

    def import_folder(self, folder):
        return [self.save(path.read_bytes()) for path in sorted(Path(folder).glob("*.json"))]


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
