import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel
from database import CircuitDatabase
from main import CircuitWindow

class ExamplesBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_library_page_scrolls_and_opens_every_example_in_file_order(self):
        with tempfile.TemporaryDirectory() as folder:
            database = CircuitDatabase(Path(folder) / "circuits.sqlite3")
            window = CircuitWindow(database=database)
            window.show()
            window.navigation_buttons[2].click()
            self.app.processEvents()
            expected = [json.loads(p.read_text())["name"] for p in sorted(
                (Path(__file__).resolve().parents[1] / "examples").rglob("*.json"))]
            self.assertEqual([d["name"] for d in window.library_page.records], expected)
            self.assertEqual(window.content_pages.currentIndex(), 2)
            self.assertIsNone(window.examples_dialog)
            self.assertGreater(window.library_page.scroll.verticalScrollBar().maximum(), 0)
            self.assertEqual(window.library_page.scroll.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            previews = [label for label in window.library_page.findChildren(QLabel) if label.pixmap() and not label.pixmap().isNull()]
            self.assertEqual(len(previews), len(expected))
            for name in expected:
                if window.content_pages.currentIndex() != 2:
                    window.navigation_buttons[2].click()
                window.library_page.open_buttons[name].click()
                self.app.processEvents()
                self.assertEqual(window.circuit.name, name)
                self.assertEqual(window.content_pages.currentIndex(), 0)
                self.assertTrue(window.component_details.isVisible())
            data = database.load(expected[0])
            data["custom_note"] = "preserve me"
            database.save(data)
            window.show_examples()
            self.assertEqual(database.load(expected[0])["custom_note"], "preserve me")
            window.close()

    def test_browsing_library_does_not_replace_current_circuit(self):
        with tempfile.TemporaryDirectory() as folder:
            window = CircuitWindow(CircuitDatabase(Path(folder) / "circuits.sqlite3"))
            window.show_examples()
            self.assertIsNone(window.circuit)
            window.change_workspace_page(0)
            self.assertIsNone(window.circuit)
            window.close()
