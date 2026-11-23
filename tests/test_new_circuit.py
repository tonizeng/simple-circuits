import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QMessageBox,QLineEdit,QDialogButtonBox
from database import CircuitDatabase
from main import CircuitWindow
ROOT=Path(__file__).resolve().parents[1]

class NewCircuitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=CircuitDatabase(Path(self.temp.name)/'circuits.db')
        self.window=CircuitWindow(database=self.db)
        self.data=json.loads((ROOT/'examples/07_rc_charging.json').read_text())
    def tearDown(self):
        self.window.close();self.window.deleteLater();self.app.processEvents();self.temp.cleanup()
    def test_new_blank_workspace_and_sequential_names(self):
        w=self.window
        w.new_circuit_button.click()
        self.assertIsNone(w.circuit)
        self.assertFalse(w.topology_valid)
        self.assertEqual(w.current_safety_issues,())
        self.assertEqual(w.circuit_name.text(),'Untitled 1')
        self.assertTrue(w.overview_dock.isHidden())
        self.assertFalse(w.view_actions[1].isChecked())
        self.assertTrue(w.save_button.isEnabled())
        self.assertFalse(w.export_button.isEnabled())
        self.assertEqual(self.db.list_names(),[])
        w.new_circuit_button.click();self.assertEqual(w.circuit_name.text(),'Untitled 1')
        self.assertTrue(w.save_circuit_title())
        w.new_circuit_button.click();self.assertEqual(w.circuit_name.text(),'Untitled 2')
    def test_cancel_preserves_unsaved_circuit(self):
        w=self.window;w.load_topology(self.data);before=w.circuit
        with patch('main.QMessageBox.question',return_value=QMessageBox.StandardButton.Cancel):w.new_circuit()
        self.assertIs(w.circuit,before)
        self.assertEqual(self.db.list_names(),[])
    def test_discard_clears_previews_without_deleting_saved_records(self):
        self.db.save(dict(self.data,name='Keep me'))
        w=self.window;w.load_topology(self.data);w.canvas.rc_slider.setValue(100)
        with patch('main.QMessageBox.question',return_value=QMessageBox.StandardButton.Discard):w.new_circuit()
        self.assertIsNone(w.circuit)
        self.assertIsNone(w.rc_preview_result)
        self.assertTrue(w.canvas.rc_controls.isHidden())
        self.assertFalse(w.power_granted)
        self.assertIsNone(w.power_protection.topology_revision)
        self.assertEqual(self.db.list_names(),['Keep me'])
    def test_save_then_new_and_load_new_topology(self):
        w=self.window;w.load_topology(self.data)
        w.circuit_name.setText('My RC circuit');w.rename_circuit_title()
        with patch('main.QMessageBox.question',return_value=QMessageBox.StandardButton.Save):w.new_circuit()
        self.assertIsNone(w.circuit)
        self.assertEqual(self.db.load('My RC circuit')['components'],self.data['components'])
        w.load_topology(self.data)
        self.assertTrue(w.save_button.isEnabled())
        self.assertTrue(w.export_button.isEnabled())

    def test_failed_save_keeps_current_circuit(self):
        w=self.window;w.load_topology(self.data);before=w.circuit
        with patch('main.QMessageBox.question',return_value=QMessageBox.StandardButton.Save), patch.object(w,'save_circuit_title',return_value=False):w.new_circuit()
        self.assertIs(w.circuit,before)
        self.assertEqual(self.db.list_names(),[])

    def test_saved_record_does_not_prompt_for_view_changes(self):
        self.db.save(self.data)
        w=self.window;w.load_topology(self.data)
        w.canvas.zoom_by(1.2);w.canvas.rc_slider.setValue(100);w.select_component_details('C1')
        with patch('main.QMessageBox.question') as prompt:w.new_circuit();prompt.assert_not_called()
        self.assertIsNone(w.circuit)
        self.assertEqual(self.db.load(self.data['name']),self.data)

    def test_blank_workspace_can_be_renamed_without_saving_empty_topology(self):
        w=self.window;w.new_circuit()
        w.edit_circuit_title()
        dialog=w.name_dialog
        self.assertEqual(dialog.windowTitle(),'Rename circuit')
        dialog.findChild(QLineEdit,'savedCircuitName').setText('My new circuit')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        self.assertEqual(w.circuit_name.text(),'My new circuit')
        self.assertEqual(w.draft_circuit_name,'My new circuit')
        self.assertIsNone(w.circuit)
        self.assertEqual(self.db.list_names(),[])
        self.assertTrue(w.save_button.isEnabled())

    def test_blank_workspace_pencil_and_cancel_rename(self):
        w=self.window;w.new_circuit()
        w.circuit_name.actions()[0].trigger()
        dialog=w.name_dialog
        dialog.findChild(QLineEdit,'savedCircuitName').setText('Renamed draft')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        self.assertEqual(w.draft_circuit_name,'Renamed draft')
        w.edit_circuit_title()
        w.name_dialog.findChild(QLineEdit,'savedCircuitName').setText('Discard this name')
        w.name_dialog.reject()
        self.assertEqual(w.circuit_name.text(),'Renamed draft')
        w.circuit_name.setText(' ')
        self.assertFalse(w.rename_circuit_title())
        self.assertEqual(w.circuit_name.text(),'Renamed draft')

    def test_renamed_empty_workspace_prompts_before_discard(self):
        w=self.window;w.new_circuit();w.circuit_name.setText('Draft');w.rename_circuit_title()
        self.assertTrue(w.has_unsaved_circuit())
        with patch('main.QMessageBox.question',return_value=QMessageBox.StandardButton.Cancel):w.new_circuit()
        self.assertEqual(w.circuit_name.text(),'Draft')
        w.save_button.click()
        self.assertFalse(w.has_unsaved_circuit())
        with patch('main.QMessageBox.question') as prompt:w.new_circuit();prompt.assert_not_called()
        self.assertEqual(self.db.load('Draft')['components'],[])
