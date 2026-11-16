import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import copy
import json
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from database import CircuitDatabase
from main import CircuitWindow


class TitleSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.database = CircuitDatabase(Path(self.folder.name) / "circuits.sqlite3")
        self.window = CircuitWindow(database=self.database)
        self.data = json.loads((Path(__file__).resolve().parents[1] / "examples/01_led_series.json").read_text())
        self.window.load_topology(self.data)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.folder.cleanup()

    def test_enter_saves_new_name_with_metadata_and_without_mutating_input(self):
        original = copy.deepcopy(self.data)
        self.window.circuit_name.setText("My LED circuit")
        self.window.circuit_name.returnPressed.emit()
        expected = dict(self.data, name="My LED circuit")
        self.assertEqual(self.database.load("My LED circuit"), expected)
        self.assertEqual(self.data, original)
        self.assertEqual(self.window.circuit.name, "My LED circuit")

    def test_blank_and_existing_names_do_not_overwrite_another_record(self):
        existing = dict(self.data, name="Already saved", description="Keep this")
        self.database.save(existing)
        self.window.circuit_name.setText("Already saved")
        self.window.save_circuit_title()
        self.assertEqual(self.database.load("Already saved"), existing)
        self.assertEqual(self.window.circuit.name, self.data["name"])
        self.window.circuit_name.setText("  ")
        self.window.save_circuit_title()
        self.assertEqual(self.window.circuit_name.text(), self.data["name"])
        self.assertEqual(self.database.list_names(), ["Already saved"])

    def test_save_button_opens_name_dialog_with_explicit_save(self):
        from PySide6.QtWidgets import QLineEdit, QDialogButtonBox
        self.window.save_button.click()
        dialog = self.window.name_dialog
        dialog.findChild(QLineEdit, "savedCircuitName").setText("Saved from button")
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        self.assertEqual(self.database.load("Saved from button")["name"], "Saved from button")

    def test_cancel_naming_does_not_save_or_rename(self):
        self.window.edit_circuit_title()
        self.window.name_dialog.reject()
        self.assertEqual(self.database.list_names(), [])
        self.assertEqual(self.window.circuit.name, self.data["name"])
        self.assertIsNone(self.window.name_dialog)
