import os
import json
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidget, QDialogButtonBox

from database import CircuitDatabase
from main import CircuitWindow


class ExamplesBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_seed_and_open_every_database_example(self):
        with tempfile.TemporaryDirectory() as folder:
            database = CircuitDatabase(Path(folder) / "circuits.sqlite3")
            window = CircuitWindow(database=database)
            window.show()
            QTest.mouseClick(window.examples_button, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            names = database.list_names()
            self.assertEqual(len(names), 11)
            for name in names:
                if window.examples_dialog is None:
                    window.show_examples()
                self.app.processEvents()
                dialog = window.examples_dialog
                items = dialog.findChild(QListWidget)
                self.assertEqual(items.count(), 11)
                expected_names = [json.loads(path.read_text())["name"] for path in sorted(
                    (Path(__file__).resolve().parents[1] / "examples").glob("*.json"))]
                self.assertEqual([items.item(row).text() for row in range(items.count())], expected_names)
                items.setCurrentItem(items.findItems(name, Qt.MatchFlag.MatchExactly)[0])
                buttons = dialog.findChild(QDialogButtonBox)
                QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Open),
                                 Qt.MouseButton.LeftButton)
                self.app.processEvents()
                self.assertEqual(window.circuit.name, name)
                self.assertGreaterEqual(window.circuit_name.width(),
                                        window.circuit_name.fontMetrics().horizontalAdvance(name) + 36)
                self.assertIsNone(window.examples_dialog)
            # Existing records are read as-is rather than overwritten by seeds.
            data = database.load(names[0])
            data["custom_note"] = "preserve me"
            database.save(data)
            window.show_examples()
            window.examples_dialog.reject()
            self.assertEqual(database.load(names[0])["custom_note"], "preserve me")
            window.close()

    def test_cancel_preserves_current_circuit(self):
        with tempfile.TemporaryDirectory() as folder:
            window = CircuitWindow(CircuitDatabase(Path(folder) / "circuits.sqlite3"))
            window.show_examples()
            window.examples_dialog.reject()
            self.assertIsNone(window.circuit)
            window.close()
