import copy
import json
import os
import unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from build_reference import compare_build
ROOT = Path(__file__).resolve().parents[1]

class BuildReferenceTests(unittest.TestCase):
    def setUp(self):
        self.reference = json.loads((ROOT/'examples/01_led_series.json').read_text())

    def test_labels_and_nonpolar_orientation_do_not_change_match(self):
        detected = copy.deepcopy(self.reference)
        ids = {c['id']: 'part' + str(i) for i,c in enumerate(detected['components'])}
        for component in detected['components']:
            component['id'] = ids[component['id']]
        for index, net in enumerate(detected['nets']):
            net['id'] = f'node{index}'
            for terminal in net['terminals']:
                if terminal['component_id'] == 'R1':
                    terminal['terminal'] = '2' if terminal['terminal']=='1' else '1'
                terminal['component_id'] = ids[terminal['component_id']]
        detected['ground_node'] = 'node2'
        self.assertEqual(compare_build(self.reference, detected).status, 'matched')

    def test_reversed_led_is_different(self):
        detected = copy.deepcopy(self.reference)
        for net in detected['nets']:
            for t in net['terminals']:
                if t['component_id']=='LED1': t['terminal']='2' if t['terminal']=='1' else '1'
        self.assertEqual(compare_build(self.reference, detected).status, 'different')

    def test_wrong_value_and_missing_component_are_different(self):
        detected = copy.deepcopy(self.reference)
        detected['components'][1]['parameters']['resistance_ohm'] = 1000
        self.assertEqual(compare_build(self.reference,detected).status,'different')
        detected = copy.deepcopy(self.reference)
        detected['components'] = [c for c in detected['components'] if c['id']!='R1']
        for net in detected['nets']:
            net['terminals']=[t for t in net['terminals'] if t['component_id']!='R1']
        self.assertIn('Missing', compare_build(self.reference,detected).messages[0])

    def test_search_limit_does_not_report_mismatch(self):
        self.assertEqual(compare_build(self.reference,self.reference,search_limit=0).status,'inconclusive')

    def test_ui_check_preserves_reference_and_database(self):
        import tempfile
        from PySide6.QtWidgets import QApplication
        from main import CircuitWindow
        from database import CircuitDatabase
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            db = CircuitDatabase(Path(folder)/'test.db')
            w = CircuitWindow(database=db)
            w.load_topology(self.reference)
            self.assertFalse(w.build_toolbar.isHidden())
            self.assertTrue(w.circuit_mode_label.isHidden())
            self.assertEqual(w.circuit_mode_label.text(), 'Building from Scratch')
            w.start_reference_build()
            self.assertFalse(w.build_toolbar.isHidden())
            self.assertEqual(w.circuit_mode_label.text(), 'Building from Reference')
            before = copy.deepcopy(w.workspace_document())
            detected = copy.deepcopy(self.reference)
            detected['components'][1]['parameters']['resistance_ohm']=1000
            self.assertEqual(w.compare_detected_build(detected).status,'different')
            self.assertEqual(w.workspace_document(),before)
            self.assertEqual(db.list_names(),[])
            self.assertIsNotNone(w.reference_document)
            w.end_reference_build()
            self.assertIsNone(w.reference_document)
            self.assertFalse(w.build_toolbar.isHidden())
            db.save(self.reference)
            w.open_saved_circuit(self.reference['name'])
            self.assertEqual(w.circuit_mode_label.text(), 'Viewing Saved Circuit')
            self.assertFalse(w.build_toolbar.isHidden())
            self.assertEqual(w.reference_title_label.text(), 'Viewing Circuit')
            self.assertFalse(w.build_reference_button.isHidden())
            w.build_reference_button.click()
            self.assertFalse(w.build_toolbar.isHidden())
            w.end_build_button.click()
            self.assertEqual(w.circuit_mode_label.text(), 'Viewing Saved Circuit')
            self.assertFalse(w.build_toolbar.isHidden())
            self.assertEqual(w.reference_title_label.text(), 'Viewing Circuit')
            w.close();w.deleteLater();app.processEvents()


class ReferenceApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import tempfile
        from main import CircuitWindow
        from database import CircuitDatabase
        self.folder = tempfile.TemporaryDirectory()
        self.w = CircuitWindow(database=CircuitDatabase(Path(self.folder.name)/'db.sqlite'))
        self.data = json.loads((ROOT/'examples/01_led_series.json').read_text())
        self.w.load_topology(self.data)
        self.sent = []
        self.w.attach_power_transport(self.sent.append)
        self.w.start_reference_build()
        self.w.receive_supply_measurement(3.3, 0.0)

    def tearDown(self):
        self.w.close(); self.w.deleteLater(); self.app.processEvents(); self.folder.cleanup()

    def test_pending_and_safe_mismatch_block_without_safety_failure(self):
        w = self.w
        self.assertFalse(w.handle_enable_request('pending', 1).granted)
        wrong = copy.deepcopy(self.data)
        wrong['components'][1]['parameters']['resistance_ohm'] = 1000
        self.assertTrue(w.receive_hardware_topology(wrong, 1))
        self.assertTrue(w.safety_report.allowed)
        decision = w.handle_enable_request('different', 1)
        self.assertFalse(decision.granted)
        self.assertIn('reference_mismatch', {i.code for i in decision.issues})
        self.assertEqual(w.workspace_document()['components'], self.data['components'])
        self.assertEqual(w.build_comparison_heading.text(), 'Does Not Match')

    def test_matching_current_revision_passes_and_new_revision_revokes(self):
        w = self.w
        w.receive_hardware_topology(self.data, 1)
        self.assertTrue(w.handle_enable_request('match', 1).granted)
        wrong = copy.deepcopy(self.data)
        wrong['components'][1]['parameters']['resistance_ohm'] = 1000
        w.receive_hardware_topology(wrong, 2)
        self.assertFalse(w.handle_enable_request('changed', 2).granted)
        self.assertFalse(w.handle_enable_request('old', 1).granted)

    def test_json_preview_cannot_authorize_board_revision(self):
        w = self.w
        w.compare_detected_build(self.data)
        self.assertFalse(w.handle_enable_request('preview', 1).granted)

    def test_matching_unsafe_reference_still_denies(self):
        w = self.w
        unsafe = copy.deepcopy(self.data)
        unsafe['components'][0]['parameters']['voltage_v'] = 5
        w.load_topology(unsafe)
        w.start_reference_build()
        w.receive_hardware_topology(unsafe, 1)
        w.receive_supply_measurement(5, 0)
        self.assertEqual(w.power_protection.reference_match_status, 'matched')
        self.assertFalse(w.handle_enable_request('unsafe', 1).granted)

    def test_exiting_invalidates_approval_scratch_uses_safety_only(self):
        w = self.w
        w.receive_hardware_topology(self.data, 1)
        w.end_reference_build()
        self.assertFalse(w.handle_enable_request('after-exit', 1).granted)
        w.receive_hardware_topology(self.data, 2)
        self.assertFalse(w.power_protection.reference_required)
        self.assertTrue(w.handle_enable_request('scratch', 2).granted)
