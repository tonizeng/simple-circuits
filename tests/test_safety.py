import copy
import json
import math
import os
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from topology import parse_topology
from circuit_safety import SafetyLimits, SafetyReport, SafetyIssue, assess_circuit
from power_protection import PowerProtection
from main import CircuitWindow

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def resistor_circuit(resistance=1000, voltage=3.3):
    return {'name': 'Load', 'components': [
        {'id': 'V1', 'type': 'voltage_source', 'parameters': {'voltage_v': voltage}},
        {'id': 'R1', 'type': 'resistor', 'parameters': {'resistance_ohm': resistance}}],
        'nets': [
            {'id': 'positive', 'terminals': [{'component_id': 'V1', 'terminal': '1'}, {'component_id': 'R1', 'terminal': '1'}]},
            {'id': 'ground', 'terminals': [{'component_id': 'V1', 'terminal': '2'}, {'component_id': 'R1', 'terminal': '2'}]}],
        'ground_node': 'ground'}


class CircuitSafetyTests(unittest.TestCase):
    def codes(self, data):
        return {i.code for i in assess_circuit(parse_topology(data)).issues}

    def test_limits_and_normal_resistive_load(self):
        for kwargs in ({'max_voltage_v': 0}, {'max_current_a': math.nan}, {'max_current_a': True}):
            with self.assertRaises(ValueError):
                SafetyLimits(**kwargs)
        report = assess_circuit(parse_topology(resistor_circuit()))
        self.assertTrue(report.allowed)
        self.assertAlmostEqual(report.predicted_supply_current_a, 0.0033)

    def test_error_example_has_a_short_and_blocks_approval(self):
        circuit = parse_topology((EXAMPLES / 'errors/01_supply_short.json').read_bytes())
        report = assess_circuit(circuit)
        self.assertFalse(report.allowed)
        short = next(issue for issue in report.issues if issue.code == 'supply_short')
        self.assertEqual(short.severity, 'error')

    def test_voltage_and_predicted_supply_current_limits(self):
        self.assertIn('overvoltage', self.codes(resistor_circuit(voltage=3.31)))
        self.assertIn('predicted_overcurrent', self.codes(resistor_circuit(resistance=1)))
        self.assertNotIn('predicted_overcurrent', self.codes(resistor_circuit(resistance=2.2)))

    def test_short_through_wire_closed_switch_button_and_inductor(self):
        for kind, params in (('wire', {}), ('switch', {'closed': True}),
                             ('button', {'normally_closed': False, 'pressed': True}),
                             ('inductor', {'inductance_h': 0.01})):
            with self.subTest(kind=kind):
                data = resistor_circuit()
                data['components'][1].update(type=kind, parameters=params)
                self.assertIn('supply_short', self.codes(data))
        for kind, params in (('switch', {'closed': False}),
                             ('button', {'normally_closed': False, 'pressed': False})):
            data = resistor_circuit()
            data['components'][1].update(type=kind, parameters=params)
            self.assertNotIn('supply_short', self.codes(data))

    def test_short_directly_on_one_net(self):
        data = resistor_circuit()
        data['nets'][0]['terminals'] += data['nets'][1]['terminals']
        data['nets'] = data['nets'][:1]
        data['ground_node'] = 'positive'
        self.assertIn('supply_short', self.codes(data))

    def test_unconnected_terminal_and_unresolved_results(self):
        for path in (EXAMPLES / 'incomplete').glob('*.json'):
            data = json.loads(path.read_text())
            data['components'][0]['parameters']['voltage_v'] = 3.3
            self.assertIn('unconnected_terminal', self.codes(data))

    def test_reactive_examples_pass_settled_dc_checks(self):
        for number in ('07', '08'):
            data = json.loads(next(EXAMPLES.glob(number + '_*.json')).read_text())
            data['components'][0]['parameters']['voltage_v'] = 3.3
            self.assertEqual(self.codes(data), set())

    def test_component_ratings_and_invalid_ratings(self):
        data = resistor_circuit(resistance=100)
        params = data['components'][1]['parameters']
        for field, value in (('max_current_a', .01), ('max_voltage_v', 1), ('max_power_w', .01)):
            rated = copy.deepcopy(data)
            rated['components'][1]['parameters'][field] = value
            self.assertIn('component_rating_exceeded', self.codes(rated))
        for invalid in (-1, float('inf'), True, '10', 10**400):
            params['max_power_w'] = invalid
            self.assertIn('invalid_rating', self.codes(data))

    def test_missing_or_multiple_sources_fail_closed(self):
        data = resistor_circuit()
        data['components'][0].update(type='resistor', parameters={'resistance_ohm': 100})
        self.assertIn('source_count', self.codes(data))
        data = resistor_circuit()
        data['components'][1].update(type='voltage_source', parameters={'voltage_v': 3.3})
        self.assertIn('source_count', self.codes(data))


class PowerProtectionTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.responses = []
        self.guard = PowerProtection(clock=lambda: self.now)

    def ready(self):
        self.guard.attach_transport(self.responses.append)
        self.guard.update_report(SafetyReport((), .0033), revision=7)
        self.guard.observe(3.2, 0)

    def test_only_replies_to_explicit_board_request(self):
        self.ready()
        self.assertEqual(self.responses, [])
        decision = self.guard.handle_enable_request('press-1', 7)
        self.assertTrue(decision.granted)
        self.assertEqual(self.responses, [decision])
        self.assertEqual(decision.max_voltage_v, 3.3)
        self.assertEqual(decision.max_current_a, 1.5)

    def test_missing_connection_topology_or_telemetry_denies(self):
        self.assertFalse(self.guard.handle_enable_request('offline', 7).granted)
        self.guard.attach_transport(self.responses.append)
        self.assertFalse(self.guard.handle_enable_request('no-topology', 7).granted)
        self.guard.update_report(SafetyReport(()), revision=7)
        self.assertFalse(self.guard.handle_enable_request('no-telemetry', 7).granted)

    def test_unsafe_report_is_denied_with_reasons(self):
        self.ready()
        self.guard.update_report(SafetyReport((SafetyIssue('supply_short', 'Short detected'),)), revision=8)
        decision = self.guard.handle_enable_request('press', 8)
        self.assertFalse(decision.granted)
        self.assertIn('supply_short', {i.code for i in decision.issues})

    def test_warnings_remain_blocking(self):
        self.ready()
        self.guard.update_report(SafetyReport((SafetyIssue('open', 'Open path', severity='warning'),)), revision=8)
        self.assertFalse(self.guard.handle_enable_request('press', 8).granted)

    def test_old_or_mismatched_topology_request_is_denied(self):
        self.ready()
        self.assertFalse(self.guard.handle_enable_request('mismatch', 6).granted)
        self.guard.update_report(SafetyReport(()), revision=8)
        self.assertFalse(self.guard.handle_enable_request('old', 7).granted)
        self.assertTrue(self.guard.handle_enable_request('new', 8).granted)

    def test_library_report_or_reused_revision_cannot_authorize_hardware(self):
        self.ready()
        self.guard.update_report(SafetyReport(()))
        self.assertFalse(self.guard.handle_enable_request('library', 7).granted)
        self.guard.update_report(SafetyReport(()), revision=7)
        self.assertFalse(self.guard.handle_enable_request('reused', 7).granted)

    def test_duplicate_request_is_not_granted_again(self):
        self.ready()
        self.assertTrue(self.guard.handle_enable_request('press', 7).granted)
        decision = self.guard.handle_enable_request('press', 7)
        self.assertFalse(decision.granted)
        self.assertIn('duplicate_request', {i.code for i in decision.issues})

    def test_stale_telemetry_denied_without_any_unsolicited_command(self):
        self.ready()
        self.now = 1.1
        self.assertEqual(self.responses, [])
        self.assertFalse(self.guard.handle_enable_request('press', 7).granted)
        self.guard.observe(3.1, 0)
        self.assertTrue(self.guard.handle_enable_request('new-press', 7).granted)

    def test_overcurrent_or_overvoltage_only_produces_denial_on_request(self):
        for voltage, current in ((3.31, 0), (-1, 0), (3.2, 1.51), (3.2, -1.51)):
            self.setUp()
            self.ready()
            self.assertFalse(self.guard.observe(voltage, current))
            self.assertEqual(self.responses, [])
            self.assertFalse(self.guard.handle_enable_request('press', 7).granted)

    def test_exact_voltage_and_current_ceiling_is_allowed(self):
        self.ready()
        self.assertTrue(self.guard.observe(3.3, 1.5))
        self.assertTrue(self.guard.handle_enable_request('press', 7).granted)

    def test_invalid_numeric_measurements_cannot_reuse_old_sample(self):
        for voltage, current in ((float('nan'), 0), (True, 0), (3.2, '1'), (10**400, 0)):
            self.setUp()
            self.ready()
            self.assertFalse(self.guard.observe(voltage, current))
            self.assertFalse(self.guard.handle_enable_request('press', 7).granted)

    def test_firmware_fault_must_be_cleared_by_firmware(self):
        self.ready()
        self.guard.report_firmware_fault('Board overcurrent protection tripped')
        self.guard.observe(3.2, 0)
        self.assertFalse(self.guard.handle_enable_request('press', 7).granted)
        self.guard.report_firmware_fault(None)
        self.assertTrue(self.guard.handle_enable_request('new-press', 7).granted)

    def test_disconnect_and_reconnect_require_new_snapshot_and_sample(self):
        self.ready()
        self.guard.disconnect()
        self.assertEqual(self.responses, [])
        self.assertFalse(self.guard.handle_enable_request('offline', 7).granted)
        self.guard.attach_transport(self.responses.append)
        self.assertFalse(self.guard.handle_enable_request('not-ready', 7).granted)
        self.guard.update_report(SafetyReport(()), revision=1)
        self.guard.observe(3.1, 0)
        self.assertTrue(self.guard.handle_enable_request('ready', 1).granted)

    def test_failed_response_is_not_reported_as_success(self):
        self.ready()
        def failing(response):
            raise OSError('disconnected')
        self.guard.transport = failing
        decision = self.guard.handle_enable_request('press', 7)
        self.assertFalse(decision.granted)
        self.assertIn('response_failed', {i.code for i in decision.issues})


class SafetyUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = CircuitWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()

    def test_no_desktop_enable_off_reset_or_details_buttons(self):
        from PySide6.QtWidgets import QPushButton
        texts = {b.text() for b in self.window.findChildren(QPushButton)}
        self.assertFalse({'Enable power', 'Power off', 'Reset fault', 'Safety details'} & texts)

    def test_five_volt_example_shows_automatic_error_card(self):
        from PySide6.QtWidgets import QLabel
        data = json.loads((EXAMPLES / '01_led_series.json').read_text())
        data['components'][0]['parameters']['voltage_v'] = 5
        self.window.load_topology(data)
        self.assertTrue(self.window.scene.items())
        dialog = self.window.safety_panel
        self.assertIsNotNone(dialog)
        self.assertFalse(dialog.isWindow())
        self.assertIs(dialog.parentWidget(), self.window.circuit_status_card)
        self.assertIn('Errors detected', [label.text() for label in dialog.findChildren(QLabel)])
        self.assertIn('3.3 V', self.window.safety_status_text)

    def test_open_path_shows_warning_card(self):
        from PySide6.QtWidgets import QLabel
        data = json.loads((EXAMPLES / 'incomplete/03_parallel_resistors_incomplete.json').read_text())
        data['components'][0]['parameters']['voltage_v'] = 3.3
        self.window.load_topology(data)
        self.assertIn('Review required', [l.text() for l in self.window.safety_panel.findChildren(QLabel)])
        self.assertFalse(self.window.safety_report.allowed)

    def test_board_request_gets_green_light_for_measured_valid_topology(self):
        responses = []
        self.window.attach_power_transport(responses.append)
        self.assertTrue(self.window.receive_hardware_topology(resistor_circuit(), 1))
        self.assertTrue(self.window.receive_supply_measurement(3.1, 0))
        self.assertAlmostEqual(self.window.simulation_result.components['R1'].current_a, .0031)
        self.assertEqual(self.window.circuit.components[0].parameters['voltage_v'], 3.3)
        self.assertEqual(responses, [])
        decision = self.window.handle_enable_request('board-press', 1)
        self.assertTrue(decision.granted)
        self.assertEqual(responses, [decision])

    def test_library_circuit_cannot_grant_board_power(self):
        responses = []
        self.window.attach_power_transport(responses.append)
        self.window.load_topology(resistor_circuit())
        self.window.receive_supply_measurement(3.2, 0)
        self.assertFalse(self.window.handle_enable_request('board-press', 1).granted)

    def test_new_topology_rejects_request_for_old_revision(self):
        self.window.attach_power_transport(lambda response: None)
        self.window.receive_hardware_topology(resistor_circuit(), 1)
        self.window.receive_supply_measurement(3.2, 0)
        self.window.receive_hardware_topology(resistor_circuit(resistance=2000), 2)
        self.assertFalse(self.window.handle_enable_request('old-press', 1).granted)
        self.assertTrue(self.window.handle_enable_request('new-press', 2).granted)

    def test_invalid_topology_is_not_cleared_by_old_circuit_measurements(self):
        self.window.attach_power_transport(lambda response: None)
        self.window.receive_hardware_topology(resistor_circuit(), 1)
        self.window.receive_supply_measurement(3.2, 0)
        self.assertFalse(self.window.receive_hardware_topology({'components': [], 'nets': 'bad'}, 2))
        self.window.receive_supply_measurement(3.2, 0)
        self.assertFalse(self.window.safety_report.allowed)
        self.assertFalse(self.window.handle_enable_request('press', 1).granted)

    def test_safety_panel_is_embedded_in_sidebar_without_covering_canvas(self):
        self.window.load_topology(resistor_circuit())
        self.app.processEvents()
        size = self.window.canvas.size()
        self.window.load_topology(resistor_circuit(voltage=5))
        self.app.processEvents()
        panel = self.window.safety_panel
        self.assertTrue(panel.embedded)
        self.assertIs(panel.parentWidget(), self.window.circuit_status_card)
        self.assertEqual(self.window.canvas.size(), size)
        self.assertTrue(self.window.isEnabled())
        self.assertTrue(panel.isVisible())
        self.window.load_topology(resistor_circuit())
        self.assertEqual(panel.issues, ())
        self.assertTrue(panel.isVisible())
        self.assertEqual(panel.handle.text(), "Checks passed")

    def test_short_badge_identifies_shorting_wire_with_message(self):
        from schematic import DiagnosticBadge
        self.window.load_topology((EXAMPLES / 'errors/01_supply_short.json').read_bytes())
        badges = [item for item in self.window.scene.items() if isinstance(item, DiagnosticBadge)]
        self.assertEqual({b.component_id for b in badges}, {'W1'})
        self.assertTrue(all(b.severity == 'error' and 'shorted' in b.toolTip() for b in badges))
        self.window.load_topology(resistor_circuit())
        self.assertFalse(any(isinstance(item, DiagnosticBadge) for item in self.window.scene.items()))

    def test_open_terminal_has_a_warning_badge_with_node_prefixed_message(self):
        from schematic import DiagnosticBadge
        self.window.load_topology((EXAMPLES / 'incomplete/03_parallel_resistors_incomplete.json').read_bytes())
        badges = [item for item in self.window.scene.items() if isinstance(item, DiagnosticBadge)]
        self.assertEqual(len(badges), 1)
        self.assertEqual(badges[0].component_id, 'R2')
        self.assertEqual(badges[0].severity, 'warning')
        self.assertIn('n_open: R2 terminal 2 is unconnected.', badges[0].toolTip())
        self.assertEqual(badges[0].issues[0].terminal_refs, (('R2', '2'),))

    def test_broken_return_has_one_badge_for_both_disconnected_ends(self):
        from schematic import DiagnosticBadge
        self.window.load_topology((EXAMPLES / 'incomplete/04_switch_led_incomplete.json').read_bytes())
        badges = [item for item in self.window.scene.items() if isinstance(item, DiagnosticBadge)]
        self.assertEqual(len(badges), 1)
        self.assertIn('V1 terminal 2', badges[0].toolTip())
        self.assertIn('LED1 terminal 2', badges[0].toolTip())

    def assert_results_hidden(self):
        from schematic import ComponentSymbol
        symbols = [item for item in self.window.scene.items() if isinstance(item, ComponentSymbol)]
        self.assertTrue(symbols)
        for symbol in symbols:
            self.assertEqual(symbol.result_box.childItems()[0].text(), ('Voltage' if symbol.component.type == 'voltage_source' else 'Voltage drop') + ': —\nCurrent: —')
            self.assertIsNone(symbol.current_arrow_points())

    def test_warning_and_error_hide_all_results_not_only_unknown_values(self):
        for path in ('incomplete/03_parallel_resistors_incomplete.json', 'errors/01_supply_short.json'):
            self.window.load_topology((EXAMPLES / path).read_bytes())
            self.assert_results_hidden()
            self.assertTrue(all('DC' not in issue.message for issue in self.window.safety_report.issues))
        self.window.load_topology(resistor_circuit())
        from schematic import ComponentSymbol
        resistor = next(s for s in self.window.scene.items() if isinstance(s, ComponentSymbol) and s.component.id == 'R1')
        self.assertIn('3.3 V', resistor.result_box.childItems()[0].text())

    def test_runtime_warning_also_hides_results(self):
        self.window.attach_power_transport(lambda response: None)
        self.window.receive_hardware_topology(resistor_circuit(), 1)
        self.window.receive_supply_measurement(3.2, 0)
        self.window.handle_enable_request('mismatch', 0)
        self.assert_results_hidden()
        self.window.handle_enable_request('valid', 1)
        self.assertEqual(self.window.current_safety_issues, ())

    def test_sidebar_cards_grow_with_long_messages_without_inner_scrolling(self):
        from PySide6.QtWidgets import QScrollArea
        self.window.load_topology(resistor_circuit(voltage=5))
        self.app.processEvents()
        panel = self.window.safety_panel
        short_height = panel.height()
        panel.set_issues((SafetyIssue('long', 'Long explanation. ' * 60),))
        self.app.processEvents()
        self.assertGreater(panel.height(), short_height)
        self.assertEqual(panel.findChildren(QScrollArea), [])
        self.window.load_topology(resistor_circuit())
        self.app.processEvents()
        self.assertIs(panel.parentWidget(), self.window.circuit_status_card)
        self.assertEqual(panel.issues, ())

    def test_request_denial_popup_is_not_hidden_by_next_timer_poll(self):
        self.window.attach_power_transport(lambda response: None)
        self.window.receive_hardware_topology(resistor_circuit(), 1)
        self.window.receive_supply_measurement(3.2, 0)
        self.assertFalse(self.window.handle_enable_request('press', 0).granted)
        self.window.poll_power_protection()
        self.assertTrue(self.window.safety_panel.isVisible())
        self.assertIn('topology_mismatch', {i.code for i in self.window.safety_panel.issues})

    def test_compact_status_orders_issues_and_clicks_keep_fault_badges(self):
        from PySide6.QtWidgets import QPushButton, QLabel
        from schematic import DiagnosticBadge
        self.window.load_topology((EXAMPLES / 'errors/02_short_disconnected_led.json').read_bytes())
        panel = self.window.safety_panel
        self.assertEqual(panel.handle.text(), "Errors detected")
        self.assertIn("Power not approved", [l.text() for l in panel.findChildren(QLabel)])
        rows = [b for b in panel.findChildren(QPushButton) if b.objectName() == "issueRow"]
        codes = [row.property("issueCode") for row in rows]
        self.assertLess(codes.index("supply_short"), codes.index("unconnected_terminal"))
        badge_count = sum(isinstance(item, DiagnosticBadge) for item in self.window.scene.items())
        self.assertGreater(badge_count, 0)
        next(row for row in rows if row.property("issueCode") == "supply_short").click()
        self.assertEqual(self.window.component_details.component_id, "W1")
        next(row for row in rows if row.property("issueCode") == "unconnected_terminal").click()
        self.assertEqual(self.window.component_details.node_id, "n_open")
        self.assertEqual(sum(isinstance(item, DiagnosticBadge) for item in self.window.scene.items()), badge_count)
        sidebar_layout = self.window.circuit_sidebar.layout()
        self.assertIs(sidebar_layout.itemAt(0).widget(), self.window.circuit_status_card)

    def test_any_warning_shows_calculation_summary_even_when_solver_succeeds(self):
        from PySide6.QtWidgets import QLabel
        self.window.load_topology((EXAMPLES / 'incomplete/03_parallel_resistors_incomplete.json').read_bytes())
        self.assertEqual(self.window.simulation_result.status, "solved")
        self.assertTrue(self.window.current_safety_issues)
        summary = self.window.safety_panel.findChild(QLabel, "calculationAvailability")
        self.assertIsNotNone(summary)
        self.assertFalse(summary.isHidden())

    def test_calculation_availability_is_a_summary_not_a_clickable_fault(self):
        from PySide6.QtWidgets import QPushButton, QLabel
        self.window.load_topology((EXAMPLES / 'errors/02_short_disconnected_led.json').read_bytes())
        panel = self.window.safety_panel
        rows = [b for b in panel.findChildren(QPushButton) if b.objectName() == "issueRow"]
        self.assertNotIn("unknown_current", [row.property("issueCode") for row in rows])
        self.assertIsNotNone(panel.findChild(QLabel, "calculationAvailability"))
        self.assertIn("unknown_current", {issue.code for issue in self.window.current_safety_issues})
        self.assertFalse(self.window.safety_report.allowed)
        panel.set_issues((SafetyIssue("unresolved_circuit", "Values unavailable", severity="warning"),))
        self.assertEqual(panel.handle.text(), "Checks incomplete")
        self.assertIn("Power not approved", [label.text() for label in panel.findChildren(QLabel)])

    def test_short_selection_highlights_both_source_and_shorting_wire(self):
        from schematic import ComponentSymbol, highlight_color
        self.window.load_topology((EXAMPLES / 'errors/02_short_disconnected_led.json').read_bytes())
        issue = next(i for i in self.window.current_safety_issues if i.code == "supply_short")
        self.window.inspect_safety_issue(issue)
        symbols = {s.component.id: s for s in self.window.scene.items() if isinstance(s, ComponentSymbol)}
        for cid in ("V1", "W1"):
            self.assertTrue(symbols[cid].highlighted)
            self.assertEqual(highlight_color(symbols[cid], "component").name(), "#c43c25")
        self.window.refresh_component_details()
        self.assertTrue(symbols["V1"].highlighted)
        self.window.clear_component_selection()
        self.assertFalse(symbols["V1"].highlighted)
        self.assertFalse(symbols["W1"].highlighted)

    def test_short_error_and_open_warning_are_both_shown(self):
        from safety_ui import SafetyAlertsPanel
        from PySide6.QtWidgets import QLabel
        dialog = SafetyAlertsPanel()
        dialog.set_issues((SafetyIssue('short', 'Short circuit detected'),
                           SafetyIssue('open', 'R2 terminal 2 is unconnected', severity='warning')))
        titles = [l.text() for l in dialog.findChildren(QLabel)]
        self.assertIn('Error!', titles)
        self.assertIn('Warning!', titles)
        dialog.close()
