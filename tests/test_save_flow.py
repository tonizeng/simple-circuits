import copy,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMessageBox
from database import CircuitDatabase
from main import CircuitWindow
ROOT=Path(__file__).resolve().parents[1]

class SaveFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.db=CircuitDatabase(Path(self.folder.name)/'db.sqlite')
        self.w=CircuitWindow(database=self.db)
        self.data=json.loads((ROOT/'examples/01_led_series.json').read_text())
        self.w.load_topology(self.data)
    def tearDown(self):
        dialog=getattr(self.w,'save_dialog',None)
        if dialog is not None:dialog.reject()
        self.w.close();self.w.deleteLater();self.app.processEvents();self.folder.cleanup()
    def commit(self,dialog):dialog.primary_button.click()
    def test_new_name_cancel_and_empty_circuit(self):
        self.w.create_blank_circuit();before=self.w.workspace_document()
        self.w.save_as_button.click();d=self.w.save_dialog;d.name_field.setText('Cancel me');d.reject()
        self.assertEqual(self.db.list_names(),[]);self.assertEqual(self.w.workspace_document(),before)
        self.w.save_as_button.click();d=self.w.save_dialog;d.name_field.setText('Empty design');self.commit(d)
        self.assertEqual(self.db.load('Empty design')['components'],[])
        self.assertFalse(self.w.has_unsaved_circuit())
    def test_library_view_is_readonly_reference_upload_saves_as_new(self):
        self.w.open_library_circuit(self.data['name'])
        self.assertFalse(self.w.save_button.isEnabled())
        self.w.save_button.click()
        self.assertIsNone(getattr(self.w,'save_dialog',None))
        self.w.start_reference_build()
        self.assertFalse(self.w.save_button.isEnabled())
        self.w.compare_detected_build(self.data)
        self.assertFalse(self.w.save_button.isEnabled())
        self.assertTrue(self.w.save_as_button.isEnabled())
        self.w.save_as_button.click();d=self.w.save_dialog
        self.assertIsNone(d.existing_name)
        d.name_field.setText('My example');self.commit(d)
        self.assertEqual(self.db.load('My example')['components'],self.data['components'])
        self.assertEqual(json.loads((ROOT/'examples/01_led_series.json').read_text()),self.data)
        self.w.end_reference_build()
        self.assertFalse(self.w.save_button.isEnabled())
    def test_update_and_save_as_new(self):
        self.db.save(self.data);self.w.open_saved_circuit(self.data['name'])
        self.w.circuit_document['notes']='Updated'
        self.w.save_button.click()
        self.assertIsNone(getattr(self.w,'save_dialog',None))
        original=self.db.load(self.data['name'])
        self.assertEqual(original['notes'],'Updated')
        self.w.circuit_document['notes']='Copy only'
        self.w.save_as_button.click();d=self.w.save_dialog
        d.name_field.setText('Personal copy');self.commit(d)
        self.assertEqual(self.db.load(self.data['name']),original)
        self.assertEqual(self.db.load('Personal copy')['notes'],'Copy only')
    def test_invalid_and_duplicate_name_keep_dialog_and_records(self):
        self.db.save(dict(self.data,name='Taken'))
        self.w.save_as_button.click();d=self.w.save_dialog
        for name in (' ', 'Taken'):
            d.name_field.setText(name);self.commit(d)
            self.assertIs(self.w.save_dialog,d);self.assertFalse(d.error.isHidden())
        self.assertEqual(self.db.list_names(),['Taken'])
        d.name_field.setText('Available');self.commit(d)
        self.assertIn('Available',self.db.list_names())
    def test_write_failure_can_retry_without_losing_workspace(self):
        self.w.save_as_button.click();d=self.w.save_dialog;d.name_field.setText('Retry me')
        before=self.w.workspace_document()
        with patch.object(self.db,'save_workspace',side_effect=sqlite3.OperationalError('locked')):
            self.commit(d)
        self.assertIs(self.w.save_dialog,d);self.assertEqual(self.w.workspace_document(),before)
        self.assertEqual(self.db.list_names(),[])
        self.assertEqual(d.primary_button.text(),'Retry Save')
        self.commit(d);self.assertIsNone(self.w.save_dialog)
        self.assertIn('Retry me',self.db.list_names())
    def test_reference_saves_detected_build_not_reference(self):
        self.db.save(self.data);self.w.open_saved_circuit(self.data['name']);self.w.start_reference_build()
        self.assertFalse(self.w.save_button.isEnabled())
        detected=copy.deepcopy(self.data);detected['components'][1]['parameters']['resistance_ohm']=1000
        self.w.compare_detected_build(detected)
        before=self.w.workspace_document()
        self.w.save_as_button.click();d=self.w.save_dialog
        self.assertIsNone(d.existing_name)
        d.name_field.setText('My physical build');self.commit(d)
        self.assertEqual(self.db.load('My physical build')['components'],detected['components'])
        self.assertEqual(self.db.load(self.data['name']),self.data)
        self.assertEqual(self.w.workspace_document(),before)
        self.assertIsNotNone(self.w.reference_document)
        self.assertFalse(self.w.has_unsaved_circuit())
        detected['components'][1]['parameters']['resistance_ohm']=2200
        self.w.compare_detected_build(detected)
        self.assertTrue(self.w.has_unsaved_circuit())
        with patch('main.QMessageBox.question',return_value=QMessageBox.StandardButton.Cancel):self.w.new_circuit()
        self.assertIsNotNone(self.w.reference_document)
    def test_unsafe_circuit_can_be_saved_without_power_approval(self):
        unsafe=copy.deepcopy(self.data);unsafe['components'][0]['parameters']['voltage_v']=5
        self.w.load_topology(unsafe)
        self.assertTrue(self.w.current_safety_issues)
        self.w.save_as_button.click();d=self.w.save_dialog;d.name_field.setText('Unsafe draft');self.commit(d)
        self.assertEqual(self.db.load('Unsafe draft')['components'],unsafe['components'])
        self.assertFalse(self.w.power_granted)
    def test_cancel_before_new_keeps_current(self):
        before=self.w.workspace_document()
        with patch('main.QMessageBox.question',return_value=QMessageBox.StandardButton.Cancel):self.w.new_circuit()
        self.assertEqual(self.w.workspace_document(),before)
        self.assertEqual(self.db.list_names(),[])
    def test_save_before_new_uses_current_name_without_dialog(self):
        with patch('main.QMessageBox.question',return_value=QMessageBox.StandardButton.Save):self.w.new_circuit()
        self.assertIsNone(self.w.circuit)
        self.assertIsNone(getattr(self.w,'save_dialog',None))
        self.assertIn(self.data['name'],self.db.list_names())
    def test_save_as_new_database_never_replaces_identical_record(self):
        self.db.save(self.data)
        with self.assertRaises(ValueError):self.db.save_workspace(self.data,require_new=True)
        self.assertEqual(self.db.load(self.data['name']),self.data)

    def test_copy_with_original_name_keeps_original_and_retry_action(self):
        self.db.save(self.data);self.w.open_saved_circuit(self.data['name'])
        self.w.circuit_document['notes']='Copy only'
        self.w.save_as_button.click();d=self.w.save_dialog
        with patch.object(self.db,'save_workspace',side_effect=sqlite3.OperationalError('locked')):
            self.commit(d)
        self.assertEqual(d.primary_button.text(),'Retry Save')
        self.assertNotEqual(d.name_field.text(),self.data['name'])
        self.assertEqual(self.db.load(self.data['name']),self.data)
        d.name_field.returnPressed.emit()
        self.assertEqual(len(self.db.list_names()),2)
        self.assertEqual(self.db.load(self.data['name']),self.data)

    def test_save_as_copies_library_without_overwriting_it(self):
        self.w.open_library_circuit(self.data['name'])
        self.assertFalse(self.w.save_button.isEnabled())
        self.assertTrue(self.w.save_as_button.isEnabled())
        self.w.save_as_button.click();d=self.w.save_dialog
        self.assertIsNone(d.existing_name)
        d.name_field.setText('Library copy');self.commit(d)
        self.assertEqual(self.db.load('Library copy')['components'],self.data['components'])
        self.assertTrue(self.w.save_button.isEnabled())
        self.assertEqual(json.loads((ROOT/'examples/01_led_series.json').read_text()),self.data)

    def test_reference_save_as_before_upload_does_not_save_reference(self):
        self.w.start_reference_build()
        self.assertTrue(self.w.save_as_button.isEnabled())
        self.w.save_as_button.click()
        self.assertIsNone(getattr(self.w,'save_dialog',None))
        self.assertEqual(self.db.list_names(),[])
        self.assertIn('upload',self.w.build_status_label.text().lower())

    def test_save_first_and_subsequent_clicks_never_open_dialog(self):
        self.w.create_blank_circuit()
        name=self.w.circuit_name.text()
        self.w.save_button.click()
        self.assertIsNone(getattr(self.w,'save_dialog',None))
        self.assertEqual(self.db.load(name)['components'],[])
        self.w.circuit_document['notes']='Updated directly'
        self.w.save_button.click()
        self.assertIsNone(getattr(self.w,'save_dialog',None))
        self.assertEqual(self.db.load(name)['notes'],'Updated directly')

    def test_direct_save_failure_preserves_workspace_without_dialog(self):
        before=self.w.workspace_document()
        with patch.object(self.db,'save_workspace',side_effect=sqlite3.OperationalError('locked')):
            self.w.save_button.click()
        self.assertIsNone(getattr(self.w,'save_dialog',None))
        self.assertEqual(self.w.workspace_document(),before)
        self.assertEqual(self.db.list_names(),[])
        self.assertIn('Could not save',self.w.statusBar().currentMessage())

    def test_save_as_live_name_validation_without_database_writes(self):
        self.db.save(dict(self.data,name='Taken'))
        self.w.save_as_button.click();d=self.w.save_dialog
        with patch.object(self.db,'save_workspace',wraps=self.db.save_workspace) as writer:
            d.name_field.setText('  Taken  ')
            self.assertFalse(d.primary_button.isEnabled())
            self.assertIn('already exists',d.error.text())
            self.assertFalse(d.error.isHidden())
            d.name_field.returnPressed.emit()
            writer.assert_not_called()
            d.name_field.setText(' ')
            self.assertFalse(d.primary_button.isEnabled())
            self.assertIn('Enter a circuit name',d.error.text())
            d.name_field.setText('Available name')
            self.assertTrue(d.primary_button.isEnabled())
            self.assertTrue(d.error.isHidden())
            writer.assert_not_called()
            self.commit(d)
            self.assertEqual(writer.call_count,1)
        self.assertIn('Available name',self.db.list_names())

    def test_final_database_check_rejects_name_added_after_dialog_open(self):
        self.w.save_as_button.click();d=self.w.save_dialog
        d.name_field.setText('Added later')
        self.assertTrue(d.primary_button.isEnabled())
        external=dict(self.data,name='Added later',notes='Preserve this record')
        self.db.save(external)
        self.commit(d)
        self.assertIs(self.w.save_dialog,d)
        self.assertIn('already exists',d.error.text())
        self.assertEqual(self.db.load('Added later'),external)
        self.assertFalse(d.primary_button.isEnabled())
