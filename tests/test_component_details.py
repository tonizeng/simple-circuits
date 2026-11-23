import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QLineEdit
from PySide6.QtSvgWidgets import QSvgWidget
from component_details import ComponentDetailsPanel, delivered_power, HELP_TOPICS
from topology import parse_topology
from simulation import solve_dc
from simulation.mna import ComponentResult

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'

class InspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = ComponentDetailsPanel()
        self.circuit = parse_topology((EXAMPLES / '01_led_series.json').read_bytes())
        self.solution = solve_dc(self.circuit)

    def tearDown(self):
        if self.panel.help_dialog:
            self.panel.help_dialog.close()
        self.panel.close()
        self.panel.deleteLater()
        self.app.processEvents()

    def text(self):
        return '\n'.join(w.text() for w in self.panel.findChildren(QLabel))

    def test_power_uses_passive_sign_convention_and_requires_both_values(self):
        self.assertAlmostEqual(delivered_power(ComponentResult(3, -.004)), .012)
        self.assertAlmostEqual(delivered_power(ComponentResult(3, .004)), -.012)
        self.assertIsNone(delivered_power(ComponentResult(3, None)))
        self.assertIsNone(delivered_power(None))

    def test_source_properties_and_worked_example_are_data_driven(self):
        source = self.circuit.components[0]
        result = self.solution.components[source.id]
        self.panel.set_content(source, result)
        text = self.text()
        self.assertIn('Source voltage', text)
        self.assertIn('Nominal', text)
        self.assertIn('Source voltage', text)
        self.assertIn('Calculated', text)
        self.assertNotIn('Power delivered · calculated', text)
        self.assertNotIn('COMPONENT INSPECTOR', text)
        self.assertIn('3.939 mA', text)
        self.assertNotIn('13 mW', text)
        self.assertNotIn('Using your circuit’s values:', text)
        self.assertFalse(self.panel.findChildren(QLineEdit))
        self.assertFalse(self.panel.symbol_icon.pixmap().isNull())

    def test_empty_inspector_is_neutral_and_shows_selection_prompt(self):
        self.assertFalse(hasattr(self.panel, "help_button"))
        self.assertTrue(self.panel.close_button.isHidden())
        self.assertFalse(self.panel.selection_prompt.isHidden())
        self.assertNotIn("No component selected", self.text())
        self.assertEqual(self.panel.title.text(), "Circuit Overview")
        self.assertNotIn("Electrical Properties", self.text())
        self.assertNotIn("Calculated", self.text())
        self.assertNotIn("—", self.text())
        self.assertIn("component or node", self.panel.selection_prompt.text())
        self.panel.set_content(self.circuit.components[0], self.solution.components['V1'])
        self.assertTrue(self.panel.selection_prompt.isHidden())
        self.panel.clear_selection()
        self.assertFalse(self.panel.selection_prompt.isHidden())

    def test_unavailable_results_do_not_fabricate_worked_example(self):
        self.panel.set_content(self.circuit.components[0], None)
        self.assertNotIn('Using your circuit’s values:', self.text())
        self.assertGreaterEqual(self.text().count('—'), 2)
        self.assertIn('3.3 V', self.text())

    def test_help_retains_all_topics_and_can_expand(self):
        self.panel.show_help()
        self.assertIsNotNone(self.panel.help_dialog)
        self.assertFalse(self.panel.help_dialog.isModal())
        for title, explanation in HELP_TOPICS:
            button = next(b for b in self.panel.help_dialog.findChildren(QPushButton) if title in b.text())
            body = next(l for l in self.panel.help_dialog.findChildren(QLabel) if l.text() == explanation)
            self.assertTrue(body.isHidden())
            button.click()
            self.assertFalse(body.isHidden())

    def test_every_component_keeps_purpose_without_any_equations_section(self):
        seen = set()
        for path in sorted(EXAMPLES.glob("*.json")):
            circuit = parse_topology(path.read_bytes())
            for component in circuit.components:
                self.panel.set_content(component, None)
                content = self.panel.scroll.widget()
                self.assertTrue(any("Purpose" in b.text() for b in content.findChildren(QPushButton)))
                self.assertFalse(any("Equations" in b.text() for b in content.findChildren(QPushButton)))
                equations = content.findChildren(QSvgWidget)
                self.assertEqual(len(equations), 0)
                self.assertTrue(all(e.renderer().isValid() for e in equations))
                seen.add(component.type)
        self.assertEqual(len(seen), 11)

    def test_variables_removed_and_purpose_collapse_is_retained(self):
        component = self.circuit.components[1]
        result = self.solution.components[component.id]
        self.panel.set_content(component, result)
        buttons = self.panel.findChildren(QPushButton)
        self.assertFalse(any('Understanding the variables' in b.text() for b in buttons))
        purpose = next(b for b in buttons if 'Purpose' in b.text())
        purpose.click()
        self.panel.set_content(component, result)
        purpose = next(b for b in self.panel.scroll.widget().findChildren(QPushButton) if 'Purpose' in b.text())
        self.assertFalse(purpose.isChecked())

if __name__ == '__main__':
    unittest.main()
