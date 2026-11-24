import json,os,sqlite3,tempfile,unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from main import CircuitWindow
from database import CircuitDatabase
ROOT=Path(__file__).resolve().parents[1]

def confirm_save(window):
    from PySide6.QtWidgets import QDialogButtonBox
    window.save_button.click()
    dialog = getattr(window, 'save_dialog', None)
    if dialog is not None:
        dialog.primary_button.click()
    assert getattr(window, 'save_dialog', None) is None


class PersonalCircuitPagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=CircuitDatabase(Path(self.temp.name)/'circuits.db')
        self.window=CircuitWindow(self.db)
    def tearDown(self):
        self.window.close();self.window.deleteLater();self.app.processEvents();self.temp.cleanup()
    def test_browsing_examples_never_writes_database(self):
        self.window.show_examples()
        self.assertEqual(self.db.list_names(),[])
        self.window.show_my_circuits()
        self.assertEqual(self.window.my_circuits_page.records,[])
    def test_library_view_save_is_disabled(self):
        w=self.window;w.show_examples();original=list(w.library_page.records);sample=original[0]
        self.assertFalse(w.save_button.isEnabled())
        w.open_library_circuit(sample['name'])
        self.assertFalse(w.save_button.isEnabled())
        w.save_button.click()
        self.assertEqual(self.db.list_names(origin='user'),[])
        self.assertIsNone(getattr(w,'save_dialog',None))
        w.show_examples();self.assertEqual(w.library_page.records,original)
    def test_personal_copy_can_share_example_name_without_modifying_library(self):
        w=self.window;w.show_examples();sample=w.library_page.records[0]
        w.load_topology(sample);w.change_workspace_page(0);confirm_save(w)
        self.assertEqual(self.db.list_names(origin='user'),[sample['name']])
        w.circuit_document['notes']='Personal note';confirm_save(w)
        w.show_examples()
        self.assertEqual(next(d for d in w.library_page.records if d['name']==sample['name']),sample)
        self.assertEqual(self.db.load(sample['name'])['notes'],'Personal note')
    def test_saved_empty_circuit_appears_and_opens_from_my_circuits(self):
        w=self.window;w.new_circuit();w.circuit_name.setText('Empty personal circuit');w.rename_circuit_title();confirm_save(w)
        w.show_my_circuits();w.my_circuits_page.open_buttons['Empty personal circuit'].click()
        self.assertIsNone(w.circuit)
        self.assertEqual(w.circuit_name.text(),'Empty personal circuit')
        self.assertFalse(w.current_safety_issues)
        self.assertFalse(w.has_unsaved_circuit())
        self.assertTrue(w.overview_dock.isHidden())
    def test_saved_rename_updates_only_personal_page_on_save(self):
        w=self.window;w.new_circuit();w.circuit_name.setText('Original');w.rename_circuit_title();confirm_save(w)
        w.circuit_name.setText('Renamed');w.rename_circuit_title()
        self.assertEqual(self.db.list_names(origin='user'),['Original'])
        confirm_save(w)
        self.assertEqual(self.db.list_names(origin='user'),['Renamed'])
        self.assertEqual([d['name'] for d in w.my_circuits_page.records],['Renamed'])

class LegacyCircuitClassificationTests(unittest.TestCase):
    def test_existing_records_preserved_and_stock_hidden_from_personal_list(self):
        stock=json.loads((ROOT/'examples/01_led_series.json').read_text())
        custom=dict(stock,name='Existing personal circuit',notes='Keep me')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'old.db'
            with sqlite3.connect(path) as c:
                c.execute('CREATE TABLE circuits (name TEXT PRIMARY KEY, circuit_json TEXT NOT NULL)')
                for data in (stock,custom):c.execute('INSERT INTO circuits VALUES (?,?)',(data['name'],json.dumps(data)))
            db=CircuitDatabase(path)
            self.assertEqual(set(db.list_names()),{stock['name'],custom['name']})
            self.assertEqual(db.list_names(origin='user'),[custom['name']])
            self.assertEqual(db.load(stock['name']),stock)
            self.assertEqual(db.load(custom['name']),custom)
            db.save_workspace(stock)
            self.assertIn(stock['name'],db.list_names(origin='user'))
            self.assertIn(stock['name'],CircuitDatabase(path).list_names(origin='user'))
