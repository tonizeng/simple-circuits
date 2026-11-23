import json,os,sqlite3,tempfile,unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from main import CircuitWindow
from database import CircuitDatabase
ROOT=Path(__file__).resolve().parents[1]

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
    def test_save_example_copy_to_my_circuits_only(self):
        w=self.window;w.show_examples();original=list(w.library_page.records);sample=original[0]
        w.open_library_circuit(sample['name'])
        w.circuit_name.setText('My copy');w.rename_circuit_title()
        self.assertEqual(self.db.list_names(origin='user'),[])
        w.save_button.click()
        self.assertIn('My copy',w.my_circuits_page.open_buttons)
        w.show_examples();self.assertEqual(w.library_page.records,original)
        w.navigation_buttons[1].click()
        self.assertEqual([d['name'] for d in w.my_circuits_page.records],['My copy'])
        w.my_circuits_page.open_buttons['My copy'].click()
        self.assertEqual(w.circuit.name,'My copy')
        self.assertEqual(w.content_pages.currentIndex(),0)
    def test_personal_copy_can_share_example_name_without_modifying_library(self):
        w=self.window;w.show_examples();sample=w.library_page.records[0]
        w.open_library_circuit(sample['name']);w.save_button.click()
        self.assertEqual(self.db.list_names(origin='user'),[sample['name']])
        w.circuit_document['notes']='Personal note';w.save_button.click()
        w.show_examples()
        self.assertEqual(next(d for d in w.library_page.records if d['name']==sample['name']),sample)
        self.assertEqual(self.db.load(sample['name'])['notes'],'Personal note')
    def test_saved_empty_circuit_appears_and_opens_from_my_circuits(self):
        w=self.window;w.new_circuit();w.circuit_name.setText('Empty personal circuit');w.rename_circuit_title();w.save_button.click()
        w.show_my_circuits();w.my_circuits_page.open_buttons['Empty personal circuit'].click()
        self.assertIsNone(w.circuit)
        self.assertEqual(w.circuit_name.text(),'Empty personal circuit')
        self.assertFalse(w.current_safety_issues)
        self.assertFalse(w.has_unsaved_circuit())
        self.assertTrue(w.overview_dock.isHidden())
    def test_saved_rename_updates_only_personal_page_on_save(self):
        w=self.window;w.new_circuit();w.circuit_name.setText('Original');w.rename_circuit_title();w.save_button.click()
        w.circuit_name.setText('Renamed');w.rename_circuit_title()
        self.assertEqual(self.db.list_names(origin='user'),['Original'])
        w.save_button.click()
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
