import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy,json,tempfile,unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication,QLineEdit,QDialogButtonBox
from database import CircuitDatabase
from main import CircuitWindow

class TitleSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.database=CircuitDatabase(Path(self.folder.name)/'circuits.db')
        self.window=CircuitWindow(database=self.database)
        self.data=json.loads((Path(__file__).resolve().parents[1]/'examples/01_led_series.json').read_text())
        self.window.load_topology(self.data)
    def tearDown(self):
        self.window.close();self.window.deleteLater();self.app.processEvents();self.folder.cleanup()
    def test_pencil_renames_only_until_save_clicked(self):
        original=copy.deepcopy(self.data)
        self.window.circuit_name.actions()[0].trigger()
        dialog=self.window.name_dialog
        dialog.findChild(QLineEdit,'savedCircuitName').setText('My LED circuit')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        self.assertEqual(self.database.list_names(),[])
        self.assertEqual(self.window.circuit.name,'My LED circuit')
        self.assertTrue(self.window.has_unsaved_circuit())
        self.window.save_button.click()
        self.assertEqual(self.database.load('My LED circuit'),dict(self.data,name='My LED circuit'))
        self.assertEqual(self.data,original)
        self.assertFalse(self.window.has_unsaved_circuit())
    def test_pencil_dialog_renames_without_database_write(self):
        self.window.edit_circuit_title();dialog=self.window.name_dialog
        dialog.findChild(QLineEdit,'savedCircuitName').setText('Renamed from pencil')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        self.assertEqual(self.window.circuit.name,'Renamed from pencil')
        self.assertEqual(self.database.list_names(),[])
        self.window.save_button.click()
        self.assertEqual(self.database.load('Renamed from pencil')['name'],'Renamed from pencil')
    def test_saved_rename_persists_only_when_saved(self):
        self.database.save(self.data);self.window.load_topology(self.data)
        self.window.circuit_name.setText('Renamed saved circuit');self.window.rename_circuit_title()
        self.assertEqual(self.database.list_names(),[self.data['name']])
        self.assertEqual(self.database.load(self.data['name']),self.data)
        self.window.save_button.click()
        self.assertEqual(self.database.list_names(),['Renamed saved circuit'])
    def test_duplicate_name_does_not_overwrite_or_delete_records(self):
        self.database.save(self.data);self.window.load_topology(self.data)
        existing=dict(self.data,name='Already saved',description='Keep this');self.database.save(existing)
        self.window.circuit_name.setText('Already saved');self.window.rename_circuit_title()
        self.assertFalse(self.window.save_circuit_title())
        self.assertEqual(self.database.load('Already saved'),existing)
        self.assertEqual(self.database.load(self.data['name']),self.data)
        self.assertTrue(self.window.has_unsaved_circuit())
    def test_blank_name_and_cancel_are_not_saved(self):
        self.window.circuit_name.setText(' ')
        self.assertFalse(self.window.rename_circuit_title())
        self.assertEqual(self.window.circuit_name.text(),self.data['name'])
        self.window.edit_circuit_title();self.window.name_dialog.reject()
        self.assertEqual(self.database.list_names(),[])
        self.assertEqual(self.window.circuit.name,self.data['name'])
    def test_empty_circuit_saved_reopened_and_renamed(self):
        w=self.window;w.create_blank_circuit();w.circuit_name.setText('Empty sketch');w.rename_circuit_title()
        self.assertEqual(self.database.list_names(),[])
        w.save_button.click();saved=self.database.load('Empty sketch')
        self.assertEqual(saved['components'],[]);self.assertEqual(saved['nets'],[])
        w.load_topology(saved)
        self.assertIsNone(w.circuit);self.assertFalse(w.current_safety_issues)
        self.assertFalse(w.has_unsaved_circuit());self.assertFalse(w.export_button.isEnabled())
        w.circuit_name.setText('Empty renamed');w.rename_circuit_title()
        self.assertEqual(self.database.list_names(),['Empty sketch'])
        w.save_button.click();self.assertEqual(self.database.list_names(),['Empty renamed'])
        w.refresh_my_circuits()
        self.assertIn('Empty renamed',w.my_circuits_page.open_buttons)

    def test_header_cannot_be_edited_directly(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        field=self.window.circuit_name
        before=field.text()
        self.assertTrue(field.isReadOnly())
        self.assertEqual(field.focusPolicy(),Qt.FocusPolicy.NoFocus)
        self.assertEqual(field.cursor().shape(),Qt.CursorShape.ArrowCursor)
        QTest.keyClicks(field,'cannot edit')
        self.assertEqual(field.text(),before)
        field.actions()[0].trigger()
        self.assertIsNotNone(self.window.name_dialog)
        self.assertFalse(self.window.name_dialog.findChild(QLineEdit,'savedCircuitName').isReadOnly())
        self.window.name_dialog.reject()
